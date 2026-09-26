"""Telegram-бот «Таро».
 
Сценарий:
  вопрос -> проверка + язык -> баланс
     * есть платные кредиты -> сразу ПОЛНЫЙ разбор (списывается 1 кредит)
     * иначе есть бесплатные -> короткий ТИЗЕР с триггером «ГЛУБЖЕ» (списывается 1 бесплатный)
     * иначе -> предложение оплаты
  «ГЛУБЖЕ» / кнопка -> полный разбор тех же карт за 1 платный кредит (или предложение оплаты)
"""
import asyncio
import html
import logging
 
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    User,
)
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import InlineKeyboardBuilder
 
import ai
import config
import db
import i18n
import tarot
 
log = logging.getLogger(__name__)
router = Router()
 
busy: set[int] = set()  # пользователи, у которых прямо сейчас идёт генерация
pending: dict[int, str] = {}  # предложенные переформулировки вопросов
 
# ------------------------------------------------------------------ утилиты
 
 
def split_text(text: str, limit: int = 3800) -> list[str]:
    """Режет длинный текст по абзацам под лимит Telegram (4096 символов)."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        while len(para) > limit:  # редкий случай: один гигантский абзац
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:limit])
            para = para[limit:]
        if len(current) + len(para) + 2 > limit and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks
 
 
async def user_lang(user: User) -> str:
    """Язык интерфейса: определённый ранее по вопросам, иначе язык Telegram."""
    return i18n.ui_lang(await db.get_lang(user.id) or user.language_code)
 
 
def balance_text(lang: str, b: db.Balance) -> str:
    key = "bal_free_daily" if config.FREE_MODE == "daily" else "bal_free_total"
    text = i18n.t(lang, key, free=b.free_left, limit=config.FREE_READINGS)
    if b.credits:
        text += "\n" + i18n.t(lang, "bal_credits", credits=b.credits)
    return text
 
 
def buy_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, p in config.PACKS.items():
        kb.button(
            text=i18n.t(lang, "btn_pack", credits=p["credits"], stars=p["stars"]),
            callback_data=f"buy:{key}",
        )
    kb.adjust(1)
    return kb.as_markup()
 
 
def deeper_keyboard(lang: str, reading_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=i18n.t(lang, "btn_deeper"), callback_data=f"deeper:{reading_id}")]]
    )
 
 
async def send_paywall(bot: Bot, chat_id: int, lang: str, code: str | None = None, deeper: bool = False) -> None:
    if deeper:
        key = "paywall_deeper"
    else:
        key = "paywall_new_daily" if config.FREE_MODE == "daily" else "paywall_new"
    await bot.send_message(
        chat_id, i18n.t(lang, key, keyword=i18n.keyword(code or lang)), reply_markup=buy_keyboard(lang)
    )
 
 
async def send_deep(bot: Bot, chat_id: int, user_id: int, lang: str, text: str) -> None:
    """Отправляет платный разбор и футер с остатком кредитов."""
    for chunk in split_text(text):
        await bot.send_message(chat_id, ai.render_html(chunk))
    b = await db.get_balance(user_id)
    await bot.send_message(
        chat_id,
        i18n.t(lang, "footer_paid", left=b.credits),
        reply_markup=buy_keyboard(lang) if b.credits == 0 else None,
    )
 
 
# ------------------------------------------------------------------ новый вопрос
 
 
async def process_question(bot: Bot, chat_id: int, user: User, question: str) -> None:
    await _guarded(bot, chat_id, user, _process(bot, chat_id, user, question))
 
 
async def process_deeper(bot: Bot, chat_id: int, user: User, reading_id: int | None = None) -> None:
    await _guarded(bot, chat_id, user, _deeper(bot, chat_id, user, reading_id))
 
 
async def _guarded(bot: Bot, chat_id: int, user: User, coro) -> None:
    """Один активный запрос на пользователя + общий перехват непредвиденных ошибок."""
    if user.id in busy:
        coro.close()
        await bot.send_message(chat_id, i18n.t(i18n.ui_lang(user.language_code), "busy"))
        return
    busy.add(user.id)
    try:
        await coro
    except Exception:
        log.exception("unexpected error for user %s", user.id)
        await bot.send_message(chat_id, i18n.t(i18n.ui_lang(user.language_code), "unexpected"))
    finally:
        busy.discard(user.id)
 
 
async def _process(bot: Bot, chat_id: int, user: User, question: str) -> None:
    question = " ".join(question.split())
    pending.pop(user.id, None)
 
    # Язык для сообщений ДО вызова OpenAI: эвристика по тексту -> сохранённый -> язык Telegram.
    lang = i18n.ui_lang(i18n.quick_lang(question) or await db.get_lang(user.id) or user.language_code)
 
    if len(question) < config.MIN_QUESTION_LEN:
        await bot.send_message(chat_id, i18n.t(lang, "too_short"))
        return
    if len(question) > config.MAX_QUESTION_LEN:
        await bot.send_message(chat_id, i18n.t(lang, "too_long", n=len(question), max=config.MAX_QUESTION_LEN))
        return
 
    await db.touch_user(user.id, user.username)
 
    # 1. Есть ли доступ? Проверяем ДО обращения к OpenAI, чтобы не тратить деньги впустую.
    if (await db.get_balance(user.id)).total <= 0:
        await send_paywall(bot, chat_id, lang)
        return
 
    # 2. Проверка формулировки + определение языка (один вызов).
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        try:
            verdict = await ai.validate_question(question, hint_lang=user.language_code)
        except Exception:
            log.exception("validation failed")
            await bot.send_message(chat_id, i18n.t(lang, "validation_error"))
            return
 
    code = (verdict.lang or i18n.quick_lang(question) or user.language_code or "en").lower()[:2]
    lang = i18n.ui_lang(code)
    await db.set_lang(user.id, code)
 
    if verdict.status == "crisis":
        await bot.send_message(chat_id, i18n.t(lang, "crisis"))
        return
 
    if verdict.status == "refuse":
        await bot.send_message(chat_id, html.escape(verdict.reason) if verdict.reason else i18n.t(lang, "refuse_default"))
        return
 
    if verdict.status == "rephrase":
        text = i18n.t(lang, "rephrase", reason=html.escape(verdict.reason))
        markup = None
        if verdict.suggestion:
            pending[user.id] = verdict.suggestion
            text += "\n\n" + i18n.t(lang, "rephrase_example", suggestion=html.escape(verdict.suggestion))
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=i18n.t(lang, "btn_use_suggestion"), callback_data="use_suggestion")]]
            )
        await bot.send_message(chat_id, text, reply_markup=markup)
        return
 
    # 3. Списываем расклад атомарно. Платный кредит в приоритете: платящий пользователь
    #    сразу получает полный разбор, тизер — только для бесплатных.
    kind = None
    for candidate in ("paid", "free"):
        if await db.try_consume(user.id, candidate):
            kind = candidate
            break
    if kind is None:
        await send_paywall(bot, chat_id, lang, code)
        return
 
    # Тизер и платный разбор — разные расклады (1 карта / новые 4), а не один и тот же
    # spread из классификатора: verdict.spread здесь больше не определяет карты.
    spread = tarot.TEASER_SPREAD if kind == "free" else tarot.DEEP_SPREAD
    cards = tarot.draw(spread)
 
    if kind == "free":
        await _send_teaser(bot, chat_id, user, lang, code, question, spread, cards)
    else:
        await _send_full(bot, chat_id, user, lang, code, question, spread, cards)
 
 
async def _send_teaser(bot, chat_id, user, lang, code, question, spread, cards) -> None:
    """БЕСПЛАТНО: карты одной строкой + короткий тизер + CTA + кнопка."""
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        try:
            teaser = await ai.generate_teaser(question, spread, cards, code)
        except Exception:
            log.exception("teaser failed")
            await db.refund(user.id, "free")
            await bot.send_message(chat_id, i18n.t(lang, "gen_error"))
            return
 
    reading_id = await db.save_reading(user.id, question, spread.key, cards, teaser, code, "free")
 
    text = f"{tarot.format_cards_compact(cards, code)}\n\n{ai.render_html(teaser)}"
    b = await db.get_balance(user.id)
    if b.free_left == 0:
        text += "\n\n" + i18n.t(lang, "last_free")
    await bot.send_message(chat_id, text, reply_markup=deeper_keyboard(lang, reading_id))
 
 
async def _send_full(bot, chat_id, user, lang, code, question, spread, cards) -> None:
    """ПЛАТНО (пользователь с кредитами задал новый вопрос): полный расклад + глубокий разбор."""
    await bot.send_message(chat_id, tarot.format_cards_html(spread, cards, code))
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        try:
            deep = await ai.generate_deep_reading(question, spread, cards, code)
        except Exception:
            log.exception("deep reading failed")
            await db.refund(user.id, "paid")
            await bot.send_message(chat_id, i18n.t(lang, "gen_error"))
            return
 
    await db.save_reading(user.id, question, spread.key, cards, deep, code, "paid")
    await send_deep(bot, chat_id, user.id, lang, deep)
 
 
# ------------------------------------------------------------------ «ГЛУБЖЕ»: раскрытие полного разбора
 
 
async def _deeper(bot: Bot, chat_id: int, user: User, reading_id: int | None) -> None:
    await db.touch_user(user.id, user.username)
    row = await db.get_reading(user.id, reading_id)
    lang = i18n.ui_lang((row.lang if row else None) or await db.get_lang(user.id) or user.language_code)
 
    if row is None or row.unlocked:
        await bot.send_message(chat_id, i18n.t(lang, "deeper_none"))
        return
 
    code = row.lang or lang
    teaser_cards = [tarot.DrawnCard(**c) for c in row.cards]  # ДО списания: если данные битые — ничего не потеряно
 
    # Занимаем раскрытие (нельзя открыть один тизер дважды) и списываем платный кредит.
    if not await db.claim_unlock(row.id, user.id):
        await bot.send_message(chat_id, i18n.t(lang, "deeper_none"))
        return
    if not await db.try_consume(user.id, "paid"):
        await db.release_unlock(row.id)
        await send_paywall(bot, chat_id, lang, code, deeper=True)
        return
 
    # Платный разбор — новый независимый расклад: карта тизера исключается из раздачи.
    spread = tarot.DEEP_SPREAD
    cards = tarot.draw(spread, exclude={c.card for c in teaser_cards})
 
    await bot.send_message(chat_id, tarot.format_cards_html(spread, cards, code))
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        try:
            # Тизер передаём модели только как контекст «что уже почувствовал пользователь»,
            # чтобы разбор не повторял его и не пересказывал ту же карту.
            deep = await ai.generate_deep_reading(row.question, spread, cards, code, teaser=row.answer)
        except Exception:
            log.exception("deep reading failed")
            await db.release_unlock(row.id)
            await db.refund(user.id, "paid")
            await bot.send_message(chat_id, i18n.t(lang, "gen_error"))
            return
 
    await db.finish_unlock(row.id, deep)
    await send_deep(bot, chat_id, user.id, lang, deep)
 
 
# ------------------------------------------------------------------ команды
 
 
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await db.touch_user(message.from_user.id, message.from_user.username)
    lang = await user_lang(message.from_user)
    b = await db.get_balance(message.from_user.id)
    await message.answer(i18n.t(lang, "welcome", balance=balance_text(lang, b)))
 
 
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(i18n.t(await user_lang(message.from_user), "help"))
 
 
@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    await db.touch_user(message.from_user.id, message.from_user.username)
    lang = await user_lang(message.from_user)
    await message.answer(balance_text(lang, await db.get_balance(message.from_user.id)))
 
 
@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    lang = await user_lang(message.from_user)
    await message.answer(i18n.t(lang, "buy_menu"), reply_markup=buy_keyboard(lang))
 
 
@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    lang = await user_lang(message.from_user)
    await message.answer(i18n.t(lang, "paysupport", support=html.escape(config.SUPPORT_CONTACT)))
 
 
# ------------------------------------------------------------------ оплата
 
 
@router.callback_query(F.data.startswith("buy:"))
async def on_buy(cb: CallbackQuery, bot: Bot) -> None:
    lang = await user_lang(cb.from_user)
    key = cb.data.split(":", 1)[1]
    pack = config.PACKS.get(key)
    if not pack:
        await cb.answer(i18n.t(lang, "pack_not_found"), show_alert=True)
        return
    await cb.answer()
    await bot.send_invoice(
        chat_id=cb.from_user.id,
        title=i18n.t(lang, "invoice_title", credits=pack["credits"]),
        description=i18n.t(lang, "invoice_desc", credits=pack["credits"]),
        payload=f"pack:{key}",
        currency="XTR",  # Telegram Stars: provider_token не нужен
        prices=[LabeledPrice(label=i18n.t(lang, "invoice_title", credits=pack["credits"]), amount=pack["stars"])],
    )
 
 
@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery) -> None:
    pack = config.PACKS.get(q.invoice_payload.removeprefix("pack:"))
    ok = bool(pack) and q.currency == "XTR" and q.total_amount == pack["stars"]
    lang = await user_lang(q.from_user)
    await q.answer(ok=ok, error_message=None if ok else i18n.t(lang, "precheckout_error"))
 
 
@router.message(F.successful_payment)
async def on_paid(message: Message) -> None:
    sp = message.successful_payment
    user = message.from_user
    lang = await user_lang(user)
    pack = config.PACKS.get(sp.invoice_payload.removeprefix("pack:"))
    if not pack:
        log.error("payment with unknown payload: %s (charge %s)", sp.invoice_payload, sp.telegram_payment_charge_id)
        await message.answer(i18n.t(lang, "pay_unknown", support=html.escape(config.SUPPORT_CONTACT)))
        return
    await db.touch_user(user.id, user.username)
    credited = await db.register_payment(
        sp.telegram_payment_charge_id, user.id, sp.invoice_payload, sp.total_amount, pack["credits"]
    )
    if not credited:
        return
    b = await db.get_balance(user.id)
    row = await db.get_reading(user.id)
    if row and not row.unlocked:
        # Человек упёрся в paywall на «ГЛУБЖЕ» — предлагаем открыть его разбор одним нажатием.
        await message.answer(
            i18n.t(lang, "paid_thanks_pending", credits=pack["credits"], keyword=i18n.keyword(row.lang or lang)),
            reply_markup=deeper_keyboard(lang, row.id),
        )
    else:
        await message.answer(i18n.t(lang, "paid_thanks", credits=pack["credits"], left=b.credits))
 
 
# ------------------------------------------------------------------ вопросы и триггеры
 
 
@router.callback_query(F.data.startswith("deeper:"))
async def on_deeper_button(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    try:
        reading_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        return
    await process_deeper(bot, cb.from_user.id, cb.from_user, reading_id)
 
 
@router.callback_query(F.data == "use_suggestion")
async def on_use_suggestion(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    question = pending.pop(cb.from_user.id, None)
    if not question:
        lang = await user_lang(cb.from_user)
        await bot.send_message(cb.from_user.id, i18n.t(lang, "suggestion_expired"))
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await process_question(bot, cb.from_user.id, cb.from_user, question)
 
 
@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, bot: Bot) -> None:
    if i18n.is_deeper_request(message.text):  # ГЛУБЖЕ / DAHA DERİN / DEEPER
        await process_deeper(bot, message.chat.id, message.from_user)
    else:
        await process_question(bot, message.chat.id, message.from_user, message.text)
 
 
@router.message()
async def on_other(message: Message) -> None:
    await message.answer(i18n.t(await user_lang(message.from_user), "text_only"))
 
 
# ------------------------------------------------------------------ запуск
 
 
async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await db.init(config.DB_PATH)
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    for code, cmds in i18n.COMMANDS.items():
        await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in cmds], language_code=code)
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in i18n.COMMANDS["en"]])  # по умолчанию
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
 
 
if __name__ == "__main__":
    asyncio.run(main())
 