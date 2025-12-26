import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from openpyxl import Workbook, load_workbook

# =====================================================
# ENV
# =====================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задано")

# =====================================================
# FILES
# =====================================================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# =====================================================
# LABELS (UA)
# =====================================================
FIELD_LABELS = {
    "category": "Категорія",
    "property_type": "Тип житла",
    "street": "Вулиця",
    "city": "Місто",
    "district": "Район",
    "advantages": "Переваги",
    "rent": "Орендна плата",
    "deposit": "Депозит",
    "commission": "Комісія",
    "parking": "Паркінг",
    "move_in": "Заселення від",
    "viewing": "Огляди від",
    "broker": "Маклер",
}

def format_offer_text(data: dict) -> str:
    text = ""
    for key, label in FIELD_LABELS.items():
        if key in data:
            text += f"{label}: {data[key]}\n"
    text += f"\n📸 Фото: {len(data.get('photos', []))}"
    return text

# =====================================================
# EXCEL
# =====================================================
HEADERS = [
    "ID","Дата створення","Категорія","Тип житла","Вулиця","Місто","Район",
    "Переваги","Орендна плата","Депозит","Комісія","Паркінг",
    "Заселення від","Огляди від","Маклер","Кількість фото","Статус",
    "Хто знайшов нерухомість","Хто знайшов клієнта","Дата контракту",
    "Сума провізії","Кількість оплат","Графік оплат",
    "Клієнт","ПМЖ","Контакт"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data: dict) -> int:
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    offer_id = ws.max_row

    ws.append([
        offer_id,
        datetime.now().strftime("%Y-%m-%d"),
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
        len(data.get("photos", [])),
        "Активна",  # 🔴 КЛЮЧОВЕ
        "", "", "", "", "", "", "", "", ""
    ])
    wb.save(EXCEL_FILE)
    return offer_id

def get_active_offers():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    offers = []
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 17).value == "Активна":
            street = ws.cell(r, 5).value
            city = ws.cell(r, 6).value
            offers.append((r, street, city))
    return offers

def set_status(row: int, status: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=17).value = status
    wb.save(EXCEL_FILE)

def write_deal(row: int, values: list):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, val in enumerate(values, start=18):
        ws.cell(row=row, column=i).value = val
    wb.save(EXCEL_FILE)

# =====================================================
# FSM
# =====================================================
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
    summary = State()

class CloseFSM(StatesGroup):
    offer_row = State()
    found_property = State()
    found_client = State()
    contract_date = State()
    commission_sum = State()
    payments_count = State()
    payments_details = State()
    client_name = State()
    residence = State()
    contact = State()

# =====================================================
# KEYBOARDS
# =====================================================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="new_offer")],
        [InlineKeyboardButton(text="📕 Закрити пропозицію / угоду", callback_data="close_offer")]
    ])

def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="Оренда")],
        [InlineKeyboardButton(text="Продаж", callback_data="Продаж")]
    ])

def photos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Готово з фото", callback_data="photos_done")]
    ])

def finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])

def status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="reserve")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="inactive")],
        [InlineKeyboardButton(text="🟢 Закрита угода", callback_data="deal")]
    ])

# =====================================================
# BOT
# =====================================================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("Вітаю 👋\nОберіть дію:", reply_markup=start_kb())

# ===================== CREATE OFFER =====================
@dp.callback_query(F.data == "new_offer")
async def new_offer(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Оберіть категорію:", reply_markup=category_kb())
    await state.set_state(OfferFSM.category)

@dp.callback_query(OfferFSM.category)
async def cat(cb, state):
    await state.update_data(category=cb.data)
    await cb.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)

@dp.message(OfferFSM.property_type)
async def step(msg, state, key="property_type", next_state=OfferFSM.street, q="Вулиця:"):
    await state.update_data(**{key: msg.text})
    await msg.answer(q)
    await state.set_state(next_state)

@dp.message(OfferFSM.street)
async def _(m,s): await step(m,s,"street",OfferFSM.city,"Місто:")
@dp.message(OfferFSM.city)
async def _(m,s): await step(m,s,"city",OfferFSM.district,"Район:")
@dp.message(OfferFSM.district)
async def _(m,s): await step(m,s,"district",OfferFSM.advantages,"Переваги:")
@dp.message(OfferFSM.advantages)
async def _(m,s): await step(m,s,"advantages",OfferFSM.rent,"Орендна плата:")
@dp.message(OfferFSM.rent)
async def _(m,s): await step(m,s,"rent",OfferFSM.deposit,"Депозит:")
@dp.message(OfferFSM.deposit)
async def _(m,s): await step(m,s,"deposit",OfferFSM.commission,"Комісія:")
@dp.message(OfferFSM.commission)
async def _(m,s): await step(m,s,"commission",OfferFSM.parking,"Паркінг:")
@dp.message(OfferFSM.parking)
async def _(m,s): await step(m,s,"parking",OfferFSM.move_in,"Заселення від:")
@dp.message(OfferFSM.move_in)
async def _(m,s): await step(m,s,"move_in",OfferFSM.viewing,"Огляди від:")
@dp.message(OfferFSM.viewing)
async def _(m,s): await step(m,s,"viewing",OfferFSM.broker,"Маклер (@нік):")

