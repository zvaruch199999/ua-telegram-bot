from aiogram.fsm.state import StatesGroup, State


class OfferForm(StatesGroup):
    category = State()
    living_type = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    price = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewings = State()
    broker = State()
    photos = State()

    preview = State()
    edit_choose = State()
    edit_value = State()
