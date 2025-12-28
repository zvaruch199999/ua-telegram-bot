from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷 Оренда", callback_data="cat:Оренда"),
         InlineKeyboardButton(text="🏷 Продаж", callback_data="cat:Продаж")],
        [InlineKeyboardButton(text="➡️ Інше (ввести)", callback_data="cat:__custom__")],
    ])

def kb_housing_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Квартира", callback_data="type:Квартира"),
         InlineKeyboardButton(text="🚪 Кімната", callback_data="type:Кімната")],
        [InlineKeyboardButton(text="🏡 Будинок", callback_data="type:Будинок"),
         InlineKeyboardButton(text="🏢 Офіс", callback_data="type:Офіс")],
        [InlineKeyboardButton(text="➡️ Інше (ввести)", callback_data="type:__custom__")],
    ])

def kb_done_photos(number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data=f"photos_done:{number}")]
    ])

def kb_preview_actions(number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Опублікувати", callback_data=f"publish:{number}")],
        [InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit:{number}"),
         InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel:{number}")]
    ])

def kb_status(number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:{number}:ACTIVE"),
         InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{number}:RESERVE")],
        [InlineKeyboardButton(text="⚫️ Знято", callback_data=f"st:{number}:WITHDRAWN"),
         InlineKeyboardButton(text="✅ Угода закрита", callback_data=f"st:{number}:CLOSED")],
    ])

def kb_back_to_preview(number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад до превʼю", callback_data=f"preview:{number}")]
    ])
