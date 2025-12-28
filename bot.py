import asyncio
import datetime as dt
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# ===================== CONFIG / ENV =====================
TZ = ZoneInfo("Europe/Copenhagen")

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
DB_PATH = os.getenv("DB_PATH", "data/bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не заданий у Variables (Railway).")
if not GROUP_CHAT_ID_RAW:
    raise RuntimeError("GROUP_CHAT_ID не заданий у Variables (Railway).")

GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

ADMIN_IDS: set[int] = set()
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.isdigit():
            ADMIN_IDS.add(int(x))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ===================== UI (Reply keyboards) =====================
def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Зробити пропозицію")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="❓ Допомога")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Оберіть дію…",
    )

def kb_photos() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="ГОТОВО"), KeyboardButton(text="СКАСУВАТИ")]],
        resize_keyboard=True,
        input_field_placeholder="Надсилайте фото або натисніть ГОТОВО…",
    )

def kb_review() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="ПУБЛІКУВАТИ"), KeyboardButton(text="СКАСУВАТИ")]],
        resize_keyboard=True,
        input_field_placeholder="Публікувати чи змінити пункт?",
    )


# ===================== DB =====================
def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db() -> None:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,            -- ISO datetime (TZ Europe/Copenhagen)
            status TEXT NOT NULL,
            category TEXT,
            property_type TEXT,
            street TEXT,
            city TEXT,
            district TEXT,
            advantages TEXT,
            rent TEXT,
            deposit TEXT,
            commission TEXT,
            parking TEXT,
            move_in TEXT,
            viewing TEXT,
            broker TEXT,                         -- @нік (в полі 14)
            photos_json TEXT NOT NULL,            -- list[file_id]
            author_id INTEGER NOT NULL,           -- telegram user id автора створення
            author_username TEXT,                 -- telegram username автора створення
            group_album_first_msg_id INTEGER,      -- перше повідомлення альбому (для довідки)
            group_offer_msg_id INTEGER             -- повідомлення з текстом пропозиції + кнопками
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            ts TEXT NOT NULL,                     -- ISO datetime (TZ Europe/Copenhagen)
            actor_id INTEGER NOT NULL,
            actor_username TEXT,
            old_status TEXT,
            new_status TEXT
        )
        """
    )
    con.commit()
    con.close()

def now_iso() -> str:
    return dt.datetime.now(TZ).replace(microsecond=0).isoformat()

def create_offer(author_id: int, author_username: str) -> int:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO offers (created_at, status, photos_json, author_id, author_username)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_iso(), "🟢 Актуально", "[]", author_id, author_username),
    )
    oid = int(cur.lastrowid)
    con.commit()
    con.close()
    return oid

def update_offer_fields(offer_id: int, fields: Dict[str, Any]) -> None:
    if not fields:
        return
    con = db()
    cur = con.cursor()
    cols = ", ".join([f"{k}=?" for k in fields.keys()])
    vals = list(fields.values()) + [offer_id]
    cur.execute(f"UPDATE offers SET {cols} WHERE id=?", vals)
    con.commit()
    con.close()

def get_offer(offer_id: int) -> Optional[Dict[str, Any]]:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None

def set_offer_photos(offer_id: int, photos: List[str]) -> None:
    update_offer_fields(offer_id, {"photos_json": json.dumps(photos, ensure_ascii=False)})

def log_status_change(offer_id: int, actor_id: int, actor_username: str, old_status: str, new_status: str) -> None:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO status_log (offer_id, ts, actor_id, actor_username, old_status, new_status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (offer_id, now_iso(), actor_id, actor_username, old_status, new_status),
    )
    con.commit()
    con.close()


# ===================== FLOW / FIELDS =====================
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
    review = State()
    edit_value = State()

class EditExistingFSM(StatesGroup):
    choose_field = State()
    edit_value = State()

FIELDS_ORDER: List[Tuple[str, str, str]] = [
    ("category", "Категорія", "2) Категорія: Оренда або Продажа"),
    ("property_type", "Проживання", "3) Проживання: ліжко / кімната / студія / 1к / 2к / 3к / 4к / інше"),
    ("street", "Вулиця", "4) Вулиця: напиши (наприклад: вул. Шевченка 10)"),
    ("city", "Місто", "5) Місто: напиши"),
    ("district", "Район", "6) Район: напиши"),
    ("advantages", "Переваги", "7) Переваги житла: напиши"),
    ("rent", "Оренда", "8) Оренда: напиши суму"),
    ("deposit", "Депозит", "9) Депозит: напиши суму"),
    ("commission", "Комісія", "10) Комісія: напиши суму"),
    ("parking", "Паркінг", "11) Паркінг: напиши"),
    ("move_in", "Заселення від", "12) Заселення від: напиши"),
    ("viewing", "Огляди від", "13) Огляди від: напиши"),
    ("broker", "Маклер", "14) Маклер: напиши нік (наприклад: @nickname)"),
]

PROPERTY_TYPES = [
    "Ліжко", "Кімната", "Студія",
    "1к квартира", "2к квартира", "3к квартира", "4к квартира",
    "Інше (напишу свій варіант)"
]

def offer_num(offer_id: int) -> str:
    return f"{offer_id:04d}"

def normalize_text(s: str) -> str:
    return (s or "").strip()

def can_manage(user_id: int, offer: Dict[str, Any]) -> bool:
    return user_id in ADMIN_IDS or int(offer["author_id"]) == int(user_id)

def field_by_number(n: int) -> Optional[str]:
    # 2..14
    if n < 2 or n > 14:
        return None
    return FIELDS_ORDER[n - 2][0]

def parse_edit_cmd(text: str) -> Optional[int]:
    m = re.match(r"^\s*змінити\s+(\d+)\s*$", text.strip().lower())
    if not m:
        return None
    return int(m.group(1))

def prompt_for_field(field_key: str) -> str:
    for k, _t, prompt in FIELDS_ORDER:
        if k == field_key:
            return prompt
    return "Напиши значення:"

def build_offer_text(offer: Dict[str, Any]) -> str:
    emoji = {
        "category": "📌", "property_type": "🏠", "street": "📍", "city": "🏙️",
        "district": "🗺️", "advantages": "✨", "rent": "💶", "deposit": "🔒",
        "commission": "🧾", "parking": "🅿️", "move_in": "📅", "viewing": "👀", "broker": "👤",
    }
    lines = []
    lines.append(f"🏠 **ПРОПОЗИЦІЯ #{offer_num(int(offer['id']))}**")
    lines.append(f"📊 **Статус:** {offer.get('status','')}")
    lines.append("")
    idx = 2
    for key, title, _ in FIELDS_ORDER:
        val = offer.get(key) or "—"
        lines.append(f"{idx}. {emoji.get(key,'•')} **{title}:** {val}")
        idx += 1
    lines.append("")
    lines.append(f"🕒 **Дата створення:** {str(offer.get('created_at',''))[:10]}")
    return "\n".join(lines)

def group_kb(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:active:{offer_id}"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:reserve:{offer_id}"),
            InlineKeyboardButton(text="🔴 Неактуально", callback_data=f"st:inactive:{offer_id}"),
            InlineKeyboardButton(text="✅ Закрили угоду", callback_data=f"st:closed:{offer_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit:{offer_id}")
        ]
    ])


# ===================== GLOBAL CANCEL =====================
@dp.message(F.text.lower() == "скасувати")
async def cancel_any(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Скасовано.", reply_markup=kb_main())


# ===================== START / MENU =====================
@dp.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Вітаю! Я бот для створення пропозицій нерухомості.\n\n"
        "Натисни кнопку ➕ Зробити пропозицію, щоб почати.",
        reply_markup=kb_main(),
    )

@dp.message(F.text == "❓ Допомога")
async def help_msg(msg: Message):
    await msg.answer(
        "🧾 Як працює бот:\n"
        "1) ➕ Зробити пропозицію\n"
        "2) Заповни пункти 2–14 (вводиш текст)\n"
        "3) Надсилай фото → ГОТОВО\n"
        "4) Перевір → ПУБЛІКУВАТИ або ЗМІНИТИ 5\n\n"
        "📊 Статистика показує день / місяць / рік, та хто скільки міняв статуси.",
        reply_markup=kb_main(),
    )

# ===================== NEW OFFER =====================
@dp.message(Command("new"))
@dp.message(F.text == "➕ Зробити пропозицію")
@dp.message(F.text.lower() == "зробити пропозицію")
async def new_offer(msg: Message, state: FSMContext):
    await state.clear()
    author_username = msg.from_user.username or "без_ніка"
    oid = create_offer(msg.from_user.id, author_username)
    await state.update_data(offer_id=oid, photos=[])
    await state.set_state(OfferFSM.category)
    await msg.answer(
        "1) «Зробити пропозицію» ✅\n\n"
        "2) Категорія: **Оренда** або **Продажа**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

# ===================== STEPS 2..14 (NO BUTTONS) =====================
@dp.message(OfferFSM.category)
async def s_category(msg: Message, state: FSMContext):
    val = normalize_text(msg.text).lower()
    if val not in ("оренда", "продажа", "продаж"):
        await msg.answer("Напиши **Оренда** або **Продажа**", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return
    val_norm = "Оренда" if val.startswith("орен") else "Продажа"
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"category": val_norm})
    await state.set_state(OfferFSM.property_type)
    await msg.answer(
        "3) Проживання: напиши один варіант:\n- " + "\n- ".join(PROPERTY_TYPES),
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(OfferFSM.property_type)
async def s_property_type(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"property_type": normalize_text(msg.text)})
    await state.set_state(OfferFSM.street)
    await msg.answer("4) Вулиця: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.street)
async def s_street(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"street": normalize_text(msg.text)})
    await state.set_state(OfferFSM.city)
    await msg.answer("5) Місто: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.city)
async def s_city(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"city": normalize_text(msg.text)})
    await state.set_state(OfferFSM.district)
    await msg.answer("6) Район: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.district)
async def s_district(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"district": normalize_text(msg.text)})
    await state.set_state(OfferFSM.advantages)
    await msg.answer("7) Переваги житла: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.advantages)
async def s_adv(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"advantages": normalize_text(msg.text)})
    await state.set_state(OfferFSM.rent)
    await msg.answer("8) Оренда: напиши суму", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.rent)
async def s_rent(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"rent": normalize_text(msg.text)})
    await state.set_state(OfferFSM.deposit)
    await msg.answer("9) Депозит: напиши суму", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.deposit)
async def s_dep(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"deposit": normalize_text(msg.text)})
    await state.set_state(OfferFSM.commission)
    await msg.answer("10) Комісія: напиши суму", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.commission)
async def s_comm(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"commission": normalize_text(msg.text)})
    await state.set_state(OfferFSM.parking)
    await msg.answer("11) Паркінг: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.parking)
async def s_parking(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"parking": normalize_text(msg.text)})
    await state.set_state(OfferFSM.move_in)
    await msg.answer("12) Заселення від: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.move_in)
async def s_move(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"move_in": normalize_text(msg.text)})
    await state.set_state(OfferFSM.viewing)
    await msg.answer("13) Огляди від: напиши", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.viewing)
async def s_view(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    update_offer_fields(oid, {"viewing": normalize_text(msg.text)})
    await state.set_state(OfferFSM.broker)
    await msg.answer("14) Маклер: напиши нік (наприклад: @nickname)", reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.broker)
async def s_broker(msg: Message, state: FSMContext):
    oid = int((await state.get_data())["offer_id"])
    nick = normalize_text(msg.text)
    if not nick.startswith("@"):
        await msg.answer("Нік має починатися з @ (наприклад: @nickname)", reply_markup=ReplyKeyboardRemove())
        return
    update_offer_fields(oid, {"broker": nick})
    await state.set_state(OfferFSM.photos)
    await msg.answer(
        "15) Завантаж фото.\nНадсилай фото (можна багато).\n\nКоли закінчиш — натисни **ГОТОВО** 👇",
        reply_markup=kb_photos(),
        parse_mode="Markdown",
    )

# ===================== PHOTOS (WITH ГОТОВО BUTTON) =====================
@dp.message(OfferFSM.photos, F.photo)
async def photo_add(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos: List[str] = data.get("photos", [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"📷 Фото додано: {len(photos)}", reply_markup=kb_photos())

@dp.message(OfferFSM.photos, F.text)
async def photos_done(msg: Message, state: FSMContext):
    if msg.text.strip().lower() != "готово":
        await msg.answer("Надсилай фото або натисни **ГОТОВО**.", reply_markup=kb_photos(), parse_mode="Markdown")
        return

    data = await state.get_data()
    oid = int(data["offer_id"])
    photos: List[str] = data.get("photos", [])
    if not photos:
        await msg.answer("❌ Потрібно хоча б одне фото.", reply_markup=kb_photos())
        return

    set_offer_photos(oid, photos)

    offer = get_offer(oid)
    preview = build_offer_text(offer)

    # Превʼю в боті: альбом + текст
    media = [InputMediaPhoto(media=p) for p in photos]
    await bot.send_media_group(msg.chat.id, media)
    await msg.answer(preview, parse_mode="Markdown", reply_markup=kb_review())

    await state.set_state(OfferFSM.review)

# ===================== REVIEW (Publish / Edit by command) =====================
@dp.message(OfferFSM.review, F.text)
async def review(msg: Message, state: FSMContext):
    t = msg.text.strip().lower()
    data = await state.get_data()
    oid = int(data["offer_id"])

    if t == "публікувати":
        await publish_to_group(msg, oid)
        await state.clear()
        await msg.answer("✅ Готово. Меню:", reply_markup=kb_main())
        return

    n = parse_edit_cmd(msg.text)
    if n is None:
        await msg.answer("Напиши **ПУБЛІКУВАТИ** або **ЗМІНИТИ 5** (2–14).", reply_markup=kb_review(), parse_mode="Markdown")
        return

    field = field_by_number(n)
    if not field:
        await msg.answer("Невірний номер. Можна 2–14. Наприклад: **ЗМІНИТИ 8**", reply_markup=kb_review(), parse_mode="Markdown")
        return

    await state.update_data(edit_field=field)
    await state.set_state(OfferFSM.edit_value)
    await msg.answer("✏️ " + prompt_for_field(field), reply_markup=ReplyKeyboardRemove())

@dp.message(OfferFSM.edit_value, F.text)
async def edit_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    oid = int(data["offer_id"])
    field = data.get("edit_field")
    if not field:
        await msg.answer("❌ Помилка. Спробуй ще раз /new", reply_markup=kb_main())
        await state.clear()
        return

    val = normalize_text(msg.text)
    if field == "broker" and not val.startswith("@"):
        await msg.answer("Нік має починатися з @. Спробуй ще раз:", reply_markup=ReplyKeyboardRemove())
        return

    update_offer_fields(oid, {field: val})
    offer = get_offer(oid)
    await msg.answer(build_offer_text(offer), parse_mode="Markdown", reply_markup=kb_review())
    await state.set_state(OfferFSM.review)

# ===================== PUBLISH (album + offer message with buttons right under) =====================
async def publish_to_group(msg: Message, offer_id: int) -> None:
    offer = get_offer(offer_id)
    if not offer:
        await msg.answer("❌ Пропозицію не знайдено.", reply_markup=kb_main())
        return

    photos = json.loads(offer.get("photos_json") or "[]")
    if not photos:
        await msg.answer("❌ Немає фото.", reply_markup=kb_main())
        return

    # 1) Альбом у групу (без caption, щоб не було ліміту 1024)
    media = [InputMediaPhoto(media=p) for p in photos]
    album_msgs = await bot.send_media_group(GROUP_CHAT_ID, media)
    album_first_id = album_msgs[0].message_id

    # 2) Одразу під альбомом: текст пропозиції + кнопки статусів + редагування
    text = build_offer_text(offer)
    offer_msg = await bot.send_message(
        GROUP_CHAT_ID,
        text,
        parse_mode="Markdown",
        reply_markup=group_kb(offer_id),
        disable_web_page_preview=True
    )

    update_offer_fields(offer_id, {
        "group_album_first_msg_id": album_first_id,
        "group_offer_msg_id": offer_msg.message_id
    })

# ===================== GROUP CALLBACKS (status + edit) =====================
STATUS_MAP = {
    "active": "🟢 Актуально",
    "reserve": "🟡 Резерв",
    "inactive": "🔴 Неактуально",
    "closed": "✅ Закрили угоду",
}

@dp.callback_query(F.data.startswith("st:"))
async def cb_status(cb: CallbackQuery):
    try:
        _, code, offer_id_s = cb.data.split(":")
        offer_id = int(offer_id_s)
    except Exception:
        await cb.answer("Помилка")
        return

    offer = get_offer(offer_id)
    if not offer:
        await cb.answer("Не знайдено")
        return

    if not can_manage(cb.from_user.id, offer):
        await cb.answer("❌ Немає прав")
        return

    if code not in STATUS_MAP:
        await cb.answer("Помилка статусу")
        return

    old_status = offer.get("status", "")
    new_status = STATUS_MAP[code]
    update_offer_fields(offer_id, {"status": new_status})

    actor_username = cb.from_user.username or "без_ніка"
    log_status_change(offer_id, cb.from_user.id, actor_username, old_status, new_status)

    # Оновлюємо повідомлення пропозиції в групі (де кнопки)
    updated = get_offer(offer_id)
    offer_msg_id = updated.get("group_offer_msg_id")
    if offer_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=GROUP_CHAT_ID,
                message_id=int(offer_msg_id),
                text=build_offer_text(updated),
                parse_mode="Markdown",
                reply_markup=group_kb(offer_id),
                disable_web_page_preview=True
            )
        except Exception:
            pass

    await cb.answer(f"Статус: {new_status}")

@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit(cb: CallbackQuery, state: FSMContext):
    offer_id = int(cb.data.split(":")[1])
    offer = get_offer(offer_id)
    if not offer:
        await cb.answer("Не знайдено")
        return

    if not can_manage(cb.from_user.id, offer):
        await cb.answer("❌ Немає прав")
        return

    # Відкриваємо редагування в приваті
    await state.clear()
    await state.set_state(EditExistingFSM.choose_field)
    await state.update_data(edit_offer_id=offer_id)

    lines = [
        f"✏️ Редагування пропозиції #{offer_num(offer_id)}",
        "Напиши номер пункту, який хочеш змінити (2–14).",
        "Наприклад: 8",
        "",
        "Список:",
    ]
    idx = 2
    for _k, title, _p in FIELDS_ORDER:
        lines.append(f"{idx}. {title}")
        idx += 1

    try:
        await bot.send_message(cb.from_user.id, "\n".join(lines), reply_markup=ReplyKeyboardRemove())
        await cb.answer("Відправив в приват")
    except Exception:
        await cb.answer("Напиши боту в приват /start")

@dp.message(EditExistingFSM.choose_field, F.text)
async def edit_choose_field(msg: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    if not offer_id:
        await msg.answer("❌ Немає ID пропозиції. /start", reply_markup=kb_main())
        await state.clear()
        return

    try:
        n = int(msg.text.strip())
    except Exception:
        await msg.answer("Введи число 2–14. Наприклад: 8")
        return

    field = field_by_number(n)
    if not field:
        await msg.answer("Невірний номер. Можна 2–14.")
        return

    await state.update_data(edit_field=field)
    await state.set_state(EditExistingFSM.edit_value)
    await msg.answer(prompt_for_field(field))

@dp.message(EditExistingFSM.edit_value, F.text)
async def edit_existing_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("edit_offer_id") or 0)
    field = data.get("edit_field")
    if not offer_id or not field:
        await msg.answer("❌ Помилка. /start", reply_markup=kb_main())
        await state.clear()
        return

    offer = get_offer(offer_id)
    if not offer:
        await msg.answer("❌ Пропозицію не знайдено.")
        await state.clear()
        return

    if not can_manage(msg.from_user.id, offer):
        await msg.answer("❌ Немає прав.")
        await state.clear()
        return

    val = normalize_text(msg.text)
    if field == "broker" and not val.startswith("@"):
        await msg.answer("Нік має починатися з @. Спробуй ще раз:")
        return

    update_offer_fields(offer_id, {field: val})
    updated = get_offer(offer_id)

    # Оновлюємо повідомлення в групі
    offer_msg_id = updated.get("group_offer_msg_id")
    if offer_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=GROUP_CHAT_ID,
                message_id=int(offer_msg_id),
                text=build_offer_text(updated),
                parse_mode="Markdown",
                reply_markup=group_kb(offer_id),
                disable_web_page_preview=True
            )
        except Exception:
            pass

    await msg.answer("✅ Оновлено. Ось актуальна пропозиція:\n\n" + build_offer_text(updated), parse_mode="Markdown")
    await state.clear()

# ===================== STATS (day / month / year + brokers status changes) =====================
def _date_parts(d: dt.date) -> Tuple[str, str, str]:
    return (d.strftime("%Y-%m-%d"), d.strftime("%Y-%m"), d.strftime("%Y"))

def _stats_counts(created_prefix: str) -> Dict[str, int]:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        SELECT status, COUNT(*) as c
        FROM offers
        WHERE created_at LIKE ?
        GROUP BY status
        """,
        (created_prefix + "%",),
    )
    rows = cur.fetchall()
    con.close()
    out = {r["status"]: int(r["c"]) for r in rows}
    # гарантуємо ключі
    for v in STATUS_MAP.values():
        out.setdefault(v, 0)
    return out

