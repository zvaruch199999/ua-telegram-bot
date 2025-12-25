import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# -----------------------------
# Simple in-memory storage
# -----------------------------
offers = {}
offer_counter = 1

# -----------------------------
# Keyboards
# -----------------------------
def offer_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Актуально", callback_data=f"status:active:{offer_id}"),
            InlineKeyboardButton("⏳ Резервація", callback_data=f"status:reserved:{offer_id}")
        ],
        [
            InlineKeyboardButton("❌ Неактуально", callback_data=f"status:inactive:{offer_id}")
        ]
    ])

# -----------------------------
# Commands
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/add – додати тестову пропозицію\n"
    )

async def add_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global offer_counter

    offer_id = offer_counter
    offer_counter += 1

    offers[offer_id] = {
        "id": offer_id,
        "text": f"🏠 Пропозиція #{offer_id}\n2-кімнатна квартира\nЦіна: 500$",
        "status": "active"
    }

    await update.message.reply_text(
        offers[offer_id]["text"],
        reply_markup=offer_keyboard(offer_id)
    )

# -----------------------------
# Callbacks
# -----------------------------
async def status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, status, offer_id = query.data.split(":")
    offer_id = int(offer_id)

    if offer_id not in offers:
        await query.answer("Пропозиція не знайдена", show_alert=True)
        return

    offers[offer_id]["status"] = status

    status_text = {
        "active": "✅ Актуально",
        "reserved": "⏳ Резервація",
        "inactive": "❌ Неактуально"
    }

    await query.edit_message_text(
        text=f"{offers[offer_id]['text']}\n\nСтатус: {status_text[status]}",
        reply_markup=offer_keyboard(offer_id)
    )

# -----------------------------
# Main
# -----------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_offer))
    app.add_handler(CallbackQueryHandler(status_callback, pattern="^status:"))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

