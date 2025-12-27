import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InputMediaPhoto,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= FSM =================

class OfferFSM(StatesGroup):
    category = State()
    property_type = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewing = State()
    broker = State()
    photos = State()

# ================= KEYBOARD =================

def status_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 Актуально", callback_data="status:active"),
                InlineKeyboardButton(text="🟡 Резерв", callback_data="status:reserved"),
                InlineKeyboardButton(text="🔴 Неактуально", callback_data="status:inactive"),
            ]
        ]
    )

# ================= START / CANCEL =================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вітаю 👋\n\n"
        "Напишіть:\n"
        "👉 `створити` — створити пропозицію\n\n"
        "`/cancel` — скасувати дію"
    )

@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Дію скасовано. Напишіть /start")

# ================= CREATE FLOW =================

@dp.message(F.text.lower() == "створити")
async def create(message: Message, state: FSMContext):
    await state.set_state(OfferFSM.category)
    await message.answer("Категорія (Оренда / Продаж):")

@dp.message(OfferFSM.category)
async def s1(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(OfferFSM.property_type)
    await message.answer("Тип житла:")

@dp.message(OfferFSM.property_type)
async def s2(message: Message, state: FSMContext):
    await state.update_data(property_type=message.text)
    await state.set_state(OfferFSM.street)
    await message.answer("Вулиця:")

@dp.message(OfferFSM.street)
async def s3(message: Message, state: FSMContext):
    await state.update_data(street=message.text)
    await state.set_state(OfferFSM.city)
    await message.answer("Місто:")

@dp.message(OfferFSM.city)
async def s4(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(OfferFSM.district)
    await message.answer("Район:")

@dp.message(OfferFSM.district)
async def s5(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await state.set_state(OfferFSM.advantages)
    await message.answer("Переваги житла:")

@dp.message(OfferFSM.advantages)
async def s6(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text)
    await state.set_state(OfferFSM.rent)
    await message.answer("Ціна:")

@dp.message(OfferFSM.rent)
async def s7(message: Message, state: FSMContext):
    await state.update_data(rent=message.text)
    await state.set_state(OfferFSM.deposit)
    await message.answer("Депозит:")

@dp.message(OfferFSM.deposit)
async def s8(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text)
    await state.set_state(OfferFSM.commission)
    await message.answer("Комісія:")

@dp.message(OfferFSM.commission)
async def s9(message: Message, state: FSMContext):
    await state.update_data(commission=message.text)
    await state.set_state(OfferFSM.parking)
    await message.answer("Паркінг:")

@dp.message(OfferFSM.parking)
async def s10(message: Message, state: FSMContext):
    await state.update_data(parking=message.text)
    await state.set_state(OfferFSM.move_in)
    await message.answer("Заселення від:")

@dp.message(OfferFSM.move_in)
async def s11(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text)
    await state.set_state(OfferFSM.viewing)
    await message.answer("Огляди від:")

@dp.message(OfferFSM.viewing)
async def s12(message: Message, state: FSMContext):
    await state.update_data(viewing=message.text)
    await state.set_state(OfferFSM.broker)
    await message.answer("Маклер (нік):")

@dp.message(OfferFSM.broker)
async def s13(message: Message, state: FSMContext):
    await state.update_data(broker=message.text, photos=[])
    await state.set_state(OfferFSM.photos)
    await message.answer(
        "📸 Надішліть фото.\n"
        "Коли закінчите — напишіть команду:\n\n"
        "`/done`"
    )

# ================= PHOTOS =================

@dp.message(OfferFSM.photos, F.photo)
async def collect_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"📷 Фото додано ({len(photos)})")

# ================= DONE =================

@dp.message(Command("done"))
async def finish(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    text = (
        "🏠 НОВА ПРОПОЗИЦІЯ\n"
        "Статус: 🟢 Актуально\n\n"
        f"Категорія: {data['category']}\n"
        f"Тип: {data['property_type']}\n"
        f"Адреса: {data['street']}, {data['city']}\n"
        f"Район: {data['district']}\n"
        f"Переваги: {data['advantages']}\n"
        f"Ціна: {data['rent']}\n"
        f"Депозит: {data['deposit']}\n"
        f"Комісія: {data['commission']}\n"
        f"Паркінг: {data['parking']}\n"
        f"Заселення: {data['move_in']}\n"
        f"Огляди: {data['viewing']}\n"
        f"Маклер: {data['broker']}"
    )

    # 🔍 PREVIEW IN BOT
    if photos:
        preview = [InputMediaPhoto(media=photos[0], caption=text)]
        for p in photos[1:]:
            preview.append(InputMediaPhoto(media=p))
        await message.answer_media_group(preview)
    else:
        await message.answer(text)

    await message.answer("👆 Це фінальний вигляд пропозиції")

    # 📢 POST TO GROUP
    if photos:
        media = [InputMediaPhoto(media=photos[0], caption=text)]
        for p in photos[1:]:
            media.append(InputMediaPhoto(media=p))

        msgs = await bot.send_media_group(GROUP_CHAT_ID, media)
        await bot.send_message(
            GROUP_CHAT_ID,
            "⬇️ Змінити статус:",
            reply_markup=status_keyboard(),
            reply_to_message_id=msgs[0].message_id,
        )
    else:
        await bot.send_message(
            GROUP_CHAT_ID,
            text,
            reply_markup=status_keyboard(),
        )

    await message.answer("✅ Пропозицію опубліковано в групу")
    await state.clear()

# ================= STATUS CHANGE =================

@dp.callback_query(F.data.startswith("status:"))
async def change_status(callback: CallbackQuery):
    status_map = {
        "active": "🟢 Актуально",
        "reserved": "🟡 Резервовано",
        "inactive": "🔴 Неактуально",
    }

    new_status = status_map[callback.data.split(":")[1]]
    msg = callback.message

    if msg.reply_to_message:
        original = msg.reply_to_message
        text = original.caption
        lines = text.splitlines()
        lines[1] = f"Статус: {new_status}"
        await original.edit_caption("\n".join(lines))
    else:
        lines = msg.text.splitlines()
        lines[1] = f"Статус: {new_status}"
        await msg.edit_text("\n".join(lines), reply_markup=status_keyboard())

    await callback.answer(f"Статус змінено: {new_status}")

# ================= RUN =================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