@dp.message(OfferFSM.broker)
async def broker(msg, state):
    await state.update_data(broker=msg.text, photos=[])
    await msg.answer("Надішліть фото:", reply_markup=photos_kb())
    await state.set_state(OfferFSM.photos)

@dp.message(OfferFSM.photos, F.photo)
async def photo(msg, state):
    data = await state.get_data()
    photos = data["photos"]
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"📸 Фото додано ({len(photos)})")

@dp.callback_query(F.data == "photos_done")
async def summary(cb, state):
    data = await state.get_data()
    await cb.message.answer("📋 ПРОПОЗИЦІЯ:\n\n"+format_offer_text(data), reply_markup=finish_kb())
    await state.set_state(OfferFSM.summary)

@dp.callback_query(F.data == "publish")
async def publish(cb, state):
    data = await state.get_data()
    offer_id = save_offer(data)
    caption = f"🆕 ПРОПОЗИЦІЯ №{offer_id}\n\n"+format_offer_text(data)
    photos = data["photos"]
    if photos:
        media=[InputMediaPhoto(media=p,caption=caption if i==0 else None) for i,p in enumerate(photos)]
        await bot.send_media_group(GROUP_CHAT_ID, media)
    else:
        await bot.send_message(GROUP_CHAT_ID, caption)
    await cb.message.answer("✅ Пропозицію опубліковано")
    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel(cb, state):
    await state.clear()
    await cb.message.answer("❌ Скасовано")

# ===================== CLOSE OFFER =====================
@dp.callback_query(F.data == "close_offer")
async def close_offer(cb, state):
    offers = get_active_offers()
    if not offers:
        await cb.message.answer("Немає активних пропозицій")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{city}, {street}", callback_data=f"row_{row}")]
        for row, street, city in offers
    ])
    await cb.message.answer("Оберіть пропозицію:", reply_markup=kb)

@dp.callback_query(F.data.startswith("row_"))
async def choose_status(cb, state):
    row = int(cb.data.split("_")[1])
    await state.update_data(offer_row=row)
    await cb.message.answer("Оберіть статус:", reply_markup=status_kb())

@dp.callback_query(F.data in ["reserve","inactive"])
async def simple_status(cb, state):
    row=(await state.get_data())["offer_row"]
    status="Резерв" if cb.data=="reserve" else "Неактуальна"
    set_status(row,status)
    await bot.send_message(GROUP_CHAT_ID,f"{'🟡' if status=='Резерв' else '🔴'} ПРОПОЗИЦІЯ №{row-1} — {status}")
    await state.clear()

@dp.callback_query(F.data=="deal")
async def deal(cb,state):
    await cb.message.answer("Хто знайшов нерухомість?")
    await state.set_state(CloseFSM.found_property)

@dp.message(CloseFSM.found_property)
async def _(m,s): await s.update_data(found_property=m.text); await m.answer("Хто знайшов клієнта?"); await s.set_state(CloseFSM.found_client)
@dp.message(CloseFSM.found_client)
async def _(m,s): await s.update_data(found_client=m.text); await m.answer("Дата контракту:"); await s.set_state(CloseFSM.contract_date)
@dp.message(CloseFSM.contract_date)
async def _(m,s): await s.update_data(contract_date=m.text); await m.answer("Сума провізії:"); await s.set_state(CloseFSM.commission_sum)
@dp.message(CloseFSM.commission_sum)
async def _(m,s): await s.update_data(commission_sum=m.text); await m.answer("Кількість оплат:"); await s.set_state(CloseFSM.payments_count)
@dp.message(CloseFSM.payments_count)
async def _(m,s): await s.update_data(payments_count=m.text); await m.answer("Графік оплат:"); await s.set_state(CloseFSM.payments_details)
@dp.message(CloseFSM.payments_details)
async def _(m,s): await s.update_data(payments_details=m.text); await m.answer("ПІБ клієнта:"); await s.set_state(CloseFSM.client_name)
@dp.message(CloseFSM.client_name)
async def _(m,s): await s.update_data(client_name=m.text); await m.answer("ПМЖ клієнта:"); await s.set_state(CloseFSM.residence)
@dp.message(CloseFSM.residence)
async def _(m,s): await s.update_data(residence=m.text); await m.answer("Контакт клієнта:"); await s.set_state(CloseFSM.contact)
@dp.message(CloseFSM.contact)
async def finish(m,s):
    d=await s.get_data()
    row=d["offer_row"]
    write_deal(row,[d[k] for k in ["found_property","found_client","contract_date","commission_sum","payments_count","payments_details","client_name","residence","contact"]])
    set_status(row,"Закрита угода")
    await bot.send_message(GROUP_CHAT_ID,f"🟢 ПРОПОЗИЦІЯ №{row-1} ЗАКРИТА\nКлієнт: {d['client_name']}\nПровізія: {d['commission_sum']}")
    await m.answer("✅ Угоду закрито")
    await s.clear()

# ===================== MAIN =====================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
