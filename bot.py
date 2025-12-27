# === imports ===
import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from openpyxl import Workbook, load_workbook

# === env ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# === files ===
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# === excel ===
HEADERS = [
    "ID","Дата","Категорія","Тип житла","Вулиця","Місто","Район","Переваги",
    "Ціна","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер","Фото","Статус",
    "Хто знайшов нерухомість","Хто знайшов клієнта","Дата контракту",
    "Сума провізії","К-сть оплат","Графік оплат",
    "Клієнт","ПМЖ","Контакт"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    row_id = ws.max_row
    ws.append([
        row_id,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"], data["property_type"],
        data["street"], data["city"], data["district"],
        data["advantages"], data["rent"], data["deposit"],
        data["commission"], data["parking"],
        data["move_in"], data["viewing"], data["broker"],
        len(data["photos"]), "Активна",
        "", "", "", "", "", "", "", "", ""
    ])
    wb.save(EXCEL_FILE)
    return row_id

def update_status(row, status):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=17).value = status
    wb.save(EXCEL_FILE)

def write_deal(row, values):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, v in enumerate(values, start=18):
        ws.cell(row=row, column=i).value = v
    wb.save(EXCEL_FILE)

def get_active():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    return [
        (r, ws.cell(r,6).value, ws.cell(r,5).value, ws.cell(r,4).value, ws.cell(r,9).value, ws.cell(r,15).value)
        for r in range(2, ws.max_row+1)
        if ws.cell(r,17).value == "Активна"
    ]

# === FSM ===
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
    parking = State
