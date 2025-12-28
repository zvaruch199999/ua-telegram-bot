import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# ВАЖЛИВО: саме GROUP_CHAT_ID (а не GROUP_ID)
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID", "").strip()

DB_PATH = os.getenv("DB_PATH", "data/bot.db").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий (Environment Variables).")

if not GROUP_CHAT_ID_RAW:
    raise RuntimeError("GROUP_CHAT_ID не заданий (Environment Variables).")

try:
    GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)
except ValueError:
    raise RuntimeError("GROUP_CHAT_ID має бути числом (наприклад: -1001234567890).")
