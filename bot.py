import asyncio
import logging
from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InputMediaPhoto
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, GROUP_CHAT_ID, DB_PATH
from states import OfferForm
from keyboards import (
    main_menu, category_kb, living_type_kb, preview_kb,
    edit_fields_kb, status_kb
)
from database import (
    init_db, create_offer, get_offer, update_offer_fields, change_status,
    set_group_message, build_stats_text,
    STATUS_ACTIVE, STATUS_RESERVED, STATUS_CLOSED, STATUS_REMOVED
)

logging.basicConfig(level=logging.INFO)
router = Router()


def offer_num(offer_id: int) -> str:
    return f"#{offer_id:04d}"


def status_label(status: str) -> str:
    if status == STATUS_ACTIVE:
        return "🟢 Актуально"
    if status == STATUS_RESERVED:
        return "🟡 Резерв"
    if status == STATUS_CLOSED:
        return "✅ Закрито"
    if status == STATUS_REMOVED:
        return "🔴 Знято"
    return status


def build_offer_text(oid: int, data: dict) -> str:
    # без слова "неактуально" взагалі
    cat = data.get("category") or "—"
    lt = data.get("living_type") or "—"
    street = data.get("street") or "—"
    city = data.get("city") or "—"
    district = data.get("district") or "—"
    adv = data.get("advantages") or "—"
    price = data.get("price") or "—"
    dep = data.get("deposit") or "—"
    com = data.get("commission") or "—"
    park = data.get("parking") or "—"
    move_in = data.get("move_in") or "—"
    viewings = data.get("viewings") or "—"
    broker = data.get("broker") or "—"
    status = data.get("status") or STATUS_ACTIVE

    return (
        f"🏡 <b>НОВА ПРОПОЗИЦІЯ {offer_num(oid)}</b>\n"
        f"📍 <b>Статус:</b> {status_label(status)}\n\n"
        f"🏷️ <b>Категорія:</b> {cat}\n"
        f"🏠 <b>Тип:</b> {lt}\n"
        f"📌 <b>Адреса:</b> {street}, {city}\n"
        f"🗺️ <b>Район:</b> {district}\n"
        f"✨ <b>Переваги:</b> {adv}\n"
        f"💶 <b>Ціна:</b> {price}\n"
        f"🔐 <b>Депозит:</b> {dep}\n"
        f"🤝 <b>Комісія:</b> {com}\n"
        f"🚗 <b>Паркінг:</b> {park}\n"
        f"🗓️ <b>Заселення від:</b> {move_in}\n"
        f"👀 <b>Огляди від:</b> {viewings}\n"
        f"👤 <b>Маклер:</b> {broker}\n"
    )


async def send_album(chat_id: int, bot: Bot, photo_ids: list[str]):
    if not photo_ids:
        return
    media = [InputMediaPhoto(media=pid) for pid in photo_ids[:10]]  # Telegram обмеження
    await bot.send_media_group(chat_id=chat_id, media=media)


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привіт! Обери дію нижче 👇",
        reply_markup=main_menu()
    )


@router.callback_query(F.data == "stats")
async def stats_cb(call: CallbackQuery):
    text = await build_stats_text(DB_PATH, date.today())
    await call.message.answer(text)
    await call.answer()


@router.message(Command("stats"))
async def stats_cmd(message: Message):
    text = await build_stats_text(DB_PATH, date.today())
    await message.answer(text)


@router.callback_query(F.data == "create_offer")
async def create_offer_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferForm.category)
    await call.message.answer("🏷️ Обери категорію:", reply_markup=category_kb())
    await call.answer()


@router.callback_query(F.data.startswith("cat:"))
async def category_chosen(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]
    category = "Оренда" if val == "rent" else "Продаж"
    await state.update_data(category=category)
    await state.set_state(OfferForm.living_type)
    await call.message.answer("🏠 Обери тип житла:", reply_markup=living_type_kb())
    await call.answer()


@router.callback_query(F.data.startswith("type:"))
async def type_chosen(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]
    mapping = {"room": "Кімната", "flat": "Квартира", "house": "Будинок"}
    await state.update_data(living_type=mapping.get(val, val))
    await state.set_state(OfferForm.street)
    await call.message.answer("📌 Вулиця (наприклад: Грабова):")
    await call.answer()


