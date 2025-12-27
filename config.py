import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID_RAW = os.getenv("GROUP_ID")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not GROUP_ID_RAW:
    raise RuntimeError("GROUP_ID is not set")

GROUP_ID = int(GROUP_ID_RAW)