def _stats_brokers_changes(ts_prefix: str) -> List[Tuple[str, int]]:
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        SELECT COALESCE(actor_username,'без_ніка') as u, COUNT(*) as c
        FROM status_log
        WHERE ts LIKE ?
        GROUP BY u
        ORDER BY c DESC
        LIMIT 20
        """,
        (ts_prefix + "%",),
    )
    rows = cur.fetchall()
    con.close()
    return [(r["u"], int(r["c"])) for r in rows]

@dp.message(F.text == "📊 Статистика")
@dp.message(Command("stats"))
async def stats(msg: Message):
    today = dt.datetime.now(TZ).date()
    day_s, month_s, year_s = _date_parts(today)

    day_counts = _stats_counts(day_s)
    month_counts = _stats_counts(month_s)
    year_counts = _stats_counts(year_s)

    day_changes = _stats_brokers_changes(day_s)
    month_changes = _stats_brokers_changes(month_s)
    year_changes = _stats_brokers_changes(year_s)

    def fmt_counts(title: str, counts: Dict[str, int]) -> str:
        return (
            f"**{title}**\n"
            f"🟢 Актуально: {counts.get('🟢 Актуально', 0)}\n"
            f"🟡 Резерв: {counts.get('🟡 Резерв', 0)}\n"
            f"🔴 Неактуально: {counts.get('🔴 Неактуально', 0)}\n"
            f"✅ Закрили угоду: {counts.get('✅ Закрили угоду', 0)}"
        )

    def fmt_changes(title: str, rows: List[Tuple[str, int]]) -> str:
        if not rows:
            return f"**{title}**\n(поки що немає змін статусів)"
        top = "\n".join([f"- @{u}: {c}" if not u.startswith("@") else f"- {u}: {c}" for u, c in rows[:10]])
        return f"**{title}**\n{top}"

    text = (
        "📊 **Статистика** (за датою створення пропозицій)\n\n"
        + fmt_counts(f"День ({day_s})", day_counts) + "\n\n"
        + fmt_counts(f"Місяць ({month_s})", month_counts) + "\n\n"
        + fmt_counts(f"Рік ({year_s})", year_counts)
        + "\n\n"
        "🧑‍💼 **Хто скільки міняв статусів**\n\n"
        + fmt_changes(f"День ({day_s})", day_changes) + "\n\n"
        + fmt_changes(f"Місяць ({month_s})", month_changes) + "\n\n"
        + fmt_changes(f"Рік ({year_s})", year_changes)
    )
    await msg.answer(text, parse_mode="Markdown", reply_markup=kb_main())

# ===================== MAIN =====================
async def main():
    init_db()
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
