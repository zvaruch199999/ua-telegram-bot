# bot.py
# ORANDA SK — Real Estate Telegram Bot (single-file version)
#
# ✅ Aiogram 3.7+ compatible (no parse_mode in Bot init)
# ✅ Wizard to create offer + photos with ✅ Готово button
# ✅ Preview in bot (album + text with buttons)
# ✅ Publish to group as album + separate text message with status buttons
# ✅ Statuses: 🟢 Актуально / 🟡 Резерв / ⚫️ Знято / ✅ Угода закрита
# ❌ Removed: "Чернетка", "Withdraw", "Неактуально"
# ✅ Edit offer by numbered fields
# ✅ Stats day/month/year:
#    - counts of status events (how many times statuses were set in period)
#    - per broker counts for each status in period
#
# ENV required (Railway Variables):
#   BOT_TOKEN=...
#   GROUP_CHAT_ID=-100xxxxxxxxxx   (your group/chat id)
#
# Notes:
# - Bot must be admin in the group to edit the status message.
# - Telegram albums: buttons cannot be attached to the album itself,
#   so we send album first, then a text message with inline buttons.

import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


# ----------------------------
# Config
# ----------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_CHAT_ID_RAW = (os.getenv("GROUP_CHAT_ID") or os.getenv("GROUP_ID") or "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий (Railway -> Variables)")

if not GROUP_CHAT_ID_RAW:
    raise RuntimeError("GROUP_CHAT_ID не заданий (Railway -> Variables)")

try:
    GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)
except ValueError:
    raise RuntimeError("GROUP_CHAT_ID має бути числом, напр. -1001234567890")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "bot.db")

TZ_NAME = os.getenv("TZ", "Europe/Bratislava")
APP_TZ = ZoneInfo(TZ_NAME) if ZoneInfo else timezone.utc


# ----------------------------
# Statuses (only allowed)
# ----------------------------

STATUS_ACTIVE = "active"
STATUS_RESERVED = "reserved"
STATUS_REMOVED = "removed"
STATUS_CLOSED = "closed"

STATUS_LABEL = {
    STATUS_ACTIVE: "🟢 Актуально",
    STATUS_RESERVED: "🟡 Резерв",
    STATUS_REMOVED: "⚫️ Знято",
    STATUS_CLOSED: "✅ Угода закрита",
}

STATUS_EMOJI = {
    STATUS_ACTIVE: "🟢",
    STATUS_RESERVED: "🟡",
    STATUS_REMOVED: "⚫️",
    STATUS_CLOSED: "✅",
}

ALLOWED_STATUSES = [STATUS_ACTIVE, STATUS_RESERVED, STATUS_REMOVED, STATUS_CLOSED]


# ----------------------------
# DB helpers (sqlite3)
# ----------------------------

