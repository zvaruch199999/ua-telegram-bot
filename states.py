from aiogram.fsm.state import State, StatesGroup

class CreateOffer(StatesGroup):
    category = State()
    housing_type = State()
    housing_type_custom = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    view_from = State()
    broker = State()
    photos = State()

class EditOffer(StatesGroup):
    choose_field_num = State()
    enter_value = State()
    housing_type_custom = State()
