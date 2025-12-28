import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Ти казав що маєш GROUP_CHAT_ID
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID", "").strip()

DB_PATH = os.getenv("DB_PATH", "data/offers.sqlite").strip()


def require_env(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"{name} не заданий (Railway → Variables)")
    return value


def get_group_chat_id() -> int:
    raw = require_env("GROUP_CHAT_ID", GROUP_CHAT_ID)
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError("GROUP_CHAT_ID має бути числом (наприклад -1001234567890)")
