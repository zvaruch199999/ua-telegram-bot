import asyncio
import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, GROUP_CHAT_ID, ADMIN_USER_IDS
from states import CreateOffer, EditOffer
from keyboards import (
    kb_category, kb_housing_type, kb_done_photos,
    kb_preview_actions, kb_status, kb_back_to_preview
)
from database import (
    init_db, create_listing, get_listing, update_field, add_photo, clear_photos,
    set_group_message, set_status, delete_listing,
    STATUS_LABELS, STATUS_DRAFT, STATUS_ACTIVE, STATUS_RESERVE, STATUS_WITHDRAWN, STATUS_CLOSED,
    stats_period
)

router = Router()

FIELDS = [
    ("category",        "🏷 Категорія"),
    ("housing_type",    "🏠 Тип житла"),
    ("street",          "📍 Вулиця"),
    ("city",            "🏙 Місто"),
    ("district",        "🗺 Район"),
    ("advantages",      "✨ Переваги"),
    ("rent",            "💶 Оренда"),
    ("deposit",         "🔐 Депозит"),
    ("commission",      "🤝 Комісія"),
    ("parking",         "🚗 Паркінг"),
    ("settlement_from", "📦 Заселення від"),
    ("viewings_from",   "👀 Огляди від"),
    ("broker",          "🧑 Маклер"),
]

EDIT_MAP = {i+1: key for i, (key, _) in enumerate([f[0] for f in FIELDS if f[0] != "broker"])}
# broker редагувати не даємо через номер, він ставиться автоматично

def broker_name(m: Message) -> str:
    if m.from_user.username:
        return f"@{m.from_user.username}"
    return (m.from_user.full_name or "—").strip()

def offer_text(listing: dict) -> str:
    number = listing["number"]
    status = STATUS_LABELS.get(listing["status"], listing["status"])
    lines = [
        f"🏡 <b>ПРОПОЗИЦІЯ #{number:04d}</b>",
        f"📊 <b>Статус:</b> {status}",
        "",
    ]
    for key, label in FIELDS:
        val = (listing.get(key) or "").strip()
        if not val:
            val = "—"
        # broker завжди показуємо
        lines.append(f"{label}: {val}")
    return "\n".join(lines)

async def send_preview(bot: Bot, chat_id: int, listing: dict):
    photos = json.loads(listing["photos_json"] or "[]")
    if photos:
        media = [InputMediaPhoto(media=p) for p in photos[:10]]
        await bot.send_media_group(chat_id=chat_id, media=media)
    await bot.send_message(
        chat_id=chat_id,
        text="👉 <b>Це фінальний вигляд пропозиції</b>\n\n" + offer_text(listing),
        reply_markup=kb_preview_actions(listing["number"])
    )

def is_admin(user_id: int) -> bool:
    return (not ADMIN_USER_IDS) or (user_id in ADMIN_USER_IDS)

@router.message(Command("start"))
async def cmd_start(m: Message):
    if not is_admin(m.from_user.id):
        return await m.answer("⛔️ Нема доступу.")
    await m.answer(
        "✅ Бот працює.\n\n"
        "Команди:\n"
        "• /new — створити пропозицію\n"
        "• /stats — статистика\n"
        "• /export — експорт CSV\n\n"
        "Можна також написати: <b>Зробити пропозицію</b>",
        parse_mode="HTML"
    )

