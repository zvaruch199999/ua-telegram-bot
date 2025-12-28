import os

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()

# ВАЖЛИВО: ти казав що маєш GROUP_CHAT_ID
# Підтримую обидва варіанти (щоб не падало): GROUP_CHAT_ID або GROUP_ID
_group = os.getenv("GROUP_CHAT_ID") or os.getenv("GROUP_ID") or ""
GROUP_CHAT_ID = int(_group) if _group.strip().lstrip("-").isdigit() else None

DB_PATH = os.getenv("DB_PATH", "data/bot.db")
