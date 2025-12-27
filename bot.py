import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InputMediaPhoto,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

if not BOT_TOKEN or not GROUP_ID:
    raise RuntimeError("BOT_TOKEN або GROUP_ID не задані")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

offers = {}
offer_counter = 1


# ================= FSM =================
class OfferFSM(StatesGroup):
    photos = State()
    text = State()


class CloseDealFSM(StatesGroup):
    client_source = State()
    commission = State()
    client_name = State()
    client_contact = State()


# ================= START =================
@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Бот працює\n\n"
        "📸 Надішли фото пропозиції.\n"
        "✍️ Коли закінчиш — напиши слово:\n"
        "ГОТОВО"
    )


# ================= COLLECT PHOTOS =================
@dp.message(F.photo)
async def collect_photos(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await state.set_state(OfferFSM.photos)
    await msg.answer(f"📷 Фото додано ({len(photos)})")


# ================= FINISH PHOTOS =================
@dp.message(F.text.lower() == "готово")
async def finish_photos(msg: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await msg.answer("❌ Спочатку надішли фото")
        return
    await state.set_state(OfferFSM.text)
    await msg.answer("✍️ Надішли текст пропозиції одним повідомленням")


# ================= SAVE TEXT =================
@dp.message(OfferFSM.text)
async def save_text(msg: Message, state: FSMContext):
    global offer_counter
    data = await state.get_data()

    offer_id = offer_counter
    offer_counter += 1

    offers[offer_id] = {
        "photos": data["photos"],
        "text": msg.text,
        "status": "🟢 Актуально",
        "author_id": msg.from_user.id,
        "author": msg.from_user.username or "без_ніка"
    }

    media = [InputMediaPhoto(media=p) for p in data["photos"]]
    media[0].caption = (
        f"🏠 ПРОПОЗИЦІЯ #{offer_id}\n\n"
        f"{msg.text}\n\n"
        f"📊 Статус: {offers[offer_id]['status']}\n"
        f"👤 Маклер: @{offers[offer_id]['author']}"
    )

    await bot.send_media_group(msg.chat.id, media)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ПУБЛІКУВАТИ", callback_data=f"publish:{offer_id}")]
    ])

    await msg.answer("👆 Перевір пропозицію", reply_markup=kb)
    await state.clear()


# ================= PUBLISH =================
@dp.callback_query(F.data.startswith("publish"))
async def publish(cb: CallbackQuery):
    offer_id = int(cb.data.split(":")[1])
    offer = offers.get(offer_id)

    media = [InputMediaPhoto(media=p) for p in offer["photos"]]
    media[0].caption = (
        f"🏠 ПРОПОЗИЦІЯ #{offer_id}\n\n"
        f"{offer['text']}\n\n"
        f"📊 Статус: {offer['status']}\n"
        f"👤 Маклер: @{offer['author']}"
    )

    await bot.send_media_group(GROUP_ID, media)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"status:active:{offer_id}"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"status:reserve:{offer_id}"),
            InlineKeyboardButton(text="🔴 Неактуально", callback_data=f"status:inactive:{offer_id}")
        ],
        [InlineKeyboardButton(text="✅ Закрити угоду", callback_data=f"close:{offer_id}")]
    ])

    await bot.send_message(GROUP_ID, "🔧 Керування:", reply_markup=kb)
    await cb.answer("Опубліковано")


# ================= STATUS =================
@dp.callback_query(F.data.startswith("status"))
async def change_status(cb: CallbackQuery):
    _, status, offer_id = cb.data.split(":")
    offer_id = int(offer_id)

    statuses = {
        "active": "🟢 Актуально",
        "reserve": "🟡 Резерв",
        "inactive": "🔴 Неактуально"
    }

    offers[offer_id]["status"] = statuses[status]
    await cb.answer(f"Статус: {statuses[status]}")


# ================= CLOSE DEAL =================
@dp.callback_query(F.data.startswith("close"))
async def close_deal(cb: CallbackQuery, state: FSMContext):
    offer_id = int(cb.data.split(":")[1])
    await state.update_data(offer_id=offer_id)
    await state.set_state(CloseDealFSM.client_source)
    await bot.send_message(cb.from_user.id, "👤 Хто знайшов клієнта?")
    await cb.answer()


@dp.message(CloseDealFSM.client_source)
async def deal_step_1(msg: Message, state: FSMContext):
    await state.update_data(client_source=msg.text)
    await state.set_state(CloseDealFSM.commission)
    await msg.answer("💰 Яка сума комісії?")


@dp.message(CloseDealFSM.commission)
async def deal_step_2(msg: Message, state: FSMContext):
    await state.update_data(commission=msg.text)
    await state.set_state(CloseDealFSM.client_name)
    await msg.answer("🧾 Імʼя клієнта?")


@dp.message(CloseDealFSM.client_name)
async def deal_step_3(msg: Message, state: FSMContext):
    await state.update_data(client_name=msg.text)
    await state.set_state(CloseDealFSM.client_contact)
    await msg.answer("📞 Контакт клієнта?")


@dp.message(CloseDealFSM.client_contact)
async def deal_finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]

    offers[offer_id]["status"] = "🔒 Закрито"

    await msg.answer(
        "✅ Угоду закрито\n\n"
        f"Пропозиція #{offer_id}\n"
        f"Комісія: {data['commission']}\n"
        f"Клієнт: {data['client_name']}"
    )

    await state.clear()


# ================= MAIN =================
async def main():
    print("BOT STARTED")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
