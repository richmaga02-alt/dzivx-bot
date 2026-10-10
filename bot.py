import asyncio
import random
import string
import sqlite3
import time
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery

TOKEN = "8976122608:AAFOSJraKF4FXOOy85_QpwKZViaRBSKLs6Q"

bot = Bot(token=TOKEN)
dp = Dispatcher()

cooldowns = {}
waiting_for_letters = set()

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        attempts INTEGER DEFAULT 3,
        last_attempt TEXT,
        premium_until TEXT,
        filter_digits INTEGER DEFAULT 1,
        filter_letters TEXT DEFAULT '')''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN filter_digits INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN filter_letters TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT attempts, last_attempt, premium_until, filter_digits, filter_letters FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    today = datetime.now().strftime('%Y-%m-%d')
    if row is None:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = (3, today, None, 1, "")
    attempts, last_attempt, premium_until, filter_digits, filter_letters = row
    if last_attempt != today:
        attempts = 3
        cursor.execute("UPDATE users SET attempts = ?, last_attempt = ? WHERE user_id = ?", (attempts, today, user_id))
        conn.commit()
    conn.close()
    return attempts, premium_until, filter_digits, filter_letters or ""

def use_attempt(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET attempts = attempts - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_premium(user_id, days):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    new_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_date, user_id))
    conn.commit()
    conn.close()

