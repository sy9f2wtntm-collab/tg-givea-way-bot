import logging
import os
import psycopg2
import csv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    number INTEGER UNIQUE,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    telegram_id BIGINT UNIQUE NOT NULL
)
""")

registration_open = True
user_state = {}

def get_next_number():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0] + 1

def user_exists(user_id):
    cursor.execute("SELECT 1 FROM users WHERE telegram_id=%s", (user_id,))
    return cursor.fetchone() is not None

def phone_exists(phone):
    cursor.execute("SELECT 1 FROM users WHERE phone=%s", (phone,))
    return cursor.fetchone() is not None

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    global registration_open

    if not registration_open:
        await message.answer("Регистрация закрыта ❌")
        return

    if user_exists(message.from_user.id):
        await message.answer("Вы уже зарегистрированы 👍")
        return

    user_state[message.from_user.id] = {"step": "name"}
    await message.answer("Введите ФИО:")

@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("/count\n/list\n/export\n/open\n/close")

@dp.message_handler(commands=['open'])
async def open_reg(message: types.Message):
    global registration_open
    if message.from_user.id == ADMIN_ID:
        registration_open = True
        await message.answer("Регистрация открыта ✅")

@dp.message_handler(commands=['close'])
async def close_reg(message: types.Message):
    global registration_open
    if message.from_user.id == ADMIN_ID:
        registration_open = False
        await message.answer("Регистрация закрыта ❌")

@dp.message_handler(commands=['count'])
async def count(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    await message.answer(f"Участников: {total}")

@dp.message_handler(commands=['list'])
async def list_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT number, name, phone FROM users ORDER BY number LIMIT 20")
    rows = cursor.fetchall()

    text = "\n".join([f"{r[0]} | {r[1]} | {r[2]}" for r in rows])
    await message.answer(text or "Пусто")

@dp.message_handler(commands=['export'])
async def export(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT number, name, phone FROM users ORDER BY number")
    rows = cursor.fetchall()

    file_path = "users.csv"

    with open(file_path, "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Номер", "ФИО", "Телефон"])
        writer.writerows(rows)

    await message.answer_document(types.InputFile(file_path))

@dp.message_handler()
async def handle(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_state:
        return

    step = user_state[user_id]["step"]

    if step == "name":
        user_state[user_id]["name"] = message.text.strip()
        user_state[user_id]["step"] = "phone"
        await message.answer("Введите номер телефона:")
        return

    if step == "phone":
        phone = message.text.strip()

        if phone_exists(phone):
            await message.answer("Этот номер уже есть ❌")
            return

        number = get_next_number()

        cursor.execute(
            "INSERT INTO users (number, name, phone, telegram_id) VALUES (%s, %s, %s, %s)",
            (number, user_state[user_id]["name"], phone, user_id)
        )

        await message.answer(f"✅ Вы зарегистрированы!\nВаш номер: {number}")
        del user_state[user_id]

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
@dp.message_handler(commands=['users'])
async def get_users(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return

    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()

    cur.execute("SELECT id, full_name, phone FROM users")
    users = cur.fetchall()

    text = "👥 Участники:\n\n"

    for user in users:
        text += f"{user[0]}. {user[1]} — {user[2]}\n"

    await message.answer(text[:4000])