def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seq INTEGER UNIQUE,
            creator_id INTEGER,
            creator_username TEXT,
            category TEXT,
            living TEXT,
            housing_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            rent TEXT,
            deposit TEXT,
            commission TEXT,
            parking TEXT,
            move_in_from TEXT,
            viewings_from TEXT,
            broker_username TEXT,
            photos_json TEXT DEFAULT '[]',
            created_at TEXT,
            current_status TEXT,
            published_chat_id INTEGER,
            published_message_id INTEGER
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER,
            status TEXT,
            user_id INTEGER,
            username TEXT,
            at TEXT
        );
        """
    )

    con.commit()
    con.close()


def now_iso() -> str:
    return datetime.now(tz=APP_TZ).isoformat(timespec="seconds")


def next_seq() -> int:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM offers;")
    val = int(cur.fetchone()[0])
    con.close()
    return val


def create_offer(creator_id: int, creator_username: str) -> int:
    con = db()
    cur = con.cursor()
    seq = next_seq()
    cur.execute(
        """
        INSERT INTO offers (
            seq, creator_id, creator_username, created_at,
            category, living, housing_type, street, city, district,
            advantages, rent, deposit, commission, parking,
            move_in_from, viewings_from, broker_username,
            photos_json, current_status, published_chat_id, published_message_id
        ) VALUES (
            ?, ?, ?, ?,
            '', '', '', '', '', '',
            '', '', '', '', '',
            '', '', ?,
            '[]', '', NULL, NULL
        );
        """,
        (seq, creator_id, creator_username, now_iso(), creator_username),
    )
    offer_id = int(cur.lastrowid)
    con.commit()
    con.close()
    return offer_id


def get_offer(offer_id: int) -> sqlite3.Row:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id = ?;", (offer_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        raise ValueError("Offer not found")
    return row


def update_offer(offer_id: int, **fields: Any) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    values = [fields[k] for k in keys]
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    con = db()
    cur = con.cursor()
    cur.execute(f"UPDATE offers SET {set_clause} WHERE id = ?;", (*values, offer_id))
    con.commit()
    con.close()


def add_photo(offer_id: int, file_id: str) -> int:
    row = get_offer(offer_id)
    photos = json.loads(row["photos_json"] or "[]")
    photos.append(file_id)
    update_offer(offer_id, photos_json=json.dumps(photos, ensure_ascii=False))
    return len(photos)


def set_published(offer_id: int, chat_id: int, message_id: int) -> None:
    update_offer(offer_id, published_chat_id=chat_id, published_message_id=message_id)


def log_status_event(offer_id: int, status: str, user: types.User) -> None:
    username = user.username or f"id{user.id}"
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO status_events (offer_id, status, user_id, username, at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (offer_id, status, user.id, username, now_iso()),
    )
    con.commit()
    con.close()


def set_status(offer_id: int, status: str, user: types.User) -> None:
    if status not in ALLOWED_STATUSES:
        return
    update_offer(offer_id, current_status=status)
    log_status_event(offer_id, status, user)


# ----------------------------
# Formatting
# ----------------------------

def fmt_seq(seq: int) -> str:
    return f"#{seq:04d}"


def clean_value(v: str) -> str:
    v = (v or "").strip()
    return v if v else "—"


def offer_text(row: sqlite3.Row, include_status: bool = True) -> str:
    seq = fmt_seq(int(row["seq"]))
    lines = [f"🏡 <b>ПРОПОЗИЦІЯ {seq}</b>"]

    status = (row["current_status"] or "").strip()
    if include_status and status in STATUS_LABEL:
        lines.append(f"📊 <b>Статус:</b> {STATUS_LABEL[status]}")
        lines.append("")

    # Fields with emojis
    lines += [
        f"🏷️ <b>Категорія:</b> {clean_value(row['category'])}",
        f"🏠 <b>Тип житла:</b> {clean_value(row['housing_type'])}",
        f"🏡 <b>Проживання:</b> {clean_value(row['living'])}",
        f"📍 <b>Вулиця:</b> {clean_value(row['street'])}",
        f"🏙️ <b>Місто:</b> {clean_value(row['city'])}",
        f"🗺️ <b>Район:</b> {clean_value(row['district'])}",
        f"✨ <b>Переваги:</b> {clean_value(row['advantages'])}",
        f"💶 <b>Оренда:</b> {clean_value(row['rent'])}",
        f"🔐 <b>Депозит:</b> {clean_value(row['deposit'])}",
        f"🤝 <b>Комісія:</b> {clean_value(row['commission'])}",
        f"🚗 <b>Паркінг:</b> {clean_value(row['parking'])}",
        f"📦 <b>Заселення від:</b> {clean_value(row['move_in_from'])}",
        f"👀 <b>Огляди від:</b> {clean_value(row['viewings_from'])}",
        f"🧑‍💼 <b>Маклер:</b> @{clean_value(row['broker_username']).lstrip('@')}",
    ]
    return "\n".join(lines)


def status_keyboard(offer_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Актуально", callback_data=f"st:{offer_id}:{STATUS_ACTIVE}")
    kb.button(text="🟡 Резерв", callback_data=f"st:{offer_id}:{STATUS_RESERVED}")
    kb.button(text="⚫️ Знято", callback_data=f"st:{offer_id}:{STATUS_REMOVED}")
    kb.button(text="✅ Угода закрита", callback_data=f"st:{offer_id}:{STATUS_CLOSED}")
    kb.adjust(2, 2)
    return kb.as_markup()


def kb_category() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Оренда", callback_data="cat:Оренда")
    kb.button(text="Продаж", callback_data="cat:Продаж")
    kb.adjust(2)
    return kb.as_markup()


HOUSING_TYPES = ["Кімната", "1-кімн.", "2-кімн.", "3-кімн.", "Будинок", "Студія"]


def kb_housing_type() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in HOUSING_TYPES:
        kb.button(text=t, callback_data=f"type:{t}")
    kb.button(text="Інше…", callback_data="type:__other__")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def kb_photos_done() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Готово", callback_data="photos:done")
    return kb.as_markup()


def kb_preview_actions(offer_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Публікувати", callback_data=f"pub:{offer_id}")
    kb.button(text="✏️ Редагувати", callback_data=f"edit:{offer_id}")
    kb.button(text="❌ Скасувати", callback_data=f"cancel:{offer_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


def safe_html(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ----------------------------
# FSM States
# ----------------------------

class NewOffer(StatesGroup):
    category = State()
    housing_type = State()
    housing_type_custom = State()
    living = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in_from = State()
    viewings_from = State()
    photos = State()
    preview = State()


class EditOffer(StatesGroup):
    choose_field = State()
    value = State()
    housing_type_custom = State()


# ----------------------------
# Router
# ----------------------------

router = Router()


# ----------------------------
# Utility for photo prompt message (avoid spam)
# ----------------------------

async def upsert_photo_prompt(message: types.Message, state: FSMContext, count: int) -> None:
    data = await state.get_data()
    prompt_id = data.get("photo_prompt_msg_id")

    text = f"📸 Фото додано ({count}).\nНадішли ще фото або натисни ✅ <b>Готово</b>."
    if prompt_id:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=prompt_id,
                reply_markup=kb_photos_done(),
            )
            return
        except Exception:
            pass

    sent = await message.answer(text, reply_markup=kb_photos_done())
    await state.update_data(photo_prompt_msg_id=sent.message_id)


async def send_media_album(bot: Bot, chat_id: int, file_ids: List[str]) -> None:
    # Telegram allows max 10 items per media group
    for i in range(0, len(file_ids), 10):
        chunk = file_ids[i : i + 10]
        media = [types.InputMediaPhoto(media=fid) for fid in chunk]
        await bot.send_media_group(chat_id=chat_id, media=media)


async def send_offer_preview(bot: Bot, chat_id: int, row: sqlite3.Row) -> None:
    photos = json.loads(row["photos_json"] or "[]")
    if photos:
        await send_media_album(bot, chat_id, photos)
    await bot.send_message(
        chat_id=chat_id,
        text=offer_text(row, include_status=False),
        reply_markup=kb_preview_actions(int(row["id"])),
    )


# ----------------------------
# Commands
# ----------------------------

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    txt = (
        "👋 <b>ORANDA SK</b>\n\n"
        "Команди:\n"
        "• /new — створити пропозицію\n"
        "• /stats — статистика\n\n"
        "Під час додавання фото:\n"
        "• натисни ✅ Готово (кнопка) або напиши /done"
    )
    await message.answer(txt)


@router.message(Command("new"))
async def cmd_new(message: types.Message, state: FSMContext):
    await state.clear()
    username = message.from_user.username or f"id{message.from_user.id}"
    offer_id = create_offer(message.from_user.id, username)
    row = get_offer(offer_id)

    await state.update_data(offer_id=offer_id)
    await state.set_state(NewOffer.category)

    await message.answer(
        f"🆕 Створюємо пропозицію {fmt_seq(int(row['seq']))}\n\nОберіть категорію:",
        reply_markup=kb_category(),
    )


@router.message(Command("done"))
async def cmd_done(message: types.Message, state: FSMContext):
    # Text command /done works in photos state
    if (await state.get_state()) != NewOffer.photos.state:
        return
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        await message.answer("⚠️ Не знайдено пропозицію. Почни заново /new")
        await state.clear()
        return

    row = get_offer(int(offer_id))
    photos = json.loads(row["photos_json"] or "[]")
    if not photos:
        await message.answer("⚠️ Спочатку додай хоча б 1 фото.", reply_markup=kb_photos_done())
        return

    # prevent duplicates
    if (await state.get_state()) == NewOffer.preview.state:
        return

    await state.set_state(NewOffer.preview)
    await message.answer("👉 <b>Це фінальний вигляд пропозиції</b> (перевір):")
    await send_offer_preview(message.bot, message.chat.id, row)


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await message.answer(build_stats_text())


@router.message(Command("id"))
async def cmd_id(message: types.Message):
    await message.answer(f"Ваш ID: <code>{message.from_user.id}</code>\nChat ID: <code>{message.chat.id}</code>")


# ----------------------------
# Wizard callbacks
# ----------------------------

@router.callback_query(StateFilter(NewOffer.category), F.data.startswith("cat:"))
async def cb_category(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    offer_id = int((await state.get_data())["offer_id"])
    category = cb.data.split(":", 1)[1]
    update_offer(offer_id, category=category)

    await state.set_state(NewOffer.housing_type)
    await cb.message.answer("Оберіть тип житла:", reply_markup=kb_housing_type())


@router.callback_query(StateFilter(NewOffer.housing_type), F.data.startswith("type:"))
async def cb_housing_type(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    offer_id = int((await state.get_data())["offer_id"])
    val = cb.data.split(":", 1)[1]

    if val == "__other__":
        await state.set_state(NewOffer.housing_type_custom)
        await cb.message.answer("✍️ Введи свій варіант типу житла (наприклад: Двоповерховий будинок):")
        return

    update_offer(offer_id, housing_type=val)
    await state.set_state(NewOffer.living)
    await cb.message.answer("🏡 Введи <b>Проживання</b> (текстом):")


@router.message(StateFilter(NewOffer.housing_type_custom))
async def msg_housing_type_custom(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    val = (message.text or "").strip()
    if not val:
        await message.answer("⚠️ Напиши текстом тип житла.")
        return
    update_offer(offer_id, housing_type=val)
    await state.set_state(NewOffer.living)
    await message.answer("🏡 Введи <b>Проживання</b> (текстом):")


@router.message(StateFilter(NewOffer.living))
async def msg_living(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, living=message.text or "")
    await state.set_state(NewOffer.street)
    await message.answer("📍 Введи <b>Вулицю</b>:")


@router.message(StateFilter(NewOffer.street))
async def msg_street(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, street=message.text or "")
    await state.set_state(NewOffer.city)
    await message.answer("🏙️ Введи <b>Місто</b>:")


@router.message(StateFilter(NewOffer.city))
async def msg_city(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, city=message.text or "")
    await state.set_state(NewOffer.district)
    await message.answer("🗺️ Введи <b>Район</b>:")


@router.message(StateFilter(NewOffer.district))
async def msg_district(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, district=message.text or "")
    await state.set_state(NewOffer.advantages)
    await message.answer("✨ Введи <b>Переваги</b> (можна списком):")


@router.message(StateFilter(NewOffer.advantages))
async def msg_advantages(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, advantages=message.text or "")
    await state.set_state(NewOffer.rent)
    await message.answer("💶 Введи <b>Оренда</b> (наприклад: 350€):")


@router.message(StateFilter(NewOffer.rent))
async def msg_rent(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, rent=message.text or "")
    await state.set_state(NewOffer.deposit)
    await message.answer("🔐 Введи <b>Депозит</b>:")


@router.message(StateFilter(NewOffer.deposit))
async def msg_deposit(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, deposit=message.text or "")
    await state.set_state(NewOffer.commission)
    await message.answer("🤝 Введи <b>Комісія</b>:")


@router.message(StateFilter(NewOffer.commission))
async def msg_commission(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, commission=message.text or "")
    await state.set_state(NewOffer.parking)
    await message.answer("🚗 Введи <b>Паркінг</b> (є/нема/умови):")


@router.message(StateFilter(NewOffer.parking))
async def msg_parking(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, parking=message.text or "")
    await state.set_state(NewOffer.move_in_from)
    await message.answer("📦 Введи <b>Заселення від</b>:")


@router.message(StateFilter(NewOffer.move_in_from))
async def msg_movein(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    update_offer(offer_id, move_in_from=message.text or "")
    await state.set_state(NewOffer.viewings_from)
    await message.answer("👀 Введи <b>Огляди від</b>:")


@router.message(StateFilter(NewOffer.viewings_from))
async def msg_viewings(message: types.Message, state: FSMContext):
    offer_id = int((await state.get_data())["offer_id"])
    # broker default = creator username (can be edited later)
    broker = message.from_user.username or f"id{message.from_user.id}"
    update_offer(offer_id, viewings_from=message.text or "", broker_username=broker)

    await state.set_state(NewOffer.photos)
    await state.update_data(photo_prompt_msg_id=None)
    await message.answer("📸 Надішли фото. Коли закінчиш — натисни ✅ <b>Готово</b> або напиши /done.")


# ----------------------------
# Photos
# ----------------------------

@router.message(StateFilter(NewOffer.photos), F.photo)
async def msg_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        await message.answer("⚠️ Не знайдено пропозицію. Почни заново /new")
        await state.clear()
        return

    # use highest resolution
    file_id = message.photo[-1].file_id
    count = add_photo(int(offer_id), file_id)

    # update one prompt message instead of spamming
    await upsert_photo_prompt(message, state, count)


@router.message(StateFilter(NewOffer.photos))
async def msg_photo_other(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip().lower()
    if txt in ("готово", "done", "/done"):
        await cmd_done(message, state)
        return
    await message.answer("Надішли фото або /done щоб завершити.", reply_markup=kb_photos_done())


@router.callback_query(StateFilter(NewOffer.photos), F.data == "photos:done")
async def cb_done_photos(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        await cb.message.answer("⚠️ Не знайдено пропозицію. Почни заново /new")
        await state.clear()
        return

    row = get_offer(int(offer_id))
    photos = json.loads(row["photos_json"] or "[]")

    if not photos:
        await cb.message.answer("⚠️ Спочатку додай хоча б 1 фото.", reply_markup=kb_photos_done())
        return

    # prevent duplicates
    if (await state.get_state()) == NewOffer.preview.state:
        return

    await state.set_state(NewOffer.preview)
    await cb.message.answer("👉 <b>Це фінальний вигляд пропозиції</b> (перевір):")
    await send_offer_preview(cb.bot, cb.message.chat.id, row)


# ----------------------------
# Preview actions: Publish / Edit / Cancel
# ----------------------------

@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    offer_id = data.get("offer_id")
    # If cancel current offer
    if offer_id:
        await state.clear()
    await cb.message.answer("❌ Скасовано. /new — щоб створити нову пропозицію.")


@router.callback_query(F.data.startswith("pub:"))
async def cb_publish(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    offer_id = int(cb.data.split(":", 1)[1])

    row = get_offer(offer_id)
    photos = json.loads(row["photos_json"] or "[]")
    if not photos:
        await cb.message.answer("⚠️ Нема фото. Додай фото перед публікацією.")
        return

    # If already published — do not duplicate
    if row["published_message_id"]:
        await cb.message.answer("✅ Вже опубліковано в групу. Статус можна змінювати кнопками під постом.")
        return

    # Send album first
    await send_media_album(cb.bot, GROUP_CHAT_ID, photos)

    # Set initial status at publish time
    set_status(offer_id, STATUS_ACTIVE, cb.from_user)

    # Send text message with status buttons
    row = get_offer(offer_id)  # refreshed
    msg = await cb.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=offer_text(row, include_status=True),
        reply_markup=status_keyboard(offer_id),
        disable_web_page_preview=True,
    )

    set_published(offer_id, GROUP_CHAT_ID, msg.message_id)

    await cb.message.answer(f"✅ Пропозицію {fmt_seq(int(row['seq']))} опубліковано в групу.")
    await state.clear()


# ----------------------------
# Editing (from preview)
# ----------------------------

EDIT_FIELDS: List[Tuple[str, str]] = [
    ("category", "Категорія"),
    ("housing_type", "Тип житла"),
    ("living", "Проживання"),
    ("street", "Вулиця"),
    ("city", "Місто"),
    ("district", "Район"),
    ("advantages", "Переваги"),
    ("rent", "Оренда"),
    ("deposit", "Депозит"),
    ("commission", "Комісія"),
    ("parking", "Паркінг"),
    ("move_in_from", "Заселення від"),
    ("viewings_from", "Огляди від"),
    ("broker_username", "Маклер"),
]


def edit_list_text(seq: int) -> str:
    lines = [f"✏️ <b>Редагування {fmt_seq(seq)}</b>", "Напиши номер пункту, який хочеш змінити (1–14).", "", "Список:"]
    for i, (_, label) in enumerate(EDIT_FIELDS, start=1):
        lines.append(f"{i}. {label}")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("edit:"))
async def cb_edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    offer_id = int(cb.data.split(":", 1)[1])
    row = get_offer(offer_id)

    await state.set_state(EditOffer.choose_field)
    await state.update_data(edit_offer_id=offer_id)

    await cb.message.answer(edit_list_text(int(row["seq"])))


@router.message(StateFilter(EditOffer.choose_field))
async def msg_edit_choose(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    if not offer_id:
        await message.answer("⚠️ Нема активного редагування.")
        await state.clear()
        return

    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer("⚠️ Напиши номер 1–14.")
        return

    idx = int(txt)
    if not (1 <= idx <= len(EDIT_FIELDS)):
        await message.answer("⚠️ Напиши номер 1–14.")
        return

    field_key, field_label = EDIT_FIELDS[idx - 1]
    await state.update_data(edit_field_key=field_key, edit_field_label=field_label)

    # housing_type: give keyboard + other
    if field_key == "housing_type":
        await state.set_state(EditOffer.value)
        await message.answer("Оберіть тип житла:", reply_markup=kb_housing_type())
        return

    # category: give keyboard
    if field_key == "category":
        await state.set_state(EditOffer.value)
        await message.answer("Оберіть категорію:", reply_markup=kb_category())
        return

    await state.set_state(EditOffer.value)
    await message.answer(f"✍️ Введи нове значення для <b>{safe_html(field_label)}</b>:")


@router.callback_query(StateFilter(EditOffer.value), F.data.startswith("type:"))
async def cb_edit_type(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    if not offer_id:
        await cb.message.answer("⚠️ Нема активного редагування.")
        await state.clear()
        return

    val = cb.data.split(":", 1)[1]
    if val == "__other__":
        await state.set_state(EditOffer.housing_type_custom)
        await cb.message.answer("✍️ Введи свій варіант типу житла:")
        return

    update_offer(offer_id, housing_type=val)
    await state.clear()

    row = get_offer(offer_id)
    await cb.message.answer("✅ Оновлено. Ось актуальний превʼю:")
    await send_offer_preview(cb.bot, cb.message.chat.id, row)


@router.message(StateFilter(EditOffer.housing_type_custom))
async def msg_edit_type_custom(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    if not offer_id:
        await message.answer("⚠️ Нема активного редагування.")
        await state.clear()
        return

    val = (message.text or "").strip()
    if not val:
        await message.answer("⚠️ Напиши текстом тип житла.")
        return

    update_offer(offer_id, housing_type=val)
    await state.clear()

    row = get_offer(offer_id)
    await message.answer("✅ Оновлено. Ось актуальний превʼю:")
    await send_offer_preview(message.bot, message.chat.id, row)


@router.callback_query(StateFilter(EditOffer.value), F.data.startswith("cat:"))
async def cb_edit_category(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    if not offer_id:
        await cb.message.answer("⚠️ Нема активного редагування.")
        await state.clear()
        return

    category = cb.data.split(":", 1)[1]
    update_offer(offer_id, category=category)
    await state.clear()

    row = get_offer(offer_id)
    await cb.message.answer("✅ Оновлено. Ось актуальний превʼю:")
    await send_offer_preview(cb.bot, cb.message.chat.id, row)


@router.message(StateFilter(EditOffer.value))
async def msg_edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    field_key = data.get("edit_field_key")
    field_label = data.get("edit_field_label")

    if not offer_id or not field_key:
        await message.answer("⚠️ Нема активного редагування.")
        await state.clear()
        return

    val = (message.text or "").strip()
    if not val:
        await message.answer("⚠️ Введи значення текстом.")
        return

    update_offer(offer_id, **{field_key: val})
    await state.clear()

    row = get_offer(offer_id)
    await message.answer(f"✅ Оновлено <b>{safe_html(field_label)}</b>. Ось актуальний превʼю:")
    await send_offer_preview(message.bot, message.chat.id, row)


# ----------------------------
# Status buttons in GROUP (or anywhere)
# ----------------------------

@router.callback_query(F.data.startswith("st:"))
async def cb_status(cb: types.CallbackQuery):
    await cb.answer()
    try:
        _, offer_id_s, status = cb.data.split(":", 2)
        offer_id = int(offer_id_s)
    except Exception:
        return

    if status not in ALLOWED_STATUSES:
        return

    row = get_offer(offer_id)
    if not row["published_message_id"]:
        # not published yet
        return

    # Update status
    set_status(offer_id, status, cb.from_user)

    # Edit group message text
    row2 = get_offer(offer_id)
    try:
        await cb.bot.edit_message_text(
            chat_id=int(row2["published_chat_id"]),
            message_id=int(row2["published_message_id"]),
            text=offer_text(row2, include_status=True),
            reply_markup=status_keyboard(offer_id),
            disable_web_page_preview=True,
        )
    except Exception:
        # if can't edit (permissions), at least respond
        pass


# ----------------------------
# Stats
# ----------------------------

def _period_bounds(period: str) -> Tuple[datetime, datetime, str]:
    # returns (start, end, label)
    now = datetime.now(tz=APP_TZ)
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
        label = f"День ({start.date().isoformat()})"
        return start, end, label

    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # next month:
        if start.month == 12:
            next_m = start.replace(year=start.year + 1, month=1)
        else:
            next_m = start.replace(month=start.month + 1)
        end = next_m - (next_m - next_m.replace(hour=0, minute=0, second=0, microsecond=0))  # midnight same
        end = next_m.replace(hour=0, minute=0, second=0, microsecond=0) - (next_m.replace(hour=0, minute=0, second=0, microsecond=0) - (next_m - (next_m - next_m)))  # noop safety
        # simpler:
        end = (next_m.replace(hour=0, minute=0, second=0, microsecond=0) - (next_m - next_m))  # still noop
        # Actually, just use < next_m in SQL, easier:
        label = f"Місяць ({start.strftime('%Y-%m')})"
        return start, next_m, label

    # year
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    next_y = start.replace(year=start.year + 1)
    label = f"Рік ({start.year})"
    return start, next_y, label


def _fetch_status_counts(start_iso: str, end_iso: str) -> Dict[str, int]:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        SELECT status, COUNT(*) AS c
        FROM status_events
        WHERE at >= ? AND at < ?
        GROUP BY status;
        """,
        (start_iso, end_iso),
    )
    counts = {r["status"]: int(r["c"]) for r in cur.fetchall()}
    con.close()
    return counts