@router.message(Command("new"))
async def cmd_new(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return await m.answer("⛔️ Нема доступу.")
    await state.clear()
    num = await create_listing(broker_name(m))
    await state.update_data(number=num)
    await state.set_state(CreateOffer.category)
    await m.answer(f"📝 Створюємо пропозицію <b>#{num:04d}</b>\n\nОбери категорію:", reply_markup=kb_category())

@router.message(F.text.lower().contains("зробити пропозицію"))
async def text_new(m: Message, state: FSMContext):
    await cmd_new(m, state)

@router.callback_query(F.data.startswith("cat:"))
async def cb_cat(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    number = data.get("number")
    if not number:
        return await c.answer("Нема активної пропозиції.")
    val = c.data.split(":", 1)[1]
    if val == "__custom__":
        await c.message.answer("Введи категорію текстом:")
        await state.update_data(_custom_field="category")
        await state.set_state(CreateOffer.category)  # лишаємось, але чекаємо текст
        await c.answer()
        return
    await update_field(number, "category", val)
    await state.set_state(CreateOffer.housing_type)
    await c.message.edit_text("Обери тип житла:", reply_markup=kb_housing_type())
    await c.answer()

@router.callback_query(F.data.startswith("type:"))
async def cb_type(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    number = data.get("number")
    if not number:
        return await c.answer("Нема активної пропозиції.")
    val = c.data.split(":", 1)[1]
    if val == "__custom__":
        await state.set_state(CreateOffer.housing_type_custom)
        await c.message.edit_text("Введи тип житла текстом (наприклад: Студія / Апарт / ...):")
        await c.answer()
        return
    await update_field(number, "housing_type", val)
    await state.set_state(CreateOffer.street)
    await c.message.edit_text("📍 Вулиця (можна — якщо не хочеш вказувати):")
    await c.answer()

@router.message(CreateOffer.housing_type_custom)
async def st_type_custom(m: Message, state: FSMContext):
    number = (await state.get_data()).get("number")
    if not number:
        return
    await update_field(number, "housing_type", m.text.strip())
    await state.set_state(CreateOffer.street)
    await m.answer("📍 Вулиця (можна — якщо не хочеш вказувати):")

@router.message(CreateOffer.category)
async def st_category_custom(m: Message, state: FSMContext):
    # якщо користувач вводить категорію вручну після cat:__custom__
    data = await state.get_data()
    number = data.get("number")
    if not number:
        return
    await update_field(number, "category", m.text.strip())
    await state.set_state(CreateOffer.housing_type)
    await m.answer("Обери тип житла:", reply_markup=kb_housing_type())

async def _simple_field_handler(m: Message, state: FSMContext, field: str, next_state):
    number = (await state.get_data()).get("number")
    if not number:
        return
    txt = m.text.strip()
    await update_field(number, field, "" if txt == "—" else txt)
    await state.set_state(next_state)

@router.message(CreateOffer.street)
async def st_street(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "street", CreateOffer.city)
    await m.answer("🏙 Місто (можна —):")

@router.message(CreateOffer.city)
async def st_city(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "city", CreateOffer.district)
    await m.answer("🗺 Район (можна —):")

@router.message(CreateOffer.district)
async def st_district(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "district", CreateOffer.advantages)
    await m.answer("✨ Переваги (можна —):")

@router.message(CreateOffer.advantages)
async def st_adv(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "advantages", CreateOffer.rent)
    await m.answer("💶 Оренда (наприклад 350€ або —):")

@router.message(CreateOffer.rent)
async def st_rent(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "rent", CreateOffer.deposit)
    await m.answer("🔐 Депозит (наприклад 350€ або —):")

@router.message(CreateOffer.deposit)
async def st_dep(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "deposit", CreateOffer.commission)
    await m.answer("🤝 Комісія (наприклад 350€ або —):")

@router.message(CreateOffer.commission)
async def st_com(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "commission", CreateOffer.parking)
    await m.answer("🚗 Паркінг (Є/Нема або —):")

@router.message(CreateOffer.parking)
async def st_parking(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "parking", CreateOffer.settlement_from)
    await m.answer("📦 Заселення від (наприклад Вже / дата / —):")

@router.message(CreateOffer.settlement_from)
async def st_settle(m: Message, state: FSMContext):
    await _simple_field_handler(m, state, "settlement_from", CreateOffer.viewings_from)
    await m.answer("👀 Огляди від (наприклад Вже / дата / —):")

@router.message(CreateOffer.viewings_from)
async def st_view(m: Message, state: FSMContext):
    number = (await state.get_data()).get("number")
    if not number:
        return
    txt = m.text.strip()
    await update_field(number, "viewings_from", "" if txt == "—" else txt)
    # broker ставимо автоматично
    await update_field(number, "broker", broker_name(m))

    await clear_photos(number)
    await state.set_state(CreateOffer.photos)

    await m.answer(
        "📸 Надішли фото.\nКоли закінчиш — натисни кнопку <b>✅ Готово</b> або напиши /done",
        reply_markup=kb_done_photos(number)
    )

@router.message(Command("done"))
async def cmd_done(m: Message, state: FSMContext):
    data = await state.get_data()
    number = data.get("number")
    if not number:
        return
    if (await state.get_state()) != CreateOffer.photos.state:
        return
    listing = await get_listing(number)
    if not listing:
        return
    await state.set_state(CreateOffer.preview)
    await send_preview(m.bot, m.chat.id, listing)

@router.callback_query(F.data.startswith("photos_done:"))
async def cb_photos_done(c: CallbackQuery, state: FSMContext):
    number = int(c.data.split(":")[1])
    data = await state.get_data()
    if data.get("number") != number:
        await c.answer("Це не твоя активна пропозиція.")
        return

    if (await state.get_state()) != CreateOffer.photos.state:
        await c.answer("Фото вже завершені.")
        return

    listing = await get_listing(number)
    if not listing:
        await c.answer("Пропозицію не знайдено.")
        return

    await state.set_state(CreateOffer.preview)
    await c.answer("Готово!")
    await send_preview(c.bot, c.message.chat.id, listing)

@router.message(CreateOffer.photos, F.photo)
async def st_photos(m: Message, state: FSMContext):
    number = (await state.get_data()).get("number")
    if not number:
        return
    # Беремо найбільший розмір
    file_id = m.photo[-1].file_id
    await add_photo(number, file_id)

    listing = await get_listing(number)
    photos = json.loads(listing["photos_json"] or "[]")
    await m.answer(f"📸 Фото додано ({len(photos)}).", reply_markup=kb_done_photos(number))

@router.message(CreateOffer.photos)
async def st_photos_other(m: Message, state: FSMContext):
    # щоб не “зациклювало” на /done скріном — відповідаємо коротко
    if m.text and m.text.strip().lower() in ("готово",):
        return await cmd_done(m, state)
    await m.answer("Надішли фото або /done щоб завершити.", reply_markup=kb_done_photos((await state.get_data()).get("number", 0)))

@router.callback_query(F.data.startswith("preview:"))
async def cb_preview(c: CallbackQuery, state: FSMContext):
    number = int(c.data.split(":")[1])
    listing = await get_listing(number)
    if not listing:
        return await c.answer("Не знайдено.")
    await c.message.answer("👉 <b>Превʼю</b>\n\n" + offer_text(listing), reply_markup=kb_preview_actions(number))
    await c.answer()

@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(c: CallbackQuery, state: FSMContext):
    number = int(c.data.split(":")[1])
    await delete_listing(number)
    await state.clear()
    await c.message.edit_text("❌ Чернетку скасовано.")
    await c.answer()

@router.callback_query(F.data.startswith("publish:"))
async def cb_publish(c: CallbackQuery, state: FSMContext):
    number = int(c.data.split(":")[1])
    listing = await get_listing(number)
    if not listing:
        return await c.answer("Не знайдено.")

    photos = json.loads(listing["photos_json"] or "[]")

    # 1) Фото-альбом у групу
    if photos:
        media = [InputMediaPhoto(media=p) for p in photos[:10]]
        await c.bot.send_media_group(chat_id=GROUP_CHAT_ID, media=media)

    # 2) Окреме повідомлення з текстом + кнопки статусів
    msg = await c.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=offer_text(listing),
        reply_markup=kb_status(number),
        disable_web_page_preview=True
    )

    await set_group_message(number, GROUP_CHAT_ID, msg.message_id)

    # після публікації ставимо "Актуально" як старт (або лишаємо Чернетку — але в групі краще одразу Актуально)
    await set_status(number, STATUS_ACTIVE, broker_name(c.message))

    # оновимо текст у групі, щоб статус одразу був 🟢
    listing = await get_listing(number)
    await c.bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=msg.message_id,
        text=offer_text(listing),
        reply_markup=kb_status(number),
        disable_web_page_preview=True
    )

    await state.clear()
    await c.message.edit_text(f"✅ Пропозицію <b>#{number:04d}</b> опубліковано в групу.")
    await c.answer()

@router.callback_query(F.data.startswith("st:"))
async def cb_status(c: CallbackQuery):
    # працює в групі
    _, num_s, st = c.data.split(":")
    number = int(num_s)

    listing = await get_listing(number)
    if not listing:
        return await c.answer("Не знайдено.")

    who = broker_name(c.message)  # у callback message.from_user — не завжди доступний; беремо через c.from_user
    if c.from_user.username:
        who = f"@{c.from_user.username}"
    else:
        who = c.from_user.full_name or "—"

    # Визначаємо статус
    new_status = {
        "ACTIVE": STATUS_ACTIVE,
        "RESERVE": STATUS_RESERVE,
        "WITHDRAWN": STATUS_WITHDRAWN,
        "CLOSED": STATUS_CLOSED,
    }.get(st)

    if not new_status:
        return await c.answer("Невідомий статус.")

    await set_status(number, new_status, who)
    listing = await get_listing(number)

    # Редагуємо те саме повідомлення — нічого не зникає
    await c.bot.edit_message_text(
        chat_id=c.message.chat.id,
        message_id=c.message.message_id,
        text=offer_text(listing),
        reply_markup=kb_status(number),
        disable_web_page_preview=True
    )

    await c.answer("Оновлено ✅")

@router.callback_query(F.data.startswith("edit:"))
async def cb_edit(c: CallbackQuery, state: FSMContext):
    number = int(c.data.split(":")[1])
    listing = await get_listing(number)
    if not listing:
        return await c.answer("Не знайдено.")
    await state.clear()
    await state.set_state(EditOffer.pick_field)
    await state.update_data(number=number)

    # список 1-12 (без брокера)
    lines = [f"✏️ <b>Редагування #{number:04d}</b>\nНапиши номер пункту 1–12:"]
    idx = 1
    for key, label in FIELDS:
        if key == "broker":
            continue
        lines.append(f"{idx}. {label.replace('🏷 ','').replace('🏠 ','').replace('📍 ','').replace('🏙 ','').replace('🗺 ','').replace('✨ ','').replace('💶 ','').replace('🔐 ','').replace('🤝 ','').replace('🚗 ','').replace('📦 ','').replace('👀 ','')}")
        idx += 1

    await c.message.edit_text("\n".join(lines))
    await c.answer()

@router.message(EditOffer.pick_field)
async def edit_pick(m: Message, state: FSMContext):
    data = await state.get_data()
    number = data.get("number")
    if not number:
        return await state.clear()

    txt = (m.text or "").strip()
    if not txt.isdigit():
        return await m.answer("Введи номер пункту (1–12).")

    n = int(txt)
    if n < 1 or n > 12:
        return await m.answer("Номер має бути 1–12.")

    field = list(EDIT_MAP.values())[n-1]
    await state.update_data(field=field)
    await state.set_state(EditOffer.new_value)

    # підказка
    label = dict(FIELDS).get(field, field)
    await m.answer(f"Введи нове значення для: {label}\n(або — щоб очистити)")

@router.message(EditOffer.new_value)
async def edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    number = data.get("number")
    field = data.get("field")
    if not number or not field:
        return await state.clear()

    val = (m.text or "").strip()
    if val == "—":
        val = ""

    await update_field(number, field, val)

    listing = await get_listing(number)
    await state.clear()
    await m.answer("✅ Оновлено.\n\n" + offer_text(listing), reply_markup=kb_preview_actions(number))

@router.message(Command("stats"))
async def cmd_stats(m: Message):
    # періоди: день/місяць/рік (UTC)
    now = datetime.now(timezone.utc)

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    month_start = day_start.replace(day=1)
    # наступний місяць:
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year+1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month+1)

    year_start = day_start.replace(month=1, day=1)
    year_end = year_start.replace(year=year_start.year+1)

    totals_d, brokers_d = await stats_period(day_start.isoformat(), day_end.isoformat())
    totals_m, brokers_m = await stats_period(month_start.isoformat(), month_end.isoformat())
    totals_y, brokers_y = await stats_period(year_start.isoformat(), year_end.isoformat())

    def fmt_totals(title, totals):
        return (
            f"<b>{title}</b>\n"
            f"🟢 Актуально: {totals.get(STATUS_ACTIVE, 0)}\n"
            f"🟡 Резерв: {totals.get(STATUS_RESERVE, 0)}\n"
            f"⚫️ Знято: {totals.get(STATUS_WITHDRAWN, 0)}\n"
            f"✅ Угода закрита: {totals.get(STATUS_CLOSED, 0)}\n"
        )

    def fmt_brokers(title, brokers):
        lines = [f"<b>{title}</b>"]
        if not brokers:
            lines.append("— немає змін")
            return "\n".join(lines)
        for who, mp in brokers.items():
            lines.append(
                f"{who}: "
                f"🟢{mp.get(STATUS_ACTIVE,0)}  "
                f"🟡{mp.get(STATUS_RESERVE,0)}  "
                f"⚫️{mp.get(STATUS_WITHDRAWN,0)}  "
                f"✅{mp.get(STATUS_CLOSED,0)}"
            )
        return "\n".join(lines)

    text = (
        "📊 <b>Статистика</b>\n\n" +
        fmt_totals(f"День ({day_start.date()})", totals_d) + "\n" +
        fmt_totals(f"Місяць ({month_start.strftime('%Y-%m')})", totals_m) + "\n" +
        fmt_totals(f"Рік ({year_start.year})", totals_y) + "\n" +
        "🧑‍💼 <b>Хто скільки міняв статусів (по статусах)</b>\n\n" +
        fmt_brokers(f"День ({day_start.date()})", brokers_d) + "\n\n" +
        fmt_brokers(f"Місяць ({month_start.strftime('%Y-%m')})", brokers_m) + "\n\n" +
        fmt_brokers(f"Рік ({year_start.year})", brokers_y)
    )
    await m.answer(text, parse_mode="HTML")

@router.message(F.text.lower().contains("статистика"))
async def text_stats(m: Message):
    await cmd_stats(m)

@router.message(Command("export"))
async def cmd_export(m: Message):
    """
    Простий експорт CSV без openpyxl.
    """
    import csv
    import os
    from database import DB_PATH
    import aiosqlite

    path = "data/export.csv"
    os.makedirs("data", exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM listings ORDER BY number DESC")
        rows = await cur.fetchall()
        await cur.close()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "number","status","category","housing_type","street","city","district","advantages",
            "rent","deposit","commission","parking","settlement_from","viewings_from","broker",
            "created_at","updated_at"
        ])
        for r in rows:
            w.writerow([
                r["number"], r["status"], r["category"], r["housing_type"], r["street"], r["city"],
                r["district"], r["advantages"], r["rent"], r["deposit"], r["commission"], r["parking"],
                r["settlement_from"], r["viewings_from"], r["broker"], r["created_at"], r["updated_at"]
            ])

    await m.answer_document(open(path, "rb"), caption="📄 Export CSV")

async def main():
    await init_db()

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
