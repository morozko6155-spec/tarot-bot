"""Колода Таро (78 карт), расклады и честная раздача. Названия локализованы: ru / tr / en.
 
Карта хранится как индекс 0..77, поэтому расклад можно показать на любом языке —
в том числе спустя время, когда пользователь открывает полный разбор.
Для остальных языков названия карт и позиций показываются по-английски,
а сам текст толкования модель пишет на языке пользователя.
"""
import random
from dataclasses import dataclass
 
# SystemRandom берёт энтропию у ОС — расклад нельзя предсказать или воспроизвести.
_rng = random.SystemRandom()
 
LANGS = ("ru", "tr", "en")
DECK_SIZE = 78
REVERSED_PROBABILITY = 0.5
 
 
def pick_lang(code: str | None) -> str:
    code = (code or "").lower()[:2]
    return code if code in LANGS else "en"
 
 
# ------------------------------------------------------------------ названия карт
 
MAJOR = {
    "ru": [
        "Шут", "Маг", "Верховная Жрица", "Императрица", "Император", "Иерофант",
        "Влюблённые", "Колесница", "Сила", "Отшельник", "Колесо Фортуны",
        "Справедливость", "Повешенный", "Смерть", "Умеренность", "Дьявол",
        "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир",
    ],
    "tr": [
        "Deli", "Büyücü", "Başrahibe", "İmparatoriçe", "İmparator", "Aziz",
        "Aşıklar", "Savaş Arabası", "Güç", "Ermiş", "Kader Çarkı",
        "Adalet", "Asılan Adam", "Ölüm", "Denge", "Şeytan",
        "Kule", "Yıldız", "Ay", "Güneş", "Yargı", "Dünya",
    ],
    "en": [
        "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
        "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
        "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
        "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World",
    ],
}
SUITS = {
    "ru": ["Жезлов", "Кубков", "Мечей", "Пентаклей"],
    "tr": ["Asa", "Kupa", "Kılıç", "Tılsım"],
    "en": ["Wands", "Cups", "Swords", "Pentacles"],
}
RANKS = {
    "ru": ["Туз", "Двойка", "Тройка", "Четвёрка", "Пятёрка", "Шестёрка", "Семёрка",
           "Восьмёрка", "Девятка", "Десятка", "Паж", "Рыцарь", "Королева", "Король"],
    "tr": ["Ası", "İkilisi", "Üçlüsü", "Dörtlüsü", "Beşlisi", "Altılısı", "Yedilisi",
           "Sekizlisi", "Dokuzlusu", "Onlusu", "Uşağı", "Şövalyesi", "Kraliçesi", "Kralı"],
    "en": ["Ace", "Two", "Three", "Four", "Five", "Six", "Seven",
           "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"],
}
MINOR_FORMAT = {"ru": "{rank} {suit}", "tr": "{suit} {rank}", "en": "{rank} of {suit}"}
 
assert all(len(v) == 22 for v in MAJOR.values())
assert all(len(v) == 4 for v in SUITS.values())
assert all(len(v) == 14 for v in RANKS.values())
 
 
def card_name(card: int, lang: str) -> str:
    lang = pick_lang(lang)
    if card < 22:
        return MAJOR[lang][card]
    suit, rank = divmod(card - 22, 14)
    return MINOR_FORMAT[lang].format(rank=RANKS[lang][rank], suit=SUITS[lang][suit])
 
 
ORIENTATION = {
    "ru": ("прямая", "перевёрнутая"),
    "tr": ("düz", "ters"),
    "en": ("upright", "reversed"),
}
SPREAD_LABEL = {"ru": "Расклад", "tr": "Açılım", "en": "Spread"}
 
 
def orientation(reversed_: bool, lang: str) -> str:
    return ORIENTATION[pick_lang(lang)][1 if reversed_ else 0]
 
 
# ------------------------------------------------------------------ расклады
 
 
@dataclass(frozen=True)
class Spread:
    key: str
    titles: dict
    positions: dict  # lang -> tuple названий позиций
    when: str  # подсказка для классификатора вопросов (ai.py)
 
    @property
    def size(self) -> int:
        return len(self.positions["en"])
 
    def title(self, lang: str) -> str:
        return self.titles[pick_lang(lang)]
 
    def position(self, index: int, lang: str) -> str:
        return self.positions[pick_lang(lang)][index]
 
 
