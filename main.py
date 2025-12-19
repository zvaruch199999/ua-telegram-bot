import os
import re
import sqlite3
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage


# =========================
# ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_ID = os.getenv("GROUP_ID", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
APP_TITLE = os.getenv("APP_TITLE", "ORENDA SK").strip()

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
if not GROUP_ID:
    raise RuntimeError("Missing GROUP_ID")

GROUP_ID_INT = int(GROUP_ID)

ADMIN_IDS: List[int] = []
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.append(int(x))


# =========================
# DB
# =========================
DB_PATH = "offers.db"

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            created_by INTEGER,
            created_by_name TEXT,
            category TEXT,
            district TEXT,
            address TEXT,
            price TEXT,
            rooms TEXT,
            area_m2 TEXT,
            floor TEXT,
            deposit TEXT,
            available_from TEXT,
            contact TEXT,
            description TEXT,
            photos TEXT,
            status TEXT,
            group_message_id INTEGER
        )
    """)
    con.commit()
    con.close()

def insert_offer(data: dict) -> int:
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO offers VALUES (
            NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """, (
        datetime.utcnow().isoformat(),
        data["created_by"],
        data["created_by_name"],
        data["category"],
        data["district"],
        data["address"],
        data["price"],
        data.get("rooms"),
        data.get("area_m2"),
        data.get("floor"),
        data.get("deposit"),
        data.get("available_from"),
        data["contact"],
        data.get("description"),
        ",".join(data.get("photos", [])),
        "active",
        None
    ))
    con.commit()
    oid = cur.lastrowid
    con.close()
    return oid

def get_offer(oid: int) -> Optional[dict]:
    con = db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id=?", (oid,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None

def update_offer(oid: int, fields: dict):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [oid]
    con = db()
    cur = con.cursor()
    cur.execute(f"UPDATE offers SET {keys} WHERE id=?", vals)
    con.commit()
    con.close()

def list_offers_by_user(uid: int):
    con = db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE created_by=? ORDER BY id DESC", (uid,))
    rows = cur.fetchall()
    con.close()
    return [dict(r) for r in rows]


# =========================
# UI
# =========================
STATUS_UA = {
    "active": "🟢 АКТИВНА",
    "reserve": "🟡 РЕЗЕРВ",
    "rented": "🔴 ЗДАНА",
}

CATEGORIES = ["Квартира", "Будинок", "Кімната", "Комерція"]

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Пропоную житло", callback_data="offer_new")],
        [InlineKeyboardButton(text="📋 Мої оголошення", callback_data="my_offers")],
        [InlineKeyboardButton(text="ℹ️ Як це працює", callback_data="help")]
    ])

def kb_categories():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"cat:{c}")]
        for c in CATEGORIES
    ])

def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])

def kb_status(oid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢", callback_data=f"st:{oid}:active"),
            InlineKeyboardButton(text="🟡", callback_data=f"st:{oid}:reserve"),
            InlineKeyboardButton(text="🔴", callback_data=f"st:{oid}:rented"),
        ]
    ])

def render(o: dict) -> str:
    return (
        f"🏠 **#{o['id']} {o['category']}**\n"
        f"📍 {o['district']}\n"
        f"📌 {o['address']}\n"
        f"💶 {o['price']}\n"
        f"☎️ {o['contact']}\n\n"
        f"{STATUS_UA.get(o['status'], o['status'])}"
    )


# =========================
# FSM
# =========================
class Flow(StatesGroup):
    category = State()
    district = State()
    address = State()
    price = State()
    contact = State()
    photos = State()
    confirm = State()


# =========================
# BOT
# =========================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(f"👋 Вітаю! **{APP_TITLE}**", reply_markup=kb_main())


@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    await c.message.answer("ℹ️ Бот для публікації оренди житла.", reply_markup=kb_main())
    await c.answer()


@dp.callback_query(F.data == "offer_new")
async def offer_new(c: CallbackQuery, state: FSMContext):
    await state.set_state(Flow.category)
    await c.message.answer("🏷 Обери тип:", reply_markup=kb_categories())
    await c.answer()


@dp.callback_query(Flow.category, F.data.startswith("cat:"))
async def cat(c: CallbackQuery, state: FSMContext):
    await state.update_data(category=c.data.split(":")[1])
    await state.set_state(Flow.district)
    await c.message.answer("📍 Район:")
    await c.answer()


@dp.message(Flow.district)
async def district(m: Message, state: FSMContext):
    await state.update_data(district=m.text)
    await state.set_state(Flow.address)
    await m.answer("📌 Адреса:")


@dp.message(Flow.address)
async def address(m: Message, state: FSMContext):
    await state.update_data(address=m.text)
    await state.set_state(Flow.price)
    await m.answer("💶 Ціна:")


@dp.message(Flow.price)
async def price(m: Message, state: FSMContext):
    await state.update_data(price=m.text)
    await state.set_state(Flow.contact)
    await m.answer("☎️ Контакт:")


@dp.message(Flow.contact)
async def contact(m: Message, state: FSMContext):
    await state.update_data(contact=m.text, photos=[])
    await state.set_state(Flow.photos)
    await m.answer("📸 Надішли фото або напиши 'готово'")


@dp.message(Flow.photos, F.photo)
async def photos(m: Message, state: FSMContext):
    data = await state.get_data()
    data["photos"].append(m.photo[-1].file_id)
    await state.update_data(photos=data["photos"])


@dp.message(Flow.photos, F.text.casefold() == "готово")
async def photos_done(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Flow.confirm)
    preview = {
        "id": 0,
        "status": "active",
        **data
    }
    await m.answer(render(preview), reply_markup=kb_confirm())


@dp.callback_query(Flow.confirm, F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("❌ Скасовано.", reply_markup=kb_main())
    await c.answer()


@dp.callback_query(Flow.confirm, F.data == "publish")
async def publish(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["created_by"] = c.from_user.id
    data["created_by_name"] = c.from_user.full_name

    oid = insert_offer(data)
    offer = get_offer(oid)

    if offer["photos"]:
        await bot.send_photo(
            GROUP_ID_INT,
            offer["photos"].split(",")[0],
            caption=render(offer),
            reply_markup=kb_status(oid)
        )
    else:
        await bot.send_message(
            GROUP_ID_INT,
            render(offer),
            reply_markup=kb_status(oid)
        )

    await state.clear()
    await c.message.answer("✅ Опубліковано!", reply_markup=kb_main())
    await c.answer()


@dp.callback_query(F.data.startswith("st:"))
async def change_status(c: CallbackQuery):
    _, oid, st = c.data.split(":")
    update_offer(int(oid), {"status": st})
    offer = get_offer(int(oid))
    await c.message.edit_text(render(offer), reply_markup=kb_status(int(oid)))
    await c.answer(STATUS_UA[st])


# =========================
# RUN
# =========================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