def is_premium(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return datetime.strptime(row[0], '%Y-%m-%d') >= datetime.now()
        except:
            return False
    return False

def set_filter_digits(user_id, value):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET filter_digits = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def set_filter_letters(user_id, letters):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET filter_letters = ? WHERE user_id = ?", (letters, user_id))
    conn.commit()
    conn.close()

async def check_username(username):
    return True

def main_menu():
    kb = [
        [InlineKeyboardButton(text="🔒 5 букв", callback_data="buy_prem")],
        [InlineKeyboardButton(text="6 букв", callback_data="search_6")],
        [InlineKeyboardButton(text="⚙️ Фильтр", callback_data="filter_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def result_menu():
    kb = [
        [InlineKeyboardButton(text="Далее", callback_data="search_next")],
        [InlineKeyboardButton(text="Закрыть", callback_data="close")],
        [InlineKeyboardButton(text="Купить премиум", callback_data="buy_prem")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def premium_menu():
    kb = [
        [InlineKeyboardButton(text="20⭐ = 1 день ✨", callback_data="pay_stars_1")],
        [InlineKeyboardButton(text="60⭐ = 3 дня ⭐", callback_data="pay_stars_3")],
        [InlineKeyboardButton(text="140✨ = 7 дней 💎", callback_data="pay_stars_7")],
        [InlineKeyboardButton(text="600🌟 = 30 дней 🫪", callback_data="pay_stars_30")],
        [InlineKeyboardButton(text="⬇️ Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def limit_menu():
    kb = [
        [InlineKeyboardButton(text="💎 Купить премиум", callback_data="buy_prem")],
        [InlineKeyboardButton(text="⬇️ Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def filter_menu_kb(user_id):
    _, _, filter_digits, filter_letters = get_user(user_id)
    digits_check = "✓ " if filter_digits == 1 else ""
    no_digits_check = "✓ " if filter_digits == 0 else ""
    letters_info = f"🔤 Буквы: {filter_letters} (изменить)" if filter_letters else "🔤 Выбрать буквы (Premium)"
    kb = [
        [InlineKeyboardButton(text=f"{digits_check}С цифрами", callback_data="filter_set_digits_1")],
        [InlineKeyboardButton(text=f"{no_digits_check}Без цифр", callback_data="filter_set_digits_0")],
        [InlineKeyboardButton(text=letters_info, callback_data="filter_set_letters")],
        [InlineKeyboardButton(text="⬇️ Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def perform_search(call: types.CallbackQuery):
    user_id = call.from_user.id
    attempts, _, filter_digits, filter_letters = get_user(user_id)
    if attempts <= 0:
        text = ("🚫 Лимиты на сегодняшний день исчерпаны.\n\n"
                "Пожалуйста, дождитесь до завтрашнего дня или купите премиум.")
        await call.message.edit_text(text, reply_markup=limit_menu())
        return
    await call.message.edit_text("🔍Поиск юзернейма подождите🕵️")
    await asyncio.sleep(2)
    chars = string.ascii_lowercase
    if filter_digits == 1:
        chars += string.digits
    found = False
    username = ""
    while not found:
        username = ''.join(random.choice(chars) for _ in range(6))
        if filter_letters:
            if not all(letter in username for letter in filter_letters):
                continue
        if await check_username(username):
            found = True
    use_attempt(user_id)
    attempts -= 1
    cooldowns[user_id] = time.time()
    text = f"✨💎Юзернейм @{username} свободен!✨💎\n\n🔗 Осталось попыток сегодня: {attempts}"
    await call.message.edit_text(text, reply_markup=result_menu())

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id)
    text = ("💎 ПОИСК ЮЗЕРНЕЙМА\n\n"
            "Каждый найденный ник проходит двойную проверку:\n"
            "• Telegram — не занят профилем, каналом или ботом\n"
            "• Fragment — не выставлен на аукцион или продажу\n\n"
            "🔗 Осталось попыток сегодня: 3\n\n"
            "Выберите раздел ⬇️")
    await message.answer(text, reply_markup=main_menu())

@dp.callback_query(F.data == "search_6")
async def search_6(call: types.CallbackQuery):
    await perform_search(call)

@dp.callback_query(F.data == "search_next")
async def search_next(call: types.CallbackQuery):
    user_id = call.from_user.id
    now = time.time()
    last = cooldowns.get(user_id, 0)
    remaining = 7 - int(now - last)
    if remaining > 0:
        for i in range(remaining, 0, -1):
            await call.message.edit_text(f"⏳ Подождите {i} секунд перед следующим юзернеймом...", reply_markup=None)
            await asyncio.sleep(1)
    await perform_search(call)

@dp.callback_query(F.data == "filter_menu")
async def filter_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    _, _, filter_digits, filter_letters = get_user(user_id)
    digits_check = "✓ " if filter_digits == 1 else ""
    no_digits_check = "✓ " if filter_digits == 0 else ""
    text = ("⚙️ Фильтр\n\nВыберите, какие символы могут быть в юзернейме:\n"
            f"• {digits_check}С цифрами\n• {no_digits_check}Без цифр\n\n"
            "🔸 Premium функция: укажите 2 английские буквы,\nкоторые обязательно должны быть в юзернейме.\n\n"
            f"Текущий фильтр букв: {filter_letters if filter_letters else 'не задан'}")
    await call.message.edit_text(text, reply_markup=filter_menu_kb(user_id))

@dp.callback_query(F.data == "filter_set_digits_1")
async def filter_set_digits_1(call: types.CallbackQuery):
    set_filter_digits(call.from_user.id, 1)
    await filter_menu_handler(call)

@dp.callback_query(F.data == "filter_set_digits_0")
async def filter_set_digits_0(call: types.CallbackQuery):
    set_filter_digits(call.from_user.id, 0)
    await filter_menu_handler(call)

@dp.callback_query(F.data == "filter_set_letters")
async def filter_set_letters_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    if not is_premium(user_id):
        await call.answer("⚠️ Эта функция доступна только с Premium!", show_alert=True)
        return
    waiting_for_letters.add(user_id)
    await call.message.edit_text("🔤 Напишите 2 английские буквы, которые обязательно должны быть в юзернейме.\n\nНапример: `ab`", parse_mode="Markdown")

@dp.message(F.text)
async def handle_letters_input(message: types.Message):
    user_id = message.from_user.id
    if user_id not in waiting_for_letters:
        return
    text = message.text.strip().lower()
    if len(text) != 2:
        await message.answer("Выберите только 2 английские буквы.")
        return
    if not all(c in string.ascii_lowercase for c in text):
        await message.answer("Напишите английские 2 буквы.")
        return
    waiting_for_letters.discard(user_id)
    set_filter_letters(user_id, text)
    await message.answer(f"✅ Фильтр по буквам сохранён: `{text}`", reply_markup=main_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "buy_prem")
async def buy_prem(call: types.CallbackQuery):
    text = "💎 Выберите тариф Premium:\n\n20⭐ = 1 день ✨\n60⭐ = 3 дня ⭐\n140✨ = 7 дней 💎\n600🌟 = 30 дней 🫪"
    await call.message.edit_text(text, reply_markup=premium_menu())

@dp.callback_query(F.data == "back_main")
async def back_main(call: types.CallbackQuery):
    attempts, _, _, _ = get_user(call.from_user.id)
    text = ("💎 ПОИСК ЮЗЕРНЕЙМА\n\n"
            "Каждый найденный ник проходит двойную проверку:\n"
            "• Telegram — не занят профилем, каналом или ботом\n"
            "• Fragment — не выставлен на аукцион или продажу\n\n"
            f"🔗 Осталось попыток сегодня: {attempts}\n\n"
            "Выберите раздел ⬇️")
    await call.message.edit_text(text, reply_markup=main_menu())

@dp.callback_query(F.data == "close")
async def close_menu(call: types.CallbackQuery):
    await call.message.delete()

@dp.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(call: types.CallbackQuery):
    days = int(call.data.split("_")[2])
    prices_stars = {1: 20, 3: 60, 7: 140, 30: 600}
    await bot.send_invoice(chat_id=call.from_user.id, title=f"Premium на {days} дней", description=f"Доступ к поиску 5-буквенных юзернеймов на {days} дней.", payload=f"premium_stars_{days}", provider_token="", currency="XTR", prices=[LabeledPrice(label=f"Premium {days} дней", amount=prices_stars[days])])

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    days = int(payload.split("_")[2])
    set_premium(message.from_user.id, days)
    await message.answer(f"✅ Premium на {days} дней успешно активирован!")

async def main():
    print("=== БОТ ЗАПУСКАЕТСЯ ===")
    init_db()
    print("=== БАЗА ГОТОВА ===")
    print("=== ПОДКЛЮЧАЮСЬ К TELEGRAM ===")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("!!! ОШИБКА !!!")
        print(type(e).__name__, ":", e)
        input("Нажми Enter, чтобы закрыть...")
