"""Локализация статических сообщений бота (ru / tr / en) и слов-триггеров «полного разбора».
 
Тексты, которые пишет OpenAI, локализуются самой моделью (см. ai.py) — на любом языке.
Здесь только то, что бот отправляет сам: меню, ошибки, оплата, CTA-строка.
Чтобы добавить язык, скопируйте один из блоков в STRINGS, CTA, KEYWORDS и COMMANDS.
"""
import re
 
SUPPORTED = ("ru", "tr", "en")
 
# Слово, которое пользователь пишет, чтобы открыть полный (платный) разбор.
KEYWORDS = {"ru": "ГЛУБЖЕ", "tr": "DAHA DERİN", "en": "DEEPER"}
DEFAULT_KEYWORD = "DEEPER"  # для языков, которых нет в таблице
 
# Строка-триггер в конце бесплатного ответа.
CTA = {
    "ru": "🔮 Карта показала только часть картины. Причина, риски и точный прогноз ждут в полном разборе — напиши: ГЛУБЖЕ",
    "tr": "🔮 Kart resmin yalnızca bir kısmını gösterdi. Neden, riskler ve net tahmin tam analizde seni bekliyor — yaz: DAHA DERİN",
    "en": "🔮 The card only showed part of the picture. The reason, the risks and a clear forecast are waiting in the full reading — write: DEEPER",
}
 
COMMANDS = {
    "ru": [("start", "Начать"), ("balance", "Мой баланс"), ("buy", "Купить полные разборы"),
           ("paysupport", "Поддержка по оплате"), ("help", "Помощь")],
    "tr": [("start", "Başla"), ("balance", "Bakiyem"), ("buy", "Tam analiz satın al"),
           ("paysupport", "Ödeme desteği"), ("help", "Yardım")],
    "en": [("start", "Start"), ("balance", "My balance"), ("buy", "Buy full readings"),
           ("paysupport", "Payment support"), ("help", "Help")],
}
 
# ------------------------------------------------------------------ нормализация
 
# Турецкие буквы приводим к ASCII: иначе "İ".lower() даёт два символа и сравнение ломается.
_TR_MAP = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c",
})
 
 
def norm(text: str) -> str:
    text = text.translate(_TR_MAP).lower()
    text = re.sub(r"[^\w\s]", " ", text)  # пунктуация и эмодзи
    return " ".join(text.split())
 
 
# Строго точное совпадение: ложное срабатывание списывает платный кредит.
_DEEPER_WORDS = {norm(v) for v in KEYWORDS.values()} | {"deeper"}
 
 
def is_deeper_request(text: str) -> bool:
    return norm(text) in _DEEPER_WORDS
 
 
def keyword(code: str | None) -> str:
    return KEYWORDS.get((code or "").lower()[:2], DEFAULT_KEYWORD)
 
 
def quick_lang(text: str) -> str | None:
    """Дешёвая эвристика для случаев, когда LLM ещё не вызывали (например, paywall)."""
    if re.search(r"[іїєґІЇЄҐ]", text):
        return "uk"
    if re.search(r"[а-яёА-ЯЁ]", text):
        return "ru"
    if re.search(r"[ğĞışŞİ]", text):
        return "tr"
    return None
 
 
def ui_lang(code: str | None) -> str:
    code = (code or "").lower()[:2]
    return code if code in SUPPORTED else "en"
 
 
def t(lang: str, key: str, **kw) -> str:
    table = STRINGS.get(lang) or STRINGS["en"]
    kw.setdefault("disclaimer", table["disclaimer"])
    return table[key].format(**kw)
 
 
# ------------------------------------------------------------------ тексты
 
STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "disclaimer": "Таро — способ взглянуть на ситуацию по-новому, а не приговор и не замена совета специалиста.",
        "welcome": (
            "🔮 <b>Добро пожаловать!</b>\n\n"
            "Задай вопрос о своей жизни, выборе или ситуации — я открою карты Таро и дам короткое предсказание. "
            "Полный разбор — по твоему желанию.\n\n"
            "<b>Примеры вопросов:</b>\n"
            "• Что мне важно понять о моей работе сейчас?\n"
            "• Стоит ли принять предложение о переезде?\n"
            "• Что чувствует ко мне близкий человек?\n\n"
            "{balance}\n\n"
            "Просто напиши вопрос ⬇️\n\n<i>{disclaimer}</i>"
        ),
        "help": (
            "Напиши один ясный вопрос — расклад я выберу сама.\n\n"
            "Сначала ты получишь короткое предсказание. Хочешь полный разбор — напиши ГЛУБЖЕ.\n\n"
            "/balance — мой баланс\n/buy — купить полные разборы\n/paysupport — поддержка по оплате"
        ),
        "bal_free_total": "🎁 Бесплатных раскладов: {free} из {limit}",
        "bal_free_daily": "🎁 Бесплатных раскладов сегодня: {free} из {limit}",
        "bal_credits": "💎 Полных разборов: {credits}",
        "paywall_new": (
            "🔒 Бесплатные расклады закончились.\n\n"
            "Чтобы продолжить и получать полные разборы — выбери пакет. "
            "Оплата в Telegram Stars ⭐, разборы не сгорают."
        ),
        "paywall_new_daily": (
            "🔒 Бесплатные расклады на сегодня закончились.\n\n"
            "Приходи завтра или выбери пакет полных разборов. Оплата в Telegram Stars ⭐, разборы не сгорают."
        ),
        "paywall_deeper": (
            "🔓 Полный разбор — с причинами, рисками и прогнозом — доступен в платных пакетах.\n\n"
            "Выбери пакет, а после оплаты нажми кнопку или ещё раз напиши {keyword}."
        ),
        "busy": "⏳ Я ещё раскладываю карты по твоему предыдущему вопросу…",
        "too_short": "Вопрос слишком короткий. Опиши ситуацию хотя бы одним предложением.",
        "too_long": "Вопрос слишком длинный ({n} символов, максимум {max}). Сформулируй главное — Таро любит ясность.",
        "validation_error": "⚠️ Не получилось проверить вопрос. Расклад не списан — попробуй ещё раз.",
        "crisis": (
            "💛 Мне очень жаль, что тебе сейчас так тяжело. Это важнее любого расклада.\n\n"
            "Пожалуйста, поговори с близким человеком или обратись на линию психологической поддержки "
            "либо в местную службу экстренной помощи. Ты не один."
        ),
        "refuse_default": "Такой вопрос я взять не могу. Давай попробуем другую тему — например, о твоём выборе или ситуации.",
        "rephrase": "🤔 Давай уточним вопрос.\n\n{reason}",
        "rephrase_example": "Например:\n<i>«{suggestion}»</i>",
        "btn_use_suggestion": "✅ Задать так",
        "suggestion_expired": "Формулировка устарела — отправь вопрос заново.",
        "gen_error": "⚠️ Не удалось составить толкование. Расклад возвращён на твой баланс — попробуй ещё раз.",
        "unexpected": "⚠️ Что-то пошло не так. Расклад не списан — попробуй ещё раз.",
        "last_free": "🎁 Это был твой последний бесплатный расклад.",
        "btn_deeper": "🔓 Полный разбор",
        "deeper_none": "Сейчас нечего раскрывать: полный разбор уже открыт или вопроса ещё не было. Задай новый вопрос 🔮",
        "footer_paid": "<i>{disclaimer}</i>\n\n💎 Осталось полных разборов: {left}",
        "text_only": "Я понимаю только текст. Напиши свой вопрос словами 🔮",
        "buy_menu": "Выбери пакет полных разборов (оплата в Telegram Stars ⭐):",
        "btn_pack": "Полные разборы ×{credits} — {stars} ⭐",
        "invoice_title": "Полные разборы Таро ×{credits}",
        "invoice_desc": "Полные разборы Таро: {credits} шт. Причины, риски и прогноз. Не сгорают.",
        "pack_not_found": "Пакет не найден",
        "precheckout_error": "Пакет недоступен, открой /buy ещё раз.",
        "pay_unknown": "Платёж получен, но пакет не распознан. Напиши {support}.",
        "paid_thanks": "✨ Спасибо! Начислено полных разборов: {credits}.\nВ твоём балансе: {left}\n\nЗадай вопрос ⬇️",
        "paid_thanks_pending": (
            "✨ Спасибо! Начислено полных разборов: {credits}.\n"
            "Твой закрытый разбор уже ждёт — нажми кнопку ниже или напиши {keyword} ⬇️"
        ),
        "paysupport": "По вопросам оплаты и возвратов пиши {support}. Укажи дату и сумму платежа.",
    },
    "tr": {
        "disclaimer": "Tarot, duruma yeni bir gözle bakmanın yoludur; bir hüküm ya da uzman tavsiyesinin yerini tutmaz.",
        "welcome": (
            "🔮 <b>Hoş geldin!</b>\n\n"
            "Hayatın, seçimlerin ya da yaşadığın durum hakkında bir soru yaz — Tarot kartlarını açıp kısa bir yorum yapayım. "
            "Tam analiz istersen ayrıca açılır.\n\n"
            "<b>Örnek sorular:</b>\n"
            "• İş hayatımda şu an neyi anlamam gerekiyor?\n"
            "• Taşınma teklifini kabul etmeli miyim?\n"
            "• Yakınım bana karşı ne hissediyor?\n\n"
            "{balance}\n\n"
            "Sorunu yazman yeterli ⬇️\n\n<i>{disclaimer}</i>"
        ),
        "help": (
            "Tek ve net bir soru yaz — açılımı ben seçerim.\n\n"
            "Önce kısa bir yorum alırsın. Tam analiz için DAHA DERİN yaz.\n\n"
            "/balance — bakiyem\n/buy — tam analiz paketi al\n/paysupport — ödeme desteği"
        ),
        "bal_free_total": "🎁 Ücretsiz açılım: {free} / {limit}",
        "bal_free_daily": "🎁 Bugünkü ücretsiz açılım: {free} / {limit}",
        "bal_credits": "💎 Tam analiz hakkı: {credits}",
        "paywall_new": (
            "🔒 Ücretsiz açılımların bitti.\n\n"
            "Devam etmek ve tam analizlere ulaşmak için bir paket seç. "
            "Ödeme Telegram Stars ⭐ ile, haklar silinmez."
        ),
        "paywall_new_daily": (
            "🔒 Bugünkü ücretsiz açılımların bitti.\n\n"
            "Yarın tekrar gel ya da bir tam analiz paketi seç. Ödeme Telegram Stars ⭐ ile, haklar silinmez."
        ),
        "paywall_deeper": (
            "🔓 Nedenleri, riskleri ve tahminiyle tam analiz ücretli paketlerde.\n\n"
            "Bir paket seç; ödemeden sonra butona bas ya da tekrar {keyword} yaz."
        ),
        "busy": "⏳ Önceki sorunun kartlarını hâlâ diziyorum…",
        "too_short": "Soru çok kısa. Durumunu en az bir cümleyle anlat.",
        "too_long": "Soru çok uzun ({n} karakter, en fazla {max}). Asıl meseleyi yaz — Tarot netliği sever.",
        "validation_error": "⚠️ Soru kontrol edilemedi. Açılım hakkın düşülmedi — tekrar dene.",
        "crisis": (
            "💛 Şu an bu kadar zorlandığını duyduğuma çok üzüldüm. Bu, her açılımdan daha önemli.\n\n"
            "Lütfen yakın biriyle konuş ya da bulunduğun ülkedeki psikolojik destek hattına veya "
            "acil yardım servisine ulaş. Yalnız değilsin."
        ),
        "refuse_default": "Bu soruyu alamıyorum. Başka bir konuyu deneyelim — örneğin senin seçimin ya da durumun hakkında.",
        "rephrase": "🤔 Soruyu biraz netleştirelim.\n\n{reason}",
        "rephrase_example": "Örneğin:\n<i>«{suggestion}»</i>",
        "btn_use_suggestion": "✅ Böyle sor",
        "suggestion_expired": "Bu ifade artık geçerli değil — soruyu yeniden gönder.",
        "gen_error": "⚠️ Yorum hazırlanamadı. Açılım hakkın iade edildi — tekrar dene.",
        "unexpected": "⚠️ Bir şeyler ters gitti. Açılım hakkın düşülmedi — tekrar dene.",
        "last_free": "🎁 Bu son ücretsiz açılımındı.",
        "btn_deeper": "🔓 Tam analiz",
        "deeper_none": "Şu an açılacak bir analiz yok: tam analiz zaten açık ya da henüz soru sormadın. Yeni bir soru sor 🔮",
        "footer_paid": "<i>{disclaimer}</i>\n\n💎 Kalan tam analiz: {left}",
        "text_only": "Yalnızca metin anlıyorum. Sorunu kelimelerle yaz 🔮",
        "buy_menu": "Tam analiz paketini seç (ödeme Telegram Stars ⭐ ile):",
        "btn_pack": "Tam analiz ×{credits} — {stars} ⭐",
        "invoice_title": "Tarot tam analiz ×{credits}",
        "invoice_desc": "Tarot tam analiz: {credits} adet. Nedenler, riskler ve tahmin. Süresi dolmaz.",
        "pack_not_found": "Paket bulunamadı",
        "precheckout_error": "Paket kullanılamıyor, /buy komutunu tekrar aç.",
        "pay_unknown": "Ödeme alındı ama paket tanınamadı. {support} ile iletişime geç.",
        "paid_thanks": "✨ Teşekkürler! {credits} tam analiz hakkı eklendi.\nBakiyen: {left}\n\nSorunu yaz ⬇️",
        "paid_thanks_pending": (
            "✨ Teşekkürler! {credits} tam analiz hakkı eklendi.\n"
            "Bekleyen analizin hazır — aşağıdaki butona bas ya da {keyword} yaz ⬇️"
        ),
        "paysupport": "Ödeme ve iade konularında {support} ile iletişime geç. Lütfen ödemenin tarihini ve tutarını belirt.",
    },
    "en": {
        "disclaimer": "Tarot is a way to look at a situation with fresh eyes — not a verdict and not a substitute for professional advice.",
        "welcome": (
            "🔮 <b>Welcome!</b>\n\n"
            "Ask a question about your life, a choice or a situation — I'll draw the Tarot cards and give you a short reading. "
            "The full reading is yours on request.\n\n"
            "<b>Example questions:</b>\n"
            "• What should I understand about my work right now?\n"
            "• Should I accept the offer to move?\n"
            "• What does someone close to me feel about me?\n\n"
            "{balance}\n\n"
            "Just type your question ⬇️\n\n<i>{disclaimer}</i>"
        ),
        "help": (
            "Write one clear question — I'll pick the spread myself.\n\n"
            "You'll get a short reading first. Want the full one? Write DEEPER.\n\n"
            "/balance — my balance\n/buy — buy full readings\n/paysupport — payment support"
        ),
        "bal_free_total": "🎁 Free readings: {free} of {limit}",
        "bal_free_daily": "🎁 Free readings today: {free} of {limit}",
        "bal_credits": "💎 Full readings: {credits}",
        "paywall_new": (
            "🔒 Your free readings are over.\n\n"
            "To continue and get full readings, pick a pack. "
            "Payment in Telegram Stars ⭐, readings never expire."
        ),
        "paywall_new_daily": (
            "🔒 Your free readings for today are over.\n\n"
            "Come back tomorrow or pick a pack of full readings. Payment in Telegram Stars ⭐, readings never expire."
        ),
        "paywall_deeper": (
            "🔓 The full reading — with causes, risks and a forecast — is part of the paid packs.\n\n"
            "Pick a pack, then tap the button or write {keyword} again after paying."
        ),
        "busy": "⏳ I'm still laying out the cards for your previous question…",
        "too_short": "That question is too short. Describe the situation in at least one sentence.",
        "too_long": "That question is too long ({n} characters, max {max}). State the main thing — Tarot loves clarity.",
        "validation_error": "⚠️ I couldn't check the question. Nothing was deducted — please try again.",
        "crisis": (
            "💛 I'm so sorry you're going through such a hard time. That matters more than any reading.\n\n"
            "Please talk to someone close to you, or reach out to a mental health helpline or your local "
            "emergency services. You are not alone."
        ),
        "refuse_default": "I can't take that question. Let's try another topic — for example, about your own choice or situation.",
        "rephrase": "🤔 Let's clarify the question.\n\n{reason}",
        "rephrase_example": "For example:\n<i>«{suggestion}»</i>",
        "btn_use_suggestion": "✅ Ask it this way",
        "suggestion_expired": "That wording has expired — please send your question again.",
        "gen_error": "⚠️ I couldn't prepare the reading. Your reading was returned to your balance — please try again.",
        "unexpected": "⚠️ Something went wrong. Nothing was deducted — please try again.",
        "last_free": "🎁 That was your last free reading.",
        "btn_deeper": "🔓 Full reading",
        "deeper_none": "There's nothing to unlock right now: the full reading is already open or no question was asked yet. Ask a new question 🔮",
        "footer_paid": "<i>{disclaimer}</i>\n\n💎 Full readings left: {left}",
        "text_only": "I only understand text. Write your question in words 🔮",
        "buy_menu": "Choose a pack of full readings (payment in Telegram Stars ⭐):",
        "btn_pack": "Full readings ×{credits} — {stars} ⭐",
        "invoice_title": "Tarot full readings ×{credits}",
        "invoice_desc": "Tarot full readings: {credits}. Causes, risks and a forecast. They never expire.",
        "pack_not_found": "Pack not found",
        "precheckout_error": "This pack is unavailable, open /buy again.",
        "pay_unknown": "Payment received, but the pack wasn't recognised. Please contact {support}.",
        "paid_thanks": "✨ Thank you! {credits} full readings added.\nYour balance: {left}\n\nAsk your question ⬇️",
        "paid_thanks_pending": (
            "✨ Thank you! {credits} full readings added.\n"
            "Your locked reading is waiting — tap the button below or write {keyword} ⬇️"
        ),
        "paysupport": "For payment and refund questions contact {support}. Please include the date and amount.",
    },
}
 
