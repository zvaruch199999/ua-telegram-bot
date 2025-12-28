from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---- Reply keyboard тільки для фото-етапу ----
def photos_done_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Готово")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ---- Inline ----
def category_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Оренда", callback_data="cat:Оренда")
    kb.button(text="🏡 Продаж", callback_data="cat:Продаж")
    kb.button(text="✍️ Інше", callback_data="cat:__other__")
    kb.adjust(2, 1)
    return kb.as_markup()

def housing_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛏 Кімната", callback_data="ht:Кімната")
    kb.button(text="🏢 Квартира", callback_data="ht:Квартира")
    kb.button(text="🏠 Будинок", callback_data="ht:Будинок")
    kb.button(text="🏬 Комерція", callback_data="ht:Комерція")
    kb.button(text="✍️ Інше", callback_data="ht:__other__")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def preview_kb(offer_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Опублікувати", callback_data=f"pub:{offer_id}")
    kb.button(text="✏️ Редагувати", callback_data=f"edit:{offer_id}")
    kb.button(text="❌ Скасувати", callback_data=f"cancel:{offer_id}")
    kb.adjust(1, 2)
    return kb.as_markup()

def status_kb(offer_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Актуально", callback_data=f"st:{offer_id}:ACTIVE")
    kb.button(text="🟡 Резерв", callback_data=f"st:{offer_id}:RESERVED")
    kb.button(text="🔴 Знято", callback_data=f"st:{offer_id}:REMOVED")
    kb.button(text="✅ Закрито", callback_data=f"st:{offer_id}:CLOSED")
    kb.adjust(2, 2)
    return kb.as_markup()
