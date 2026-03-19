import logging
import os
import csv
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = os.getenv("TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

registration_open = True
user_state = {}


def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        number INTEGER UNIQUE,
        name TEXT NOT NULL,
        phone TEXT UNIQUE NOT NULL,
        telegram_id BIGINT UNIQUE NOT NULL
    )
    """)
    cur.close()
    conn.close()


def get_next_number():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count + 1


def user_exists(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE telegram_id = %s", (user_id,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


def phone_exists(phone):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE phone = %s", (phone,))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists


def is_admin(message: types.Message) -> bool:
    return str(message.from_user.id) == ADMIN_ID


@dp.message_handler(commands=["clear"])
async def clear_db(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE users RESTART IDENTITY")
    cur.close()
    conn.close()

    await message.answer("🔥 База очищена! Можно начинать новый розыгрыш.")


@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    global registration_open

    if not registration_open:
        await message.answer("Регистрация закрыта ❌")
        return

    if user_exists(message.from_user.id):
        await message.answer("Вы уже зарегистрированы 👍")
        return

    text = (
        "💥 Условия участия:\n"
        "1. Введи ФИО\n"
        "2. Введи номер телефона\n\n"
        "🎟 Ты получишь номер участника\n"
        "🎲 Победитель выбирается случайно\n\n"
    )

    user_state[message.from_user.id] = {"step": "name"}

    await message.answer(text)
    await message.answer("Введите ФИО:")


@dp.message_handler(commands=["users"])
async def users_list(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT number, name, phone FROM users ORDER BY number ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Участников пока нет")
        return

    text = "👥 Участники:\n\n"
    for number, name, phone in rows:
        line = f"{number}. {name} — {phone}\n"
        if len(text) + len(line) > 4000:
            await message.answer(text)
            text = ""
        text += line

    if text:
        await message.answer(text)


@dp.message_handler(commands=["count"])
async def count_users(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.close()
    conn.close()

    await message.answer(f"Участников: {total}")


@dp.message_handler(commands=["winner"])
async def choose_winner(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT number, name, phone FROM users ORDER BY RANDOM() LIMIT 1")
    winner = cur.fetchone()
    cur.close()
    conn.close()

    if not winner:
        await message.answer("Участников пока нет")
        return

    number, name, phone = winner
    await message.answer(
        f"🎉 Победитель:\n\n"
        f"Номер: {number}\n"
        f"ФИО: {name}\n"
        f"Телефон: {phone}"
    )


@dp.message_handler(commands=["export"])
async def export_users(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT number, name, phone, telegram_id FROM users ORDER BY number ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    file_path = "users.csv"
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Номер", "ФИО", "Телефон", "Telegram ID"])
        writer.writerows(rows)

    await message.answer_document(types.InputFile(file_path))


@dp.message_handler(commands=["close"])
async def close_registration(message: types.Message):
    global registration_open

    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    registration_open = False
    await message.answer("Регистрация закрыта ❌")


@dp.message_handler(commands=["open"])
async def open_registration(message: types.Message):
    global registration_open

    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    registration_open = True
    await message.answer("Регистрация открыта ✅")


@dp.message_handler(commands=["admin"])
async def admin_help(message: types.Message):
    if not is_admin(message):
        await message.answer("Нет доступа")
        return

    await message.answer(
        "Команды админа:\n"
        "/users - список участников\n"
        "/count - количество участников\n"
        "/winner - выбрать победителя\n"
        "/export - скачать базу CSV\n"
        "/clear - очистить базу\n"
        "/close - закрыть регистрацию\n"
        "/open - открыть регистрацию"
    )


@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_state:
        if user_exists(user_id):
            await message.answer("Вы уже зарегистрированы 👍")
        return

    step = user_state[user_id]["step"]

    if step == "name":
        name = message.text.strip()
        if not name:
            await message.answer("Введите ФИО текстом")
            return

        user_state[user_id]["name"] = name
        user_state[user_id]["step"] = "phone"
        await message.answer("Введите номер телефона:")
        return

    if step == "phone":
        phone = message.text.strip()

        if phone_exists(phone):
            await message.answer("Этот номер уже зарегистрирован ❌")
            return

        if user_exists(user_id):
            await message.answer("Вы уже зарегистрированы 👍")
            return

        number = get_next_number()

        conn = get_conn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (number, name, phone, telegram_id) VALUES (%s, %s, %s, %s)",
            (number, user_state[user_id]["name"], phone, user_id)
        )
        cur.close()
        conn.close()

        del user_state[user_id]

        await message.answer(
            f"✅ Вы зарегистрированы!\n"
            f"Ваш номер: {number}"
        )


if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