@router.message(OfferForm.street)
async def street_step(message: Message, state: FSMContext):
    await state.update_data(street=message.text.strip())
    await state.set_state(OfferForm.city)
    await message.answer("🏙️ Місто (наприклад: Братислава):")


@router.message(OfferForm.city)
async def city_step(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(OfferForm.district)
    await message.answer("🗺️ Район (наприклад: Дубравка):")


@router.message(OfferForm.district)
async def district_step(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(OfferForm.advantages)
    await message.answer("✨ Переваги (коротко, можна через кому):")


@router.message(OfferForm.advantages)
async def adv_step(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text.strip())
    await state.set_state(OfferForm.price)
    await message.answer("💶 Ціна / Оренда (наприклад: 350€):")


@router.message(OfferForm.price)
async def price_step(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(OfferForm.deposit)
    await message.answer("🔐 Депозит (наприклад: 350€):")


@router.message(OfferForm.deposit)
async def dep_step(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text.strip())
    await state.set_state(OfferForm.commission)
    await message.answer("🤝 Комісія (наприклад: 98€ або 350€):")


@router.message(OfferForm.commission)
async def com_step(message: Message, state: FSMContext):
    await state.update_data(commission=message.text.strip())
    await state.set_state(OfferForm.parking)
    await message.answer("🚗 Паркінг (Є / Немає):")


@router.message(OfferForm.parking)
async def parking_step(message: Message, state: FSMContext):
    await state.update_data(parking=message.text.strip())
    await state.set_state(OfferForm.move_in)
    await message.answer("🗓️ Заселення від (наприклад: Вже / 01.01):")


@router.message(OfferForm.move_in)
async def move_in_step(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text.strip())
    await state.set_state(OfferForm.viewings)
    await message.answer("👀 Огляди від (наприклад: Вже / з 18:00):")


@router.message(OfferForm.viewings)
async def view_step(message: Message, state: FSMContext):
    await state.update_data(viewings=message.text.strip())
    await state.set_state(OfferForm.broker)
    await message.answer("👤 Маклер (нік, наприклад: @zvarych1):")


@router.message(OfferForm.broker)
async def broker_step(message: Message, state: FSMContext):
    await state.update_data(broker=message.text.strip())
    await state.update_data(photos=[])
    await state.set_state(OfferForm.photos)
    await message.answer("📸 Надішли фото. Коли закінчиш — напиши команду: /done")


@router.message(Command("done"))
async def done_photos(message: Message, state: FSMContext, bot: Bot):
    if await state.get_state() != OfferForm.photos.state:
        return

    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await message.answer("⚠️ Немає фото. Надішли хоча б 1 фото, або напиши /cancel")
        return

    data["status"] = STATUS_ACTIVE

    # PREVIEW в боті: альбом + картка + кнопки publish/edit
    await send_album(message.chat.id, bot, photos)

    preview_text = (
        "👇 <b>Це фінальний вигляд пропозиції (перед публікацією)</b>\n\n"
        + build_offer_text(0, data).replace("#0000", "#—")
    )
    msg = await message.answer(preview_text, reply_markup=preview_kb())
    await state.update_data(preview_msg_id=msg.message_id)
    await state.set_state(OfferForm.preview)


@router.message(OfferForm.photos)
async def photo_collector(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Надішли фото або /done щоб завершити.")
        return
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(photo_id)
    await state.update_data(photos=photos)
    await message.answer(f"📷 Фото додано ({len(photos)})")


@router.callback_query(F.data == "edit")
async def edit_cb(call: CallbackQuery, state: FSMContext):
    if await state.get_state() != OfferForm.preview.state:
        await call.answer("Спочатку створи пропозицію.")
        return
    await state.set_state(OfferForm.edit_choose)
    await call.message.answer(
        "✏️ <b>Редагування</b>\nОбери поле кнопкою нижче (або можеш написати цифру 2–14):",
        reply_markup=edit_fields_kb()
    )
    await call.answer()


FIELD_MAP_BY_NUMBER = {
    "2": "category",
    "3": "living_type",
    "4": "street",
    "5": "city",
    "6": "district",
    "7": "advantages",
    "8": "price",
    "9": "deposit",
    "10": "commission",
    "11": "parking",
    "12": "move_in",
    "13": "viewings",
    "14": "broker",
}


@router.message(OfferForm.edit_choose)
async def edit_choose_text(message: Message, state: FSMContext):
    # якщо користувач вводить цифру (як у твоєму скріні)
    key = FIELD_MAP_BY_NUMBER.get(message.text.strip())
    if not key:
        await message.answer("Напиши цифру 2–14 або натисни кнопку.")
        return
    await state.update_data(edit_field=key)
    await state.set_state(OfferForm.edit_value)
    await message.answer("Введи нове значення для цього пункту:")


@router.callback_query(F.data.startswith("editfield:"))
async def edit_choose_btn(call: CallbackQuery, state: FSMContext):
    if await state.get_state() != OfferForm.edit_choose.state:
        await call.answer()
        return
    key = call.data.split(":", 1)[1]
    await state.update_data(edit_field=key)
    await state.set_state(OfferForm.edit_value)
    await call.message.answer("Введи нове значення для цього пункту:")
    await call.answer()


@router.callback_query(F.data == "back_to_preview")
async def back_to_preview(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferForm.preview)
    await call.message.answer("Повернув у превʼю. Можеш Опублікувати або ще Редагувати.", reply_markup=preview_kb())
    await call.answer()


@router.message(OfferForm.edit_value)
async def edit_value_step(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("edit_field")
    if not key:
        await state.set_state(OfferForm.preview)
        await message.answer("Помилка редагування. Повернув у превʼю.", reply_markup=preview_kb())
        return

    await state.update_data(**{key: message.text.strip()})
    await state.set_state(OfferForm.preview)

    new_data = await state.get_data()
    new_data["status"] = STATUS_ACTIVE

    preview_text = (
        "✅ <b>Оновлено!</b>\n\n"
        + build_offer_text(0, new_data).replace("#0000", "#—")
    )
    await message.answer(preview_text, reply_markup=preview_kb())


@router.callback_query(F.data == "publish")
async def publish_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    if await state.get_state() != OfferForm.preview.state:
        await call.answer("Немає превʼю для публікації.")
        return

    data = await state.get_data()
    photos = data.get("photos", [])
    if not photos:
        await call.message.answer("⚠️ Немає фото. Повернись і додай фото.")
        await call.answer()
        return

    if GROUP_CHAT_ID is None:
        await call.message.answer("⚠️ Не задано GROUP_CHAT_ID у змінних Railway. Додай і перезапусти.")
        await call.answer()
        return

    data["status"] = STATUS_ACTIVE

    # створюємо офер в БД
    oid = await create_offer(DB_PATH, data)

    # 1) в групу альбом
    await send_album(GROUP_CHAT_ID, bot, photos)

    # 2) в групу текст з кнопками статусів (кнопки НЕ пропадають)
    text = build_offer_text(oid, {**data, "status": STATUS_ACTIVE})
    msg = await bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        reply_markup=status_kb(oid),
        disable_web_page_preview=True
    )
    await set_group_message(DB_PATH, oid, GROUP_CHAT_ID, msg.message_id)

    await call.message.answer(f"✅ Пропозицію {offer_num(oid)} опубліковано в групу.")
    await state.clear()
    await call.answer()


@router.callback_query(F.data.startswith("status:"))
async def status_change_cb(call: CallbackQuery, bot: Bot):
    # працює в групі
    # status:<offer_id>:<status>
    try:
        _, oid_str, new_status = call.data.split(":")
        oid = int(oid_str)
    except Exception:
        await call.answer("Помилка даних кнопки.")
        return

    offer = await get_offer(DB_PATH, oid)
    if not offer:
        await call.answer("Не знайдено пропозицію.")
        return

    changed_by = call.from_user.username
    changed_by = f"@{changed_by}" if changed_by else (call.from_user.full_name or "—")

    await change_status(DB_PATH, oid, new_status, changed_by)

    # оновлюємо текст повідомлення, кнопки залишаємо
    updated = await get_offer(DB_PATH, oid)
    text = build_offer_text(oid, updated)

    try:
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text,
            reply_markup=status_kb(oid),
            disable_web_page_preview=True
        )
    except Exception:
        # якщо не можна відредагувати (інколи), просто скажемо що ок
        pass

    await call.answer("✅ Статус оновлено")


@router.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Скасовано. /start")
    await call.answer()


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Скасовано. /start")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не заданий")

    await init_db(DB_PATH)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