SPREADS: dict[str, Spread] = {
    s.key: s
    for s in (
        Spread(
            "yes_no",
            {"ru": "Одна карта: ответ", "tr": "Tek kart: cevap", "en": "Single card: the answer"},
            {"ru": ("Ответ",), "tr": ("Cevap",), "en": ("Answer",)},
            "closed yes/no question or 'should I…' with a simple choice",
        ),
        Spread(
            "three_card",
            {"ru": "Ситуация — Препятствие — Совет", "tr": "Durum — Engel — Tavsiye",
             "en": "Situation — Obstacle — Advice"},
            {"ru": ("Ситуация", "Препятствие", "Совет"), "tr": ("Durum", "Engel", "Tavsiye"),
             "en": ("Situation", "Obstacle", "Advice")},
            "universal spread: general question about a situation, work, money, wellbeing, "
            "self-development; use when nothing more precise fits",
        ),
        Spread(
            "timeline",
            {"ru": "Прошлое — Настоящее — Будущее", "tr": "Geçmiş — Şimdi — Gelecek",
             "en": "Past — Present — Future"},
            {"ru": ("Прошлое", "Настоящее", "Ближайшее будущее"),
             "tr": ("Geçmiş", "Şimdi", "Yakın gelecek"),
             "en": ("Past", "Present", "Near future")},
            "how something will develop, where a situation is heading, what was and what will be",
        ),
        Spread(
            "relationship",
            {"ru": "Отношения", "tr": "İlişki", "en": "Relationship"},
            {"ru": ("Ты", "Другой человек", "Связь между вами", "Вызов", "Потенциал"),
             "tr": ("Sen", "Diğer kişi", "Aranızdaki bağ", "Zorluk", "Potansiyel"),
             "en": ("You", "The other person", "The bond between you", "The challenge", "The potential")},
            "relationship with a specific person: partner, family member, friend, colleague; "
            "what someone feels or thinks about the user",
        ),
        Spread(
            "choice",
            {"ru": "Выбор", "tr": "Seçim", "en": "Choice"},
            {"ru": ("Вариант А", "Вариант Б", "Скрытый фактор", "Совет"),
             "tr": ("Seçenek A", "Seçenek B", "Gizli etken", "Tavsiye"),
             "en": ("Option A", "Option B", "Hidden factor", "Advice")},
            "choice between two or more options, a fork in the road, 'A or B'",
        ),
    )
}
DEFAULT_SPREAD = "three_card"
 
# ------------------------------------------------------------------ фиксированные расклады уровней
#
# Бесплатный тизер и платный разбор — не разные версии одного расклада, а два разных расклада:
# тизер всегда 1 карта, платный разбор — независимая новая раздача из 4 карт (Совет — как часть
# раскладов, а не отдельная опция уровня; см. ai.py). Их размер и позиции не зависят от того,
# какой тематический spread выбрал классификатор вопроса (SPREADS выше) — тот по-прежнему
# используется только для оценки формулировки.
 
TEASER_SPREAD = Spread(
    "teaser",
    {"ru": "Один знак", "tr": "Tek işaret", "en": "A single sign"},
    {"ru": ("Знак",), "tr": ("İşaret",), "en": ("Sign",)},
    "free teaser: exactly one card",
)
 
DEEP_SPREAD = Spread(
    "deep",
    {"ru": "Полный расклад", "tr": "Tam açılım", "en": "Full spread"},
    {
        "ru": ("Ситуация", "Скрытые влияния", "Прогноз", "Совет"),
        "tr": ("Durum", "Gizli etkiler", "Tahmin", "Tavsiye"),
        "en": ("Situation", "Hidden influences", "Forecast", "Advice"),
    },
    "paid deep reading: a brand-new independent spread, never reuses the teaser's card",
)
 
 
@dataclass(frozen=True)
class DrawnCard:
    pos: int  # индекс позиции в раскладе
    card: int  # индекс карты 0..77
    reversed: bool
 
 
def draw(spread: Spread, exclude: set[int] | None = None) -> list[DrawnCard]:
    """Раздаёт карты для расклада. exclude — индексы карт, которые не должны выпасть
    (например, карта уже показанного бесплатного тизера — платный разбор должен быть новым)."""
    pool = [i for i in range(DECK_SIZE) if not exclude or i not in exclude]
    ids = _rng.sample(pool, spread.size)  # без повторов
    return [DrawnCard(i, cid, _rng.random() < REVERSED_PROBABILITY) for i, cid in enumerate(ids)]
 
 
# ------------------------------------------------------------------ вывод
 
 
def format_cards_html(spread: Spread, cards: list[DrawnCard], lang: str) -> str:
    """Полный расклад с позициями — показывается вместе с платным разбором."""
    lang = pick_lang(lang)
    lines = [f"🔮 <b>{SPREAD_LABEL[lang]}: {spread.title(lang)}</b>", ""]
    for c in cards:
        arrow = "🔻" if c.reversed else "🔺"
        lines.append(
            f"{arrow} <b>{spread.position(c.pos, lang)}:</b> "
            f"{card_name(c.card, lang)} ({orientation(c.reversed, lang)})"
        )
    return "\n".join(lines)
 
 
def format_cards_compact(cards: list[DrawnCard], lang: str) -> str:
    """Одна строка для бесплатного тизера: только названия, позиции скрыты."""
    lang = pick_lang(lang)
    parts = [
        card_name(c.card, lang) + (f" ({orientation(True, lang)})" if c.reversed else "")
        for c in cards
    ]
    return "🃏 " + " · ".join(parts)
 
 
def describe(spread: Spread, cards: list[DrawnCard], lang: str) -> str:
    """Текстовое описание расклада для промпта OpenAI."""
    lang = pick_lang(lang)
    return "\n".join(
        f"{i}. {spread.position(c.pos, lang)} — {card_name(c.card, lang)} ({orientation(c.reversed, lang)})"
        for i, c in enumerate(cards, 1)
    )
 