import os
import re
import sqlite3
from datetime import datetime
from typing import List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv


# =========================
# ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_ID = os.getenv("GROUP_ID", "").strip()  # napr. -1003078875082
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()  # napr. "1057216609,123"
APP_TITLE = os.getenv("APP_TITLE", "ORENDA SK").strip()

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN in environment variables.")
if not GROUP_ID:
    raise RuntimeError("Missing GROUP_ID in environment variables.")

try:
    GROUP_ID_INT = int(GROUP_ID)
except ValueError:
    raise RuntimeError("GROUP_ID must be integer, e.g. -1003078875082")

ADMIN_IDS: List[int] = []
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x:
            try:
                ADMIN_IDS.append(int(x))
            except ValueError:
                pass


# =========================
# DB (SQLite)
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
            created_at TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_by_name TEXT,
            category TEXT NOT NULL,
            district TEXT NOT NULL,
            address TEXT NOT NULL,
            price TEXT NOT NULL,
            rooms TEXT,
            area_m2 TEXT,
            floor TEXT,
            deposit TEXT,
            available_from TEXT,
            contact TEXT NOT NULL,
            description TEXT,
            photos TEXT,               -- comma-separated file_ids
            status TEXT NOT NULL,      -- active/reserve/rented
            group_message_id INTEGER   -- message id in group
        )
    """)
    con.commit()
    con.close()

def insert_offer(data: dict) -> int:
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO offers (
            created_at, created_by, created_by_name,
            category, district, address, price, rooms, area_m2, floor,
            deposit, available_from, contact, description, photos, status, group_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        data.get("created_by"),
        data.get("created_by_name"),
        data.get("category"),
        data.get("district"),
        data.get("address"),
        data.get("price"),
        data.get("rooms"),
        data.get("area_m2"),
        data.get("floor"),
        data.get("deposit"),
        data.get("available_from"),
        data.get("contact"),
        data.get("description"),
        ",".join(data.get("photos", [])),
        data.get("status", "active"),
        None
    ))
    con.commit()
    offer_id = cur.lastrowid
    con.close()
    return offer_id

def get_offer(offer_id: int) -> Optional[dict]:
    con = db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id=?", (offer_id,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None

def update_offer(offer_id: int, fields: dict):
    keys = list(fields.keys())
    if not keys:
        return
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [fields[k] for k in keys]
    vals.append(offer_id)
    con = db()
    cur = con.cursor()
    cur.execute(f"UPDATE offers SET {sets} WHERE id=?", vals)
    con.commit()
    con.close()

def list_offers_by_user(user_id: int, limit: int = 30) -> List[dict]:
    con = db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE created_by=? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = cur.fetchall()
    con.close()
    return [dict(r) for r in rows]

def normalize_text_done(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("✅", "").strip()
    return t

# =========================
# UI (UA)
# =========================
STATUS_UA = {
    "active": "АКТИВНА",
    "reserve": "РЕЗЕРВОВАНО",
    "rented": "ЗДАНА В ОРЕНДУ",
}

CATEGORIES = [
    "Квартира",
    "Будинок",
    "Кімната",
    "Комерція",
]

# Bratislava – širší výber
BRATISLAVA_AREAS = [
    "Bratislava – Старе Місто",
    "Bratislava – Петржалка",
    "Bratislava – Ружинов",
    "Bratislava – Нове Місто",
    "Bratislava – Карлова Вес",
    "Bratislava – Дубравка",
    "Bratislava – Ламач",
    "Bratislava – Девін",
    "Bratislava – Девінська Нова Вес",
    "Bratislava – Зáгорська Бистриця",
    "Bratislava – Вайно́ри",
    "Bratislava – Рача",
    "Bratislava – Русовце",
    "Bratislava – Чуново",
    "Bratislava – Яро́вце",
    "Bratislava – Врáкуня",
    "Bratislava – Подунáйске Біску́піце",
]

OTHER_AREAS = [
    "Senec",
    "Pezinok",
    "Malacky",
    "Trnava",
    "Nitra",
    "Žilina",
    "Košice",
    "Інше (впиши вручну)",
]

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Пропоную житло", callback_data="offer_new")],
        [InlineKeyboardButton(text="📋 Мої оголошення", callback_data="my_offers")],
        [InlineKeyboardButton(text="ℹ️ Як це працює", callback_data="help")],
    ])

def kb_categories() -> InlineKeyboardMarkup:
    rows = []
    for c in CATEGORIES:
        rows.append([InlineKeyboardButton(text=c, callback_data=f"cat:{c}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_areas_page(page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    all_areas = BRATISLAVA_AREAS + OTHER_AREAS
    start = page * page_size
    end = start + page_size
    chunk = all_areas[start:end]

    rows = [[InlineKeyboardButton(text=a, callback_data=f"area:{a}")] for a in chunk]

    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"areas:{page-1}"))
    if end < len(all_areas):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"areas:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="✍️ Ввести вручну", callback_data="area:manual")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_photos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="photos:done")],
        [InlineKeyboardButton(text="⏭ Пропустити фото", callback_data="photos:skip")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:address")],
    ])

def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="confirm:publish")],
        [InlineKeyboardButton(text="✏️ Редагувати", callback_data="confirm:edit_menu")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm:cancel")],
    ])

def kb_status_controls(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Активна", callback_data=f"st:{offer_id}:active"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{offer_id}:reserve"),
        ],
        [
            InlineKeyboardButton(text="🔴 Здано", callback_data=f"st:{offer_id}:rented"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редагувати (DM)", callback_data=f"edit:{offer_id}"),
        ]
    ])

def compact(text: str) -> str:
    # menší rozostup – žiadne dvojité prázdne riadky
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def render_offer_text(o: dict) -> str:
    status = STATUS_UA.get(o["status"], o["status"])
    # menšie rozostupy + jasný formát
    parts = [
        f"🏠 **Оголошення #{o['id']}**",
        f"📌 **Статус:** {status}",
        f"🏷 **Тип:** {o['category']}",
        f"📍 **Район:** {o['district']}",
        f"📌 **Адреса:** {o['address']}",
        f"💶 **Ціна:** {o['price']}",
    ]
    if o.get("rooms"):
        parts.append(f"🛏 **Кімнати:** {o['rooms']}")
    if o.get("area_m2"):
        parts.append(f"📐 **Площа:** {o['area_m2']} м²")
    if o.get("floor"):
        parts.append(f"🏢 **Поверх:** {o['floor']}")
    if o.get("deposit"):
        parts.append(f"💳 **Депозит:** {o['deposit']}")
    if o.get("available_from"):
        parts.append(f"📅 **Вільно з:** {o['available_from']}")
    parts.append(f"☎️ **Контакт:** {o['contact']}")

    if o.get("description"):
        parts.append(f"📝 **Опис:** {o['description']}")

    parts.append("")
    parts.append("👤 Маклер: **Олександр**")  # požiadavka

    return compact("\n".join(parts))


# =========================
# FSM
# =========================
class OfferFlow(StatesGroup):
    category = State()
    district = State()
    district_manual = State()
    address = State()
    price = State()
    rooms = State()
    area_m2 = State()
    floor = State()
    deposit = State()
    available_from = State()
    contact = State()
    description = State()
    photos_collect = State()
    confirm = State()

class EditFlow(StatesGroup):
    offer_id = State()
    field = State()
    value = State()


# =========================
# Bot
# =========================
bot = Bot(BOT_TOKEN, parse_mode="Markdown")
dp = Dispatcher(storage=MemoryStorage())


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS if ADMIN_IDS else False


async def send_menu(message: Message):
    await message.answer(
        compact(
            f"👋 Вітаю! Це бот **{APP_TITLE}**.\n\n"
            "Обери дію нижче:"
        ),
        reply_markup=kb_main()
    )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await send_menu(message)


@dp.callback_query(F.data == "help")
async def help_cb(call: CallbackQuery):
    await call.message.answer(
        compact(
            "ℹ️ **Як це працює**\n\n"
            "1) Натисни **🏠 Пропоную житло**\n"
            "2) Заповни дані\n"
            "3) Додай фото (або пропусти)\n"
            "4) Натисни **✅ Опублікувати**\n\n"
            "Оголошення буде опубліковано в групі, а статус можна змінювати кнопками."
        ),
        reply_markup=kb_main()
    )
    await call.answer()


@dp.callback_query(F.data == "back:main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_menu(call.message)
    await call.answer()

@dp.callback_query(F.data == "back:cats")
async def back_cats(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await call.message.answer("🏷 Обери тип:", reply_markup=kb_categories())
    await call.answer()

@dp.callback_query(F.data == "back:address")
async def back_address(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.address)
    await call.message.answer("📌 Вкажи адресу (вулиця/орієнтир):")
    await call.answer()


# =========================
# Create offer
# =========================
@dp.callback_query(F.data == "offer_new")
async def offer_new(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFlow.category)
    await call.message.answer("🏷 Обери тип:", reply_markup=kb_categories())
    await call.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def choose_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":", 1)[1]
    await state.update_data(category=cat)
    await state.set_state(OfferFlow.district)
    await call.message.answer("📍 Обери район:", reply_markup=kb_areas_page(0))
    await call.answer()

@dp.callback_query(F.data.startswith("areas:"))
async def areas_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":", 1)[1])
    await call.message.answer("📍 Обери район:", reply_markup=kb_areas_page(page))
    await call.answer()

@dp.callback_query(F.data.startswith("area:"))
async def choose_area(call: CallbackQuery, state: FSMContext):
    area = call.data.split(":", 1)[1]
    if area == "manual":
        await state.set_state(OfferFlow.district_manual)
        await call.message.answer("✍️ Впиши район текстом:")
    else:
        await state.update_data(district=area)
        await state.set_state(OfferFlow.address)
        await call.message.answer("📌 Вкажи адресу (вулиця/орієнтир):")
    await call.answer()

@dp.message(OfferFlow.district_manual)
async def district_manual(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        return await message.answer("✍️ Напиши район нормально (мін. 2 символи).")
    await state.update_data(district=text)
    await state.set_state(OfferFlow.address)
    await message.answer("📌 Вкажи адресу (вулиця/орієнтир):")

@dp.message(OfferFlow.address)
async def address_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        return await message.answer("📌 Адреса занадто коротка. Спробуй ще раз.")
    await state.update_data(address=text)
    await state.set_state(OfferFlow.price)
    await message.answer("💶 Вкажи ціну (напр. 650€/міс + енергії):")

@dp.message(OfferFlow.price)
async def price_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 2:
        return await message.answer("💶 Напиши ціну (коротко).")
    await state.update_data(price=text)
    await state.set_state(OfferFlow.rooms)
    await message.answer("🛏 Кількість кімнат? (можна 1, 2, 3+ або '-' якщо не актуально)")

@dp.message(OfferFlow.rooms)
async def rooms_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) > 20:
        return await message.answer("🛏 Занадто довго. Напиши коротко.")
    await state.update_data(rooms=text if text != "-" else "")
    await state.set_state(OfferFlow.area_m2)
    await message.answer("📐 Площа м²? (наприклад 45, або '-')")

@dp.message(OfferFlow.area_m2)
async def area_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(area_m2=text if text != "-" else "")
    await state.set_state(OfferFlow.floor)
    await message.answer("🏢 Поверх? (наприклад 3/8, або '-')")

@dp.message(OfferFlow.floor)
async def floor_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(floor=text if text != "-" else "")
    await state.set_state(OfferFlow.deposit)
    await message.answer("💳 Депозит? (наприклад 1 місяць, або '-')")

@dp.message(OfferFlow.deposit)
async def deposit_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(deposit=text if text != "-" else "")
    await state.set_state(OfferFlow.available_from)
    await message.answer("📅 Вільно з якої дати? (наприклад 01.01 або 'зараз', або '-')")

@dp.message(OfferFlow.available_from)
async def avail_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(available_from=text if text != "-" else "")
    await state.set_state(OfferFlow.contact)
    await message.answer("☎️ Контакт (телефон / Telegram @username):")

@dp.message(OfferFlow.contact)
async def contact_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if len(text) < 3:
        return await message.answer("☎️ Контакт занадто короткий. Спробуй ще раз.")
    await state.update_data(contact=text)
    await state.set_state(OfferFlow.description)
    await message.answer("📝 Короткий опис (можна '-' якщо не треба):")

@dp.message(OfferFlow.description)
async def desc_step(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    await state.update_data(description="" if text == "-" else text)
    await state.update_data(photos=[])
    await state.set_state(OfferFlow.photos_collect)
    await message.answer(
        "📸 Надішли фото (до 10). Коли завершиш — натисни ✅ Готово або напиши 'готово'.",
        reply_markup=kb_photos()
    )

@dp.message(OfferFlow.photos_collect, F.photo)
async def photo_collect(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) >= 10:
        return await message.answer("📸 Вже 10 фото. Натисни ✅ Готово.")
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Фото додано ({len(photos)}/10). Можеш ще або натисни ✅ Готово.")

@dp.message(OfferFlow.photos_collect, F.text)
async def photos_done_text(message: Message, state: FSMContext):
    t = normalize_text_done(message.text)
    if t == "готово":
        return await go_next_after_photos(message, state)
    await message.answer("📸 Надішли ще фото або натисни ✅ Готово (або напиши 'готово').")

@dp.callback_query(OfferFlow.photos_collect, F.data == "photos:done")
async def photos_done_cb(call: CallbackQuery, state: FSMContext):
    await go_next_after_photos(call.message, state)
    await call.answer()

@dp.callback_query(OfferFlow.photos_collect, F.data == "photos:skip")
async def photos_skip_cb(call: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await go_next_after_photos(call.message, state)
    await call.answer()

async def go_next_after_photos(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = {
        "id": 0,
        "status": "active",
        "category": data.get("category", ""),
        "district": data.get("district", ""),
        "address": data.get("address", ""),
        "price": data.get("price", ""),
        "rooms": data.get("rooms", ""),
        "area_m2": data.get("area_m2", ""),
        "floor": data.get("floor", ""),
        "deposit": data.get("deposit", ""),
        "available_from": data.get("available_from", ""),
        "contact": data.get("contact", ""),
        "description": data.get("description", ""),
    }
    await state.set_state(OfferFlow.confirm)
    await message.answer(
        compact("✅ Перевір оголошення перед публікацією:\n\n" + render_offer_text(preview)),
        reply_markup=kb_confirm()
    )

@dp.callback_query(OfferFlow.confirm, F.data == "confirm:cancel")
async def cancel_offer(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Скасовано.", reply_markup=kb_main())
    await call.answer()

@dp.callback_query(OfferFlow.confirm, F.data == "confirm:edit_menu")
async def edit_menu(call: CallbackQuery):
    await call.message.answer(
        compact(
            "✏️ Щоб швидко відредагувати:\n"
            "— натисни ⬅️ Назад до потрібного кроку\n\n"
            "Найчастіше: адреса/ціна/контакт."
        )
    )
    await call.answer()

@dp.callback_query(OfferFlow.confirm, F.data == "confirm:publish")
async def publish_offer(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    creator = call.from_user

    payload = dict(data)
    payload["created_by"] = creator.id
    payload["created_by_name"] = creator.full_name

    offer_id = insert_offer(payload)
    offer = get_offer(offer_id)

    # send to group (photos if exist)
    text = render_offer_text(offer)
    photos = (offer.get("photos") or "").split(",") if offer.get("photos") else []
    photos = [p for p in photos if p.strip()]

    if photos:
        # send first photo with caption
        msg = await bot.send_photo(
            chat_id=GROUP_ID_INT,
            photo=photos[0],
            caption=text,
            reply_markup=kb_status_controls(offer_id)
        )
        # send rest photos
        for p in photos[1:]:
            await bot.send_photo(chat_id=GROUP_ID_INT, photo=p)
    else:
        msg = await bot.send_message(
            chat_id=GROUP_ID_INT,
            text=text,
            reply_markup=kb_status_controls(offer_id)
        )

    update_offer(offer_id, {"group_message_id": msg.message_id})

    await state.clear()
    await call.message.answer(
        compact(f"✅ Опубліковано в групі.\nID оголошення: **#{offer_id}**"),
        reply_markup=kb_main()
    )
    await call.answer()


# =========================
# Status change in group
# =========================
@dp.callback_query(F.data.startswith("st:"))
async def status_change(call: CallbackQuery):
    # st:{offer_id}:{status}
    try:
        _, offer_id_s, st = call.data.split(":", 2)
        offer_id = int(offer_id_s)
    except Exception:
        await call.answer("Помилка.", show_alert=True)
        return

    offer = get_offer(offer_id)
    if not offer:
        await call.answer("Оголошення не знайдено.", show_alert=True)
        return

    # Admin policy:
    # - якщо ADMIN_IDS задані -> тільки адміни можуть міняти
    # - якщо не задані -> дозволимо всім (простий режим)
    if ADMIN_IDS and not is_admin(call.from_user.id):
        await call.answer("Тільки адмініни можуть змінювати статус.", show_alert=True)
        return

    if st not in STATUS_UA:
        await call.answer("Невідомий статус.", show_alert=True)
        return

    update_offer(offer_id, {"status": st})
    offer = get_offer(offer_id)

    new_text = render_offer_text(offer)
    # update message text/caption in group
    try:
        # if message has caption (photo message), edit_caption; else edit_text
        if call.message.photo:
            await call.message.edit_caption(new_text, reply_markup=kb_status_controls(offer_id))
        else:
            await call.message.edit_text(new_text, reply_markup=kb_status_controls(offer_id))
    except Exception:
        # niekedy Telegram nedovolí edit podľa typu správy, tak aspoň odpoveď
        pass

    await call.answer(f"Статус: {STATUS_UA[st]}")


# =========================
# Edit in DM
# =========================
@dp.callback_query(F.data.startswith("edit:"))
async def edit_offer_from_group(call: CallbackQuery, state: FSMContext):
    try:
        offer_id = int(call.data.split(":", 1)[1])
    except Exception:
        return await call.answer("Помилка.", show_alert=True)

    offer = get_offer(offer_id)
    if not offer:
        return await call.answer("Не знайдено.", show_alert=True)

    # Only creator or admin
    if call.from_user.id != offer["created_by"] and (ADMIN_IDS and not is_admin(call.from_user.id)):
        return await call.answer("Немає доступу.", show_alert=True)

    await bot.send_message(
        call.from_user.id,
        compact(
            f"✏️ Редагування оголошення **#{offer_id}**\n\n"
            "Напиши команду:\n"
            f"`/edit {offer_id}`\n\n"
            "Або відкрий меню: 📋 Мої оголошення"
        )
    )
    await call.answer("Я написав тобі в приват.")


@dp.callback_query(F.data == "my_offers")
async def my_offers(call: CallbackQuery):
    offers = list_offers_by_user(call.from_user.id)
    if not offers:
        await call.message.answer("📋 У тебе ще немає оголошень.", reply_markup=kb_main())
        await call.answer()
        return

    lines = ["📋 **Мої оголошення:**"]
    for o in offers[:20]:
        lines.append(f"• #{o['id']} — {STATUS_UA.get(o['status'], o['status'])} — {o['district']} — {o['price']}")
    lines.append("\nЩоб редагувати: `/edit ID` (наприклад `/edit 12`).")

    await call.message.answer(compact("\n".join(lines)), reply_markup=kb_main())
    await call.answer()


@dp.message(F.text.regexp(r"^/edit\s+\d+"))
async def edit_cmd(message: Message, state: FSMContext):
    offer_id = int(message.text.strip().split()[1])
    offer = get_offer(offer_id)
    if not offer:
        return await message.answer("❌ Оголошення не знайдено.")

    if message.from_user.id != offer["created_by"] and (ADMIN_IDS and not is_admin(message.from_user.id)):
        return await message.answer("❌ Немає доступу до цього оголошення.")

    await state.clear()
    await state.set_state(EditFlow.offer_id)
    await state.update_data(offer_id=offer_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💶 Ціна", callback_data="ef:price")],
        [InlineKeyboardButton(text="📍 Район", callback_data="ef:district")],
        [InlineKeyboardButton(text="📌 Адреса", callback_data="ef:address")],
        [InlineKeyboardButton(text="☎️ Контакт", callback_data="ef:contact")],
        [InlineKeyboardButton(text="📝 Опис", callback_data="ef:description")],
        [InlineKeyboardButton(text="🟢/🟡/🔴 Статус", callback_data="ef:status")],
        [InlineKeyboardButton(text="❌ Закрити", callback_data="ef:close")],
    ])

    await message.answer(
        compact(f"✏️ Обери що змінити в оголошенні **#{offer_id}**:"),
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("ef:"))
async def edit_field(call: CallbackQuery, state: FSMContext):
    field = call.data.split(":", 1)[1]
    data = await state.get_data()
    offer_id = data.get("offer_id")

    if field == "close":
        await state.clear()
        await call.message.answer("✅ Готово.", reply_markup=kb_main())
        return await call.answer()

    await state.set_state(EditFlow.field)
    await state.update_data(field=field)

    if field == "status":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Активна", callback_data="efs:active")],
            [InlineKeyboardButton(text="🟡 Резерв", callback_data="efs:reserve")],
            [InlineKeyboardButton(text="🔴 Здано", callback_data="efs:rented")],
        ])
        await call.message.answer("Обери статус:", reply_markup=kb)
        await call.answer()
        return

    prompt = {
        "price": "💶 Впиши нову ціну:",
        "district": "📍 Впиши новий район:",
        "address": "📌 Впиши нову адресу:",
        "contact": "☎️ Впиши новий контакт:",
        "description": "📝 Впиши новий опис (або '-' щоб очистити):",
    }.get(field, "Впиши значення:")

    await call.message.answer(prompt)
    await call.answer()

@dp.callback_query(F.data.startswith("efs:"))
async def edit_status_pick(call: CallbackQuery, state: FSMContext):
    st = call.data.split(":", 1)[1]
    data = await state.get_data()
    offer_id = data.get("offer_id")
    if not offer_id:
        await call.answer("Немає ID.", show_alert=True)
        return

    update_offer(int(offer_id), {"status": st})
    await call.message.answer(f"✅ Статус змінено на: {STATUS_UA[st]}")

    # try update group message too
    offer = get_offer(int(offer_id))
    if offer and offer.get("group_message_id"):
        try:
            msg_id = int(offer["group_message_id"])
            new_text = render_offer_text(offer)
            # We don't know if it was photo/caption; safest: send a new update message in group
            await bot.send_message(
                GROUP_ID_INT,
                compact(f"🔁 Оновлено оголошення #{offer_id}\n\n{new_text}"),
                reply_markup=kb_status_controls(int(offer_id))
            )
        except Exception:
            pass

    await call.answer("OK")

@dp.message(EditFlow.field)
async def edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    offer_id = int(data.get("offer_id", 0))
    field = data.get("field")

    offer = get_offer(offer_id)
    if not offer:
        await state.clear()
        return await message.answer("❌ Оголошення не знайдено.")

    if message.from_user.id != offer["created_by"] and (ADMIN_IDS and not is_admin(message.from_user.id)):
        await state.clear()
        return await message.answer("❌ Немає доступу.")

    val = (message.text or "").strip()

    if field == "description" and val == "-":
        val = ""

    if field not in {"price", "district", "address", "contact", "description"}:
        await state.clear()
        return await message.answer("❌ Невірне поле.")

    update_offer(offer_id, {field: val})
    await message.answer(f"✅ Оновлено: {field}")

    # Optional: send updated message to group
    offer = get_offer(offer_id)
    if offer and offer.get("group_message_id"):
        try:
            new_text = render_offer_text(offer)
            await bot.send_message(
                GROUP_ID_INT,
                compact(f"🔁 Оновлено оголошення #{offer_id}\n\n{new_text}"),
                reply_markup=kb_status_controls(offer_id)
            )
        except Exception:
            pass

    await state.clear()
    await message.answer("✅ Готово.", reply_markup=kb_main())


# =========================
# Run
# =========================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
