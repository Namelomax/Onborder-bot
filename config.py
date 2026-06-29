"""Конфигурация системы. Все секреты читаются из переменных окружения (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения {name}. "
            f"Скопируйте .env.example в .env и заполните значения."
        )
    return value


# Telegram (Bot API через aiogram — нужен только токен бота)
BOT_TOKEN = _require("BOT_TOKEN")
# Необязательный прокси (socks5://... или http://...), если Telegram заблокирован
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY") or None

# OpenRouter (ИИ-ассистент)
OPENROUTER_API_KEY = _require("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Хранилище и база знаний
DB_PATH = os.getenv("DB_PATH", "onboarding.db")
KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", "knowledge_base")

# Временные характеристики (ТЗ 4.1.4): время отклика ИИ не более 10 секунд
AI_TIMEOUT_SECONDS = 10
