"""SQLite-хранилище: пользователи, бесплатный лимит, платные кредиты, раскрытие полных разборов, платежи."""
import dataclasses
import datetime as dt
import json
import time
from dataclasses import dataclass

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    free_used   INTEGER NOT NULL DEFAULT 0,
    free_period TEXT    NOT NULL DEFAULT '',
    credits     INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    question   TEXT    NOT NULL,
    spread     TEXT    NOT NULL,
    cards      TEXT    NOT NULL,
    answer     TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    charge_id  TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    payload    TEXT    NOT NULL,
    stars      INTEGER NOT NULL,
    credits    INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
"""

# Колонки, добавленные позже. Применяются и к новой, и к уже существующей базе.
# Старые записи readings получают unlocked=1: полного разбора у них «открывать» нечего.
MIGRATIONS = [
    ("users", "lang", "TEXT"),
    ("readings", "lang", "TEXT"),
    ("readings", "tier", "TEXT NOT NULL DEFAULT 'paid'"),  # 'free' = тизер, 'paid' = полный разбор
    ("readings", "unlocked", "INTEGER NOT NULL DEFAULT 1"),  # 0 = тизер ждёт раскрытия
    ("readings", "deep_answer", "TEXT"),  # полный разбор, открытый после тизера
]

_db: aiosqlite.Connection | None = None


@dataclass(frozen=True)
class Balance:
    free_left: int
    credits: int

    @property
    def total(self) -> int:
        return self.free_left + self.credits


@dataclass(frozen=True)
class Reading:
    id: int
    question: str
    spread: str
    cards: list  # список словарей DrawnCard
    answer: str  # тизер (tier='free') или полный разбор (tier='paid')
    lang: str | None
    tier: str
    unlocked: bool


async def init(path: str) -> None:
    global _db
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    for table, column, ddl in MIGRATIONS:
        cur = await _db.execute(f"PRAGMA table_info({table})")
        existing = {r["name"] for r in await cur.fetchall()}
        if column not in existing:
            await _db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    await _db.commit()


async def close() -> None:
    if _db is not None:
        await _db.close()


# ------------------------------------------------------------------ пользователи и баланс


def _period() -> str:
    if config.FREE_MODE == "daily":
        return dt.datetime.now(dt.timezone.utc).date().isoformat()
    return "total"


async def _roll_period(user_id: int) -> None:
    """В режиме daily обнуляет счётчик бесплатных раскладов при смене даты."""
    p = _period()
    await _db.execute(
        "UPDATE users SET free_used = 0, free_period = ? "
        "WHERE user_id = ? AND free_period != ?",
        (p, user_id, p),
    )


async def touch_user(user_id: int, username: str | None) -> None:
    await _db.execute(
        "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET username = excluded.username",
        (user_id, username, int(time.time())),
    )
    await _db.commit()


async def set_lang(user_id: int, lang: str) -> None:
    await _db.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
    await _db.commit()


async def get_lang(user_id: int) -> str | None:
    cur = await _db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return row["lang"] if row else None


async def get_balance(user_id: int) -> Balance:
    await _roll_period(user_id)
    cur = await _db.execute(
        "SELECT free_used, credits FROM users WHERE user_id = ?", (user_id,)
    )
    row = await cur.fetchone()
    await _db.commit()
    if row is None:
        return Balance(config.FREE_READINGS, 0)
    return Balance(max(config.FREE_READINGS - row["free_used"], 0), row["credits"])


async def try_consume(user_id: int, kind: str) -> bool:
    """Атомарно списывает один расклад.

    kind='free' — бесплатный тизер (лимит FREE_READINGS),
    kind='paid' — платный кредит (полный разбор).
    """
    if kind == "free":
        await _roll_period(user_id)
        cur = await _db.execute(
            "UPDATE users SET free_used = free_used + 1 WHERE user_id = ? AND free_used < ?",
            (user_id, config.FREE_READINGS),
        )
    else:
        cur = await _db.execute(
            "UPDATE users SET credits = credits - 1 WHERE user_id = ? AND credits > 0",
            (user_id,),
        )
    await _db.commit()
    return bool(cur.rowcount)


async def refund(user_id: int, kind: str) -> None:
    """Возвращает расклад, если генерация не удалась."""
    if kind == "free":
        await _db.execute(
            "UPDATE users SET free_used = MAX(free_used - 1, 0) WHERE user_id = ?",
            (user_id,),
        )
    else:
        await _db.execute(
            "UPDATE users SET credits = credits + 1 WHERE user_id = ?", (user_id,)
        )
    await _db.commit()


# ------------------------------------------------------------------ расклады


async def save_reading(
    user_id: int, question: str, spread: str, cards: list, answer: str, lang: str, tier: str
) -> int:
    """tier='free' -> тизер, ждёт раскрытия (unlocked=0); tier='paid' -> полный разбор (unlocked=1)."""
    cur = await _db.execute(
        "INSERT INTO readings (user_id, question, spread, cards, answer, created_at, lang, tier, unlocked) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            question,
            spread,
            json.dumps([dataclasses.asdict(c) for c in cards]),
            answer,
            int(time.time()),
            lang,
            tier,
            0 if tier == "free" else 1,
        ),
    )
    await _db.commit()
    return cur.lastrowid


async def get_reading(user_id: int, reading_id: int | None = None) -> Reading | None:
    """Последний расклад пользователя или конкретный по id."""
    if reading_id is None:
        cur = await _db.execute(
            "SELECT * FROM readings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        )
    else:
        cur = await _db.execute(
            "SELECT * FROM readings WHERE user_id = ? AND id = ?", (user_id, reading_id)
        )
    row = await cur.fetchone()
    if row is None:
        return None
    return Reading(
        id=row["id"],
        question=row["question"],
        spread=row["spread"],
        cards=json.loads(row["cards"]),
        answer=row["answer"],
        lang=row["lang"],
        tier=row["tier"],
        unlocked=bool(row["unlocked"]),
    )


async def claim_unlock(reading_id: int, user_id: int) -> bool:
    """Атомарно «занимает» раскрытие: один тизер нельзя открыть дважды."""
    cur = await _db.execute(
        "UPDATE readings SET unlocked = 1 WHERE id = ? AND user_id = ? AND unlocked = 0",
        (reading_id, user_id),
    )
    await _db.commit()
    return bool(cur.rowcount)


async def release_unlock(reading_id: int) -> None:
    await _db.execute("UPDATE readings SET unlocked = 0 WHERE id = ?", (reading_id,))
    await _db.commit()


async def finish_unlock(reading_id: int, deep_answer: str) -> None:
    await _db.execute(
        "UPDATE readings SET deep_answer = ? WHERE id = ?", (deep_answer, reading_id)
    )
    await _db.commit()


# ------------------------------------------------------------------ платежи


async def register_payment(
    charge_id: str, user_id: int, payload: str, stars: int, credits: int
) -> bool:
    """Записывает платёж и начисляет кредиты. Идемпотентно по charge_id."""
    cur = await _db.execute(
        "INSERT OR IGNORE INTO payments (charge_id, user_id, payload, stars, credits, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (charge_id, user_id, payload, stars, credits, int(time.time())),
    )
    if not cur.rowcount:  # этот платёж уже обработан
        await _db.commit()
        return False
    await _db.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits, user_id)
    )
    await _db.commit()
    return True
