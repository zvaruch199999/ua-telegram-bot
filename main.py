import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

class OfferFlow(StatesGroup):
    category = State()
    address = State()
    price = State()
    contact = State()
    confirm = State()

offers = {}

def menu():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Пропоную житло", callback_data="offer")]
    ])

def confirm_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])

dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Вітаю! Оберіть дію:", reply_markup=menu())

@dp.callback_query(F.data == "offer")
async def offer_start(c: CallbackQuery, state: FSMContext):
    offers[c.from_user.id] = {}
    await state.set_state(OfferFlow.category)
    await c.message.answer("Який тип житла? (квартира / кімната / будинок)")
    await c.answer()

@dp.message(OfferFlow.category)
async def step_category(m: Message, state: FSMContext):
    offers[m.from_user.id]["category"] = m.text
    await state.set_state(OfferFlow.address)
    await m.answer("Вкажіть адресу або район:")

@dp.message(OfferFlow.address)
async def step_address(m: Message, state: FSMContext):
    offers[m.from_user.id]["address"] = m.text
    await state.set_state(OfferFlow.price)
    await m.answer("Ціна (наприклад 700€):")

@dp.message(OfferFlow.price)
async def step_price(m: Message, state: FSMContext):
    offers[m.from_user.id]["price"] = m.text
    await state.set_state(OfferFlow.contact)
    await m.answer("Контакт для звʼязку:")

@dp.message(OfferFlow.contact)
async def step_contact(m: Message, state: FSMContext):
    offers[m.from_user.id]["contact"] = m.text
    text = (
        "📢 НОВА ПРОПОЗИЦІЯ\n"
        f"Тип: {offers[m.from_user.id]['category']}\n"
        f"Адреса: {offers[m.from_user.id]['address']}\n"
        f"Ціна: {offers[m.from_user.id]['price']}\n"
        f"Контакт: {offers[m.from_user.id]['contact']}"
    )
    offers[m.from_user.id]["text"] = text
    await state.set_state(OfferFlow.confirm)
    await m.answer(text, reply_markup=confirm_kb())

@dp.callback_query(OfferFlow.confirm, F.data == "publish")
async def publish(c: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_message(chat_id=int(GROUP_ID), text=offers[c.from_user.id]["text"])
    await c.message.answer("✅ Опубліковано у групі")
    await state.clear()
    await c.answer()

@dp.callback_query(OfferFlow.confirm, F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("Скасовано")
    await c.answer()

async def main():
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