def _fetch_broker_counts(start_iso: str, end_iso: str) -> Dict[str, Dict[str, int]]:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        SELECT username, status, COUNT(*) AS c
        FROM status_events
        WHERE at >= ? AND at < ?
        GROUP BY username, status;
        """,
        (start_iso, end_iso),
    )
    out: Dict[str, Dict[str, int]] = {}
    for r in cur.fetchall():
        u = r["username"] or "unknown"
        out.setdefault(u, {})
        out[u][r["status"]] = int(r["c"])
    con.close()
    return out


def build_stats_text() -> str:
    parts: List[str] = ["📊 <b>Статистика</b> (зміни статусів)\n"]

    for period in ("day", "month", "year"):
        start, end, label = _period_bounds(period)
        start_iso = start.isoformat(timespec="seconds")
        end_iso = end.isoformat(timespec="seconds")

        counts = _fetch_status_counts(start_iso, end_iso)
        parts.append(f"<b>{label}</b>")
        parts.append(f"🟢 Актуально: {counts.get(STATUS_ACTIVE, 0)}")
        parts.append(f"🟡 Резерв: {counts.get(STATUS_RESERVED, 0)}")
        parts.append(f"⚫️ Знято: {counts.get(STATUS_REMOVED, 0)}")
        parts.append(f"✅ Угода закрита: {counts.get(STATUS_CLOSED, 0)}")

        broker = _fetch_broker_counts(start_iso, end_iso)
        if broker:
            parts.append("\n👤 <b>Маклери (по статусах)</b>")
            # sort by total
            def total(d: Dict[str, int]) -> int:
                return sum(d.get(s, 0) for s in ALLOWED_STATUSES)

            for u, d in sorted(broker.items(), key=lambda x: total(x[1]), reverse=True):
                line = (
                    f"- @{u.lstrip('@')}: "
                    f"🟢{d.get(STATUS_ACTIVE, 0)} "
                    f"🟡{d.get(STATUS_RESERVED, 0)} "
                    f"⚫️{d.get(STATUS_REMOVED, 0)} "
                    f"✅{d.get(STATUS_CLOSED, 0)}"
                )
                parts.append(line)
        parts.append("\n")

    return "\n".join(parts).strip()


# ----------------------------
# Fallback: text shortcuts (optional)
# ----------------------------

@router.message(F.text)
async def any_text(message: types.Message):
    t = (message.text or "").strip().lower()
    if t in ("статистика", "📊 статистика"):
        await message.answer(build_stats_text())
        return
    if t in ("допомога", "help", "/help"):
        await cmd_start(message)


# ----------------------------
# Main
# ----------------------------

async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
