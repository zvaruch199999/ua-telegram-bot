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

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий")

# ================= FILES =================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ================= EXCEL =================
HEADERS = [
    "ID", "Дата", "Категорія", "Тип житла", "Вулиця", "Місто", "Район",
    "Переваги", "Ціна", "Депозит", "Комісія", "Паркінг",
    "Заселення", "Огляди", "Маклер",
    "Фото_IDs", "Статус", "GroupMessageID"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def load_ws():
    wb = load_workbook(EXCEL_FILE)
    return wb, wb.active

def save_offer(data, group_msg_id):
    wb, ws = load_ws()
    ws.append([
        ws.max_row,
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        data["category"],
        data["property_type"],
        data["street"],
        data["city"],
        data["district"],
        data["advantages"],
        data["rent"],
        data["deposit"],
        data["commission"],
        data["parking"],
        data["move_in"],
        data["viewing"],
        data["broker"],
        ",".join(data["photos"]),
        "Активна",
        group_msg_id
    ])
    wb.save(EXCEL_FILE)

def get_active_offers():
    wb, ws = load_ws()
    offers = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[16] == "Активна":
            offers.append(row)
    return offers

def update_status(offer_id, new_status):
    wb, ws = load_ws()
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 1).value == offer_id:
            ws.cell(r, 17).value = new_status
            wb.save(EXCEL_FILE)
            return ws.cell(r, 18).value
    return None

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

class CloseFSM(StatesGroup):
    choose_offer = State()
    choose_status = State()

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= START =================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="create")],
        [InlineKeyboardButton(text="📕 Закрити пропозицію", callback_data="close")]
    ])
    await message.answer("Вітаю 👋\nОберіть дію:", reply_markup=kb)

# ================= CREATE =================
@dp.callback_query(F.data == "create")
async def create(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Оренда", callback_data="rent"),
            InlineKeyboardButton(text="Продаж", callback_data="sale")
        ]
    ])
    await call.message.answer("Категорія:", reply_markup=kb)
    await state.set_state(OfferFSM.category)
    await call.answer()

@dp.callback_query(F.data.in_(["rent", "sale"]), OfferFSM.category)
async def set_category(call: CallbackQuery, state: FSMContext):
    await state.update_data(category="Оренда" if call.data == "rent" else "Продаж")
    await call.message.edit_reply_markup(None)
    await call.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)
    await call.answer()

def step(next_state, text):
    async def handler(message: Message, state: FSMContext):
        await state.update_data(**{next_state.split(".")[1]: message.text})
        await message.answer(text)
        await state.set_state(getattr(OfferFSM, next_state.split(".")[1]))
    return handler

@dp.message(OfferFSM.property_type)
async def _(m: Message, s: FSMContext):
    await s.update_data(property_type=m.text)
    await m.answer("Вулиця:")
    await s.set_state(OfferFSM.street)

@dp.message(OfferFSM.street)
async def _(m: Message, s: FSMContext):
    await s.update_data(street=m.text)
    await m.answer("Місто:")
    await s.set_state(OfferFSM.city)

@dp.message(OfferFSM.city)
async def _(m: Message, s: FSMContext):
    await s.update_data(city=m.text)
    await m.answer("Район:")
    await s.set_state(OfferFSM.district)

@dp.message(OfferFSM.district)
async def _(m: Message, s: FSMContext):
    await s.update_data(district=m.text)
    await m.answer("Переваги:")
    await s.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def _(m: Message, s: FSMContext):
    await s.update_data(advantages=m.text)
    await m.answer("Ціна:")
    await s.set_state(OfferFSM.rent)

@dp.message(OfferFSM.rent)
async def _(m: Message, s: FSMContext):
    await s.update_data(rent=m.text)
    await m.answer("Депозит:")
    await s.set_state(OfferFSM.deposit)

@dp.message(OfferFSM.deposit)
async def _(m: Message, s: FSMContext):
    await s.update_data(deposit=m.text)
    await m.answer("Комісія:")
    await s.set_state(OfferFSM.commission)

@dp.message(OfferFSM.commission)
async def _(m: Message, s: FSMContext):
    await s.update_data(commission=m.text)
    await m.answer("Паркінг:")
    await s.set_state(OfferFSM.parking)

@dp.message(OfferFSM.parking)
async def _(m: Message, s: FSMContext):
    await s.update_data(parking=m.text)
    await m.answer("Заселення від:")
    await s.set_state(OfferFSM.move_in)

@dp.message(OfferFSM.move_in)
async def _(m: Message, s: FSMContext):
    await s.update_data(move_in=m.text)
    await m.answer("Огляди від:")
    await s.set_state(OfferFSM.viewing)

@dp.message(OfferFSM.viewing)
async def _(m: Message, s: FSMContext):
    await s.update_data(viewing=m.text)
    await m.answer("Маклер:")
    await s.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def _(m: Message, s: FSMContext):
    await s.update_data(broker=m.text, photos=[])
    await m.answer("Надішліть фото.")
    await s.set_state(OfferFSM.photos)

@dp.message(OfferFSM.photos, F.photo)
async def add_photo(m: Message, s: FSMContext):
    data = await s.get_data()
    data["photos"].append(m.photo[-1].file_id)
    await s.update_data(photos=data["photos"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="finish")]
    ])
    await m.answer("Фото додано.", reply_markup=kb)

@dp.callback_query(F.data == "finish")
async def finish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    media = [InputMediaPhoto(p) for p in data["photos"]]
    sent = await bot.send_media_group(GROUP_CHAT_ID, media)
    save_offer(data, sent[0].message_id)
    await call.message.answer("✅ Пропозицію створено")
    await state.clear()
    await call.answer()

# ================= CLOSE =================
@dp.callback_query(F.data == "close")
async def close(call: CallbackQuery, state: FSMContext):
    offers = get_active_offers()
    if not offers:
        await call.message.answer("Немає активних пропозицій")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{o[0]} {o[3]} {o[4]}", callback_data=f"off_{o[0]}")]
            for o in offers
        ]
    )
    await call.message.answer("Оберіть пропозицію:", reply_markup=kb)
    await state.set_state(CloseFSM.choose_offer)
    await call.answer()

@dp.callback_query(F.data.startswith("off_"), CloseFSM.choose_offer)
async def choose_status(call: CallbackQuery, state: FSMContext):
    offer_id = int(call.data.split("_")[1])
    await state.update_data(offer_id=offer_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="status_reserve")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="status_closed")]
    ])
    await call.message.answer("Оберіть статус:", reply_markup=kb)
    await state.set_state(CloseFSM.choose_status)
    await call.answer()

@dp.callback_query(F.data.startswith("status_"), CloseFSM.choose_status)
async def set_status(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    new_status = "Резерв" if call.data.endswith("reserve") else "Неактуальна"
    msg_id = update_status(data["offer_id"], new_status)

    if msg_id:
        await bot.send_message(
            GROUP_CHAT_ID,
            f"📌 Пропозиція #{data['offer_id']} — {new_status}",
            reply_to_message_id=msg_id
        )

    await call.message.answer("✅ Статус оновлено")
    await state.clear()
    await call.answer()

# ================= MAIN =================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
