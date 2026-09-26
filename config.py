import os

from dotenv import load_dotenv

load_dotenv()

# --- Секреты ---
BOT_TOKEN = os.getenv("8867860123:AAGvNpJwnAN20AbTZti_q-WwxImdlztJe8I")
print("TOKEN:", repr(BOT_TOKEN))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# --- Модели OpenAI ---
# Дешёвая модель проверяет вопрос, более сильная пишет толкование.
# Укажите актуальные названия моделей из вашего аккаунта OpenAI.
MODEL_VALIDATE = os.getenv("OPENAI_MODEL_VALIDATE", "gpt-4o-mini")
MODEL_READING = os.getenv("OPENAI_MODEL_READING", "gpt-4o")
# Короткий бесплатный тизер можно генерировать дешёвой моделью.
MODEL_TEASER = os.getenv("OPENAI_MODEL_TEASER", MODEL_VALIDATE)

# --- Бесплатный лимит ---
# FREE_MODE=total  -> FREE_READINGS бесплатных тизеров на всё время (пробный период)
# FREE_MODE=daily  -> FREE_READINGS бесплатных тизеров в сутки (по UTC)
FREE_READINGS = int(os.getenv("FREE_READINGS", "2"))
FREE_MODE = os.getenv("FREE_MODE", "total")

# --- Прочее ---
DB_PATH = os.getenv("DB_PATH", "tarot.db")
SUPPORT_CONTACT = os.getenv("SUPPORT_CONTACT", "@your_support")

MIN_QUESTION_LEN = 8
MAX_QUESTION_LEN = 400

# --- Платные пакеты (цена в Telegram Stars, валюта XTR) ---
# 1 кредит = 1 полный разбор. Названия кнопок локализуются в i18n.py.
PACKS = {
    "p1": {"credits": 1, "stars": 145},
    "p3": {"credits": 3, "stars": 390},
    "p5": {"credits": 5, "stars": 600}
}
