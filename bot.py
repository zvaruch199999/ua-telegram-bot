import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from openpyxl import Workbook, load_workbook

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задано")

# =========================
# FILES
# =========================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# =========================
# EXCEL
# =========================
HEADERS = [
    "ID",
    "Дата створення",
    "Категорія",
    "Тип житла",
    "Вулиця",
    "Місто",
    "Район",
    "Переваги",
    "Орендна плата",
    "Депозит",
    "Комісія",
    "Паркінг",
    "Заселення від",
    "Огляди від",
    "Маклер",
    "Кількість фото",
    "Статус",
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
        "Активна",
    ])

    wb.save(EXCEL_FILE)
    return offer_id

# =========================
# FSM
# =========================
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
    edit_field = State()

# =========================
# KEYBOARDS
# =========================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="new_offer")]
    ])

def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="Оренда")],
        [InlineKeyboardButton(text="Продаж", callback_data="Продаж")],
    ])

def photos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Готово з фото", callback_data="photos_done")]
    ])

def finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish")],
        [InlineKeyboardButton(text="✏️ Змінити пункт", callback_data="edit")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")],
    ])

def edit_kb():
    fields = [
        ("Категорія", "category"),
        ("Тип житла", "property_type"),
        ("Вулиця", "street"),
        ("Місто", "city"),
        ("Район", "district"),
        ("Переваги", "advantages"),
        ("Орендна плата", "rent"),
        ("Депозит", "deposit"),
        ("Комісія", "commission"),
        ("Паркінг", "parking"),
        ("Заселення", "move_in"),
        ("Огляди", "viewing"),
        ("Маклер", "broker"),
    ]
    kb = [[InlineKeyboardButton(text=name, callback_data=f"edit_{field}")]
          for name, field in fields]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_summary")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =========================
# BOT
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# START
# =========================
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("Вітаю 👋\nОберіть дію:", reply_markup=start_kb())

# =========================
# CREATE OFFER
# =========================
@dp.callback_query(F.data == "new_offer")
async def new_offer(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Оберіть категорію:", reply_markup=category_kb())
    await state.set_state(OfferFSM.category)

@dp.callback_query(OfferFSM.category)
async def category(cb: CallbackQuery, state: FSMContext):
    await state.update_data(category=cb.data)
    await cb.message.answer("Вкажіть тип житла:")
    await state.set_state(OfferFSM.property_type)

@dp.message(OfferFSM.property_type)
async def property_type(msg: Message, state: FSMContext):
    await state.update_data(property_type=msg.text)
    await msg.answer("Вкажіть вулицю:")
    await state.set_state(OfferFSM.street)

@dp.message(OfferFSM.street)
async def street(msg: Message, state: FSMContext):
    await state.update_data(street=msg.text)
    await msg.answer("Вкажіть місто:")
    await state.set_state(OfferFSM.city)

@dp.message(OfferFSM.city)
async def city(msg: Message, state: FSMContext):
    await state.update_data(city=msg.text)
    await msg.answer("Вкажіть район:")
    await state.set_state(OfferFSM.district)

@dp.message(OfferFSM.district)
async def district(msg: Message, state: FSMContext):
    await state.update_data(district=msg.text)
    await msg.answer("Опишіть переваги житла:")
    await state.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def advantages(msg: Message, state: FSMContext):
    await state.update_data(advantages=msg.text)
    await msg.answer("Вкажіть орендну плату / ціну:")
    await state.set_state(OfferFSM.rent)

@dp.message(OfferFSM.rent)
async def rent(msg: Message, state: FSMContext):
    await state.update_data(rent=msg.text)
    await msg.answer("Вкажіть депозит:")
    await state.set_state(OfferFSM.deposit)

@dp.message(OfferFSM.deposit)
async def deposit(msg: Message, state: FSMContext):
    await state.update_data(deposit=msg.text)
    await msg.answer("Вкажіть комісію:")
    await state.set_state(OfferFSM.commission)

@dp.message(OfferFSM.commission)
async def commission(msg: Message, state: FSMContext):
    await state.update_data(commission=msg.text)
    await msg.answer("Інформація про паркінг:")
    await state.set_state(OfferFSM.parking)

@dp.message(OfferFSM.parking)
async def parking(msg: Message, state: FSMContext):
    await state.update_data(parking=msg.text)
    await msg.answer("Заселення можливе від:")
    await state.set_state(OfferFSM.move_in)

@dp.message(OfferFSM.move_in)
async def move_in(msg: Message, state: FSMContext):
    await state.update_data(move_in=msg.text)
    await msg.answer("Огляди можливі від:")
    await state.set_state(OfferFSM.viewing)

@dp.message(OfferFSM.viewing)
async def viewing(msg: Message, state: FSMContext):
    await state.update_data(viewing=msg.text)
    await msg.answer("Вкажіть нік маклера:")
    await state.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def broker(msg: Message, state: FSMContext):
    await state.update_data(broker=msg.text, photos=[])
    await msg.answer(
        "Надішліть фото обʼєкта (можна декілька).\nПісля завершення натисніть кнопку 👇",
        reply_markup=photos_kb()
    )
    await state.set_state(OfferFSM.photos)

# =========================
# PHOTOS
# =========================
@dp.message(OfferFSM.photos, F.photo)
async def get_photos(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"📸 Фото додано ({len(photos)})")

@dp.callback_query(F.data == "photos_done")
async def photos_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = "📋 ПЕРЕВІРТЕ ПРОПОЗИЦІЮ:\n\n"
    for k, v in data.items():
        if k != "photos":
            text += f"{k}: {v}\n"
    text += f"\nФото: {len(data.get('photos', []))}"
    await cb.message.answer(text, reply_markup=finish_kb())
    await state.set_state(OfferFSM.summary)

# =========================
# EDIT
# =========================
@dp.callback_query(F.data == "edit")
async def edit(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Оберіть пункт для редагування:", reply_markup=edit_kb())

@dp.callback_query(F.data.startswith("edit_"))
async def choose_edit(cb: CallbackQuery, state: FSMContext):
    field = cb.data.replace("edit_", "")
    await state.update_data(edit_field=field)
    await cb.message.answer("Введіть нове значення:")
    await state.set_state(OfferFSM.edit_field)

@dp.message(OfferFSM.edit_field)
async def apply_edit(msg: Message, state: FSMContext):
    data = await state.get_data()
    field = data["edit_field"]
    await state.update_data({field: msg.text})
    await photos_done(msg, state)

@dp.callback_query(F.data == "back_to_summary")
async def back(cb: CallbackQuery, state: FSMContext):
    await photos_done(cb, state)

# =========================
# PUBLISH
# =========================
@dp.callback_query(F.data == "publish")
async def publish(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = save_offer(data)

    caption = f"🆕 ПРОПОЗИЦІЯ №{offer_id}\n\n"
    for k, v in data.items():
        if k != "photos":
            caption += f"{k}: {v}\n"

    photos = data.get("photos", [])
    if photos:
        media = []
        for i, file_id in enumerate(photos):
            media.append(InputMediaPhoto(
                media=file_id,
                caption=caption if i == 0 else None
            ))
        await bot.send_media_group(GROUP_CHAT_ID, media)
    else:
        await bot.send_message(GROUP_CHAT_ID, caption)

    await cb.message.answer("✅ Пропозицію опубліковано")
    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Створення пропозиції скасовано")

# =========================
# MAIN
# =========================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
