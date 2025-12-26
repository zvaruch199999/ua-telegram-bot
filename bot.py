import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    InputMediaPhoto
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from openpyxl import Workbook, load_workbook

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# ================= FILES =================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ================= EXCEL =================
HEADERS = [
    "ID","Дата","Категорія","Тип житла","Вулиця","Місто","Район","Переваги",
    "Ціна","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер",
    "К-сть фото","Фото_IDs","Статус",
    "Хто знайшов нерухомість","Хто знайшов клієнта","Дата контракту",
    "Сума провізії","К-сть оплат","Графік оплат",
    "Клієнт","ПМЖ","Контакт"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    row = ws.max_row
    ws.append([
        row,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"], data["property_type"],
        data["street"], data["city"], data["district"],
        data["advantages"], data["rent"], data["deposit"],
        data["commission"], data["parking"],
        data["move_in"], data["viewing"], data["broker"],
        len(data["photos"]),
        ",".join(data["photos"]),
        "Активна",
        "", "", "", "", "", "", "", "", ""
    ])
    wb.save(EXCEL_FILE)
    return row

def get_offer(row):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    return {
        "property_type": ws.cell(row,4).value,
        "street": ws.cell(row,5).value,
        "city": ws.cell(row,6).value,
        "rent": ws.cell(row,9).value,
        "broker": ws.cell(row,15).value,
        "photos": ws.cell(row,17).value.split(",")
    }

def update_status(row, status):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=18).value = status
    wb.save(EXCEL_FILE)

def write_deal(row, values):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, v in enumerate(values, start=19):
        ws.cell(row=row, column=i).value = v
    wb.save(EXCEL_FILE)

def get_active_rows():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    return [r for r in range(2, ws.max_row + 1) if ws.cell(r,18).value == "Активна"]

# ================= TEXT =================
def offer_text(o, status=None):
    base = (
        f"🏠 {o['property_type']}\n"
        f"📍 {o['city']}, {o['street']}\n"
        f"💰 Ціна: {o['rent']}\n"
        f"🧑‍💼 Маклер: {o['broker']}"
    )
    return f"{status}\n\n{base}" if status else base

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
    row = State()
    found_property = State()
    found_client = State()
    contract_date = State()
    commission_sum = State()
    payments_count = State()
    payments_details = State()
    client_name = State()
    residence = State()
    contact = State()
    summary = State()

# ================= KEYBOARDS =================
def reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Створити пропозицію")],
            [KeyboardButton(text="📕 Закрити пропозицію / угоду")]
        ],
        resize_keyboard=True
    )

def status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="reserve")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="inactive")],
        [InlineKeyboardButton(text="🟢 Закрита угода", callback_data="deal")]
    ])

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Чудово, зберегти", callback_data="deal_ok")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="deal_cancel")]
    ])

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ===== START (ЗАХИСТ) =====
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вітаю 👋\n⚠️ Поточну дію скасовано.\nОберіть дію:",
        reply_markup=reply_menu()
    )

# ===== REPLY BUTTONS (БЕЗ ЛАМАННЯ FSM) =====
@dp.message(F.text == "➕ Створити пропозицію")
async def reply_new(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        await message.answer("⚠️ Завершіть або скасуйте поточну дію.")
        return
    await message.answer("Категорія:")
    await state.set_state(OfferFSM.category)

@dp.message(F.text == "📕 Закрити пропозицію / угоду")
async def reply_close(message: Message, state: FSMContext):
    if await state.get_state() is not None:
        await message.answer("⚠️ Завершіть або скасуйте поточну дію.")
        return
    rows = get_active_rows()
    if not rows:
        await message.answer("Немає активних пропозицій")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Пропозиція {r}", callback_data=f"row_{r}")]
        for r in rows
    ])
    await message.answer("Оберіть пропозицію:", reply_markup=kb)

# ===== CREATE OFFER FSM =====
@dp.message(OfferFSM.category)
async def s1(m,s): await s.update_data(category=m.text); await m.answer("Тип житла:"); await s.set_state(OfferFSM.property_type)
@dp.message(OfferFSM.property_type)
async def s2(m,s): await s.update_data(property_type=m.text); await m.answer("Вулиця:"); await s.set_state(OfferFSM.street)
@dp.message(OfferFSM.street)
async def s3(m,s): await s.update_data(street=m.text); await m.answer("Місто:"); await s.set_state(OfferFSM.city)
@dp.message(OfferFSM.city)
async def s4(m,s): await s.update_data(city=m.text); await m.answer("Район:"); await s.set_state(OfferFSM.district)
@dp.message(OfferFSM.district)
async def s5(m,s): await s.update_data(district=m.text); await m.answer("Переваги:"); await s.set_state(OfferFSM.advantages)
@dp.message(OfferFSM.advantages)
async def s6(m,s): await s.update_data(advantages=m.text); await m.answer("Ціна:"); await s.set_state(OfferFSM.rent)
@dp.message(OfferFSM.rent)
async def s7(m,s): await s.update_data(rent=m.text); await m.answer("Депозит:"); await s.set_state(OfferFSM.deposit)
@dp.message(OfferFSM.deposit)
async def s8(m,s): await s.update_data(deposit=m.text); await m.answer("Комісія:"); await s.set_state(OfferFSM.commission)
@dp.message(OfferFSM.commission)
async def s9(m,s): await s.update_data(commission=m.text); await m.answer("Паркінг:"); await s.set_state(OfferFSM.parking)
@dp.message(OfferFSM.parking)
async def s10(m,s): await s.update_data(parking=m.text); await m.answer("Заселення від:"); await s.set_state(OfferFSM.move_in)
@dp.message(OfferFSM.move_in)
async def s11(m,s): await s.update_data(move_in=m.text); await m.answer("Огляди від:"); await s.set_state(OfferFSM.viewing)
@dp.message(OfferFSM.viewing)
async def s12(m,s): await s.update_data(viewing=m.text); await m.answer("Маклер:"); await s.set_state(OfferFSM.broker)
@dp.message(OfferFSM.broker)
async def s13(m,s): await s.update_data(broker=m.text, photos=[]); await m.answer("Надішліть фото:"); await s.set_state(OfferFSM.photos)
@dp.message(OfferFSM.photos, F.photo)
async def s14(m,s):
    d=await s.get_data()
    d["photos"].append(m.photo[-1].file_id)
    await s.update_data(photos=d["photos"])
    await m.answer("Фото додано. Напишіть будь-що для завершення.")
@dp.message(OfferFSM.photos)
async def s15(m,s):
    data=await s.get_data()
    save_offer(data)
    media=[InputMediaPhoto(p, caption=offer_text(data) if i==0 else None) for i,p in enumerate(data["photos"])]
    await bot.send_media_group(GROUP_CHAT_ID, media)
    await m.answer("✅ Пропозицію опубліковано", reply_markup=reply_menu())
    await s.clear()

# ================= MAIN =================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
