import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from openpyxl import Workbook, load_workbook

# ================= ENV (SAFE) =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не заданий")

GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW) if GROUP_CHAT_ID_RAW else None

# ================= FILES =================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ================= EXCEL =================
HEADERS = [
    "ID","Дата","Категорія","Тип житла","Вулиця","Місто","Район","Переваги",
    "Ціна","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер",
    "Фото_IDs","Статус"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data: dict):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.append([
        ws.max_row,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"], data["property_type"],
        data["street"], data["city"], data["district"],
        data["advantages"], data["rent"], data["deposit"],
        data["commission"], data["parking"],
        data["move_in"], data["viewing"], data["broker"],
        ",".join(data["photos"]),
        "Активна"
    ])
    wb.save(EXCEL_FILE)

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

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= START =================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Оренда", callback_data="cat_rent"),
            InlineKeyboardButton(text="Продаж", callback_data="cat_sale")
        ]
    ])
    await message.answer("Вітаю 👋\nОберіть категорію:", reply_markup=kb)
    await state.set_state(OfferFSM.category)

# ================= CATEGORY BUTTON =================
@dp.callback_query(F.data.startswith("cat_"))
async def category_button(call: CallbackQuery, state: FSMContext):
    category = "Оренда" if call.data == "cat_rent" else "Продаж"
    await state.update_data(category=category)
    await call.message.edit_reply_markup(None)
    await call.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)
    await call.answer()

# ================= CATEGORY TEXT =================
@dp.message(OfferFSM.category)
async def category_text(message: Message, state: FSMContext):
    text = message.text.lower()
    if "оренд" in text:
        category = "Оренда"
    elif "прод" in text:
        category = "Продаж"
    else:
        await message.answer("Напишіть `Оренда` або `Продаж`")
        return

    await state.update_data(category=category)
    await message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)

# ================= FLOW =================
@dp.message(OfferFSM.property_type)
async def step_property_type(message: Message, state: FSMContext):
    await state.update_data(property_type=message.text)
    await message.answer("Вулиця:")
    await state.set_state(OfferFSM.street)

@dp.message(OfferFSM.street)
async def step_street(message: Message, state: FSMContext):
    await state.update_data(street=message.text)
    await message.answer("Місто:")
    await state.set_state(OfferFSM.city)

@dp.message(OfferFSM.city)
async def step_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Район:")
    await state.set_state(OfferFSM.district)

@dp.message(OfferFSM.district)
async def step_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await message.answer("Переваги житла:")
    await state.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def step_advantages(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text)
    await message.answer("Ціна:")
    await state.set_state(OfferFSM.rent)

@dp.message(OfferFSM.rent)
async def step_rent(message: Message, state: FSMContext):
    await state.update_data(rent=message.text)
    await message.answer("Депозит:")
    await state.set_state(OfferFSM.deposit)

@dp.message(OfferFSM.deposit)
async def step_deposit(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text)
    await message.answer("Комісія:")
    await state.set_state(OfferFSM.commission)

@dp.message(OfferFSM.commission)
async def step_commission(message: Message, state: FSMContext):
    await state.update_data(commission=message.text)
    await message.answer("Паркінг:")
    await state.set_state(OfferFSM.parking)

@dp.message(OfferFSM.parking)
async def step_parking(message: Message, state: FSMContext):
    await state.update_data(parking=message.text)
    await message.answer("Заселення від:")
    await state.set_state(OfferFSM.move_in)

@dp.message(OfferFSM.move_in)
async def step_move_in(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text)
    await message.answer("Огляди від:")
    await state.set_state(OfferFSM.viewing)

@dp.message(OfferFSM.viewing)
async def step_viewing(message: Message, state: FSMContext):
    await state.update_data(viewing=message.text)
    await message.answer("Маклер (нік):")
    await state.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def step_broker(message: Message, state: FSMContext):
    await state.update_data(broker=message.text, photos=[])
    await message.answer("Надішліть фото. Коли готово — напишіть будь-який текст.")
    await state.set_state(OfferFSM.photos)

@dp.message(OfferFSM.photos, F.photo)
async def step_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    data["photos"].append(message.photo[-1].file_id)
    await state.update_data(photos=data["photos"])
    await message.answer("Фото додано.")

@dp.message(OfferFSM.photos)
async def finish(message: Message, state: FSMContext):
    data = await state.get_data()
    save_offer(data)

    if GROUP_CHAT_ID:
        media = [
            InputMediaPhoto(p, caption="🏠 Нова пропозиція" if i == 0 else None)
            for i, p in enumerate(data["photos"])
        ]
        await bot.send_media_group(GROUP_CHAT_ID, media)

    await message.answer("✅ Пропозицію створено.\nНапишіть /start для нової.")
    await state.clear()

# ================= MAIN =================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
