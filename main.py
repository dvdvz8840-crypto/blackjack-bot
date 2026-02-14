import telebot
from telebot import types
import random
import sqlite3
import time

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
ADMIN_ID = 6151671553

bot = telebot.TeleBot(TOKEN)

# ---------------- База данных ----------------
conn = sqlite3.connect("blackjack.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 1000
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_rewards (
    user_id INTEGER PRIMARY KEY,
    last_claim INTEGER DEFAULT 0
)
""")
conn.commit()

# ---------------- Функции работы с балансом ----------------
def get_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 1000)", (user_id,))
        conn.commit()
        return 1000
    return row[0]

def update_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (amount, user_id))
    conn.commit()

def update_username(user_id, username):
    if username:
        cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 1000)", (user_id, username))
        else:
            cursor.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()

def ensure_username(message):
    update_username(message.from_user.id, message.from_user.username)

# ---------------- Блэкджек ----------------
games = {}           # Соло-игра: user_id -> game
cooldowns = {}       # Для бкоманды

def create_deck():
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    return deck

def hand_value(hand):
    value = sum(hand)
    while value > 21 and 11 in hand:
        hand[hand.index(11)] = 1
        value = sum(hand)
    return value

def game_keyboard(can_double=False):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🃏 Доб", callback_data="hit"),
        types.InlineKeyboardButton("✋ Стоп", callback_data="stand")
    )
    markup.row(
        types.InlineKeyboardButton("💰 Кэш 60%", callback_data="cash")
    )
    if can_double:
        markup.row(
            types.InlineKeyboardButton("🔥 Дабл", callback_data="double")
        )
    return markup

# ---------------- Главные кнопки ----------------
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("бал", "бкоманды")
    markup.row("блек 100", "деньги")
    return markup

# ---------------- Ежедневная награда ----------------
def can_claim_daily(user_id):
    cursor.execute("SELECT last_claim FROM daily_rewards WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    now = int(time.time())
    if row is None:
        cursor.execute("INSERT INTO daily_rewards (user_id, last_claim) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        return True, 0
    last = row[0]
    if now - last >= 86400:
        return True, last
    return False, last

def claim_daily(user_id, amount=500):
    can_claim, last = can_claim_daily(user_id)
    now = int(time.time())
    if can_claim:
        balance = get_balance(user_id)
        update_balance(user_id, balance + amount)
        cursor.execute("UPDATE daily_rewards SET last_claim=? WHERE user_id=?", (now, user_id))
        conn.commit()
        return True, amount
    else:
        remaining = 86400 - (now - last)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        return False, f"{hours}ч {minutes}м {seconds}с"

# ---------------- Команды ----------------
@bot.message_handler(commands=["start"])
def start(message):
    ensure_username(message)
    get_balance(message.from_user.id)
    bot.send_message(message.chat.id,
                     "🎰 Добро пожаловать в BlackJack!\n\n"
                     "Используй кнопки или пиши команды.\n"
                     "Нажми <b>бкоманды</b> чтобы увидеть все команды.",
                     parse_mode="HTML",
                     reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def commands(message):
    ensure_username(message)
    user_id = message.from_user.id
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 60:
        bot.send_message(message.chat.id, "⏳ Подожди 1 минуту перед повторным использованием команды.")
        return
    cooldowns[user_id] = now
    bot.send_message(message.chat.id,
                     "📜 <b>Команды BlackJack:</b>\n\n"
                     "💰 <b>бал</b> — проверить баланс\n"
                     "🎰 <b>блек сумма</b> — начать игру\n"
                     "💸 <b>перевод @username сумма</b> — перевести монеты\n"
                     "🎁 <b>деньги</b> — ежедневная награда\n"
                     "👑 <b>админвыдать @username сумма</b> — админ выдать монеты\n"
                     "📜 <b>бкоманды</b> — список команд", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance_cmd(message):
    ensure_username(message)
    bal = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 <b>Твой баланс:</b> {bal} монет", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.lower() == "деньги")
def daily_reward(message):
    ensure_username(message)
    user_id = message.from_user.id
    success, result = claim_daily(user_id)
    if success:
        bot.send_message(message.chat.id, f"🎁 Ты получил ежедневную награду: {result} монет!")
    else:
        bot.send_message(message.chat.id, f"⏳ Ежедневная награда уже получена.\nДоступно через: {result}")

# ---------------- Перевод по username ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("перевод"))
def transfer(message):
    ensure_username(message)
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❗ Используй: перевод @username сумма")
        return
    target_username = parts[1].lstrip("@")
    amount = int(parts[2])
    sender_id = message.from_user.id
    sender_balance = get_balance(sender_id)
    if amount <= 0 or amount > sender_balance:
        bot.send_message(message.chat.id, "❌ Недостаточно средств.")
        return
    cursor.execute("SELECT user_id FROM users WHERE username=?", (target_username,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(message.chat.id, f"❌ Игрок @{target_username} не найден.")
        return
    target_id = row[0]
    target_balance = get_balance(target_id)
    update_balance(sender_id, sender_balance - amount)
    update_balance(target_id, target_balance + amount)
    bot.send_message(message.chat.id, f"💸 Переведено {amount} монет игроку @{target_username}")

# ---------------- Админская выдача по username ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("админвыдать"))
def admin_give(message):
    ensure_username(message)
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❗ Используй: админвыдать @username сумма")
        return
    target_username = parts[1].lstrip("@")
    amount = int(parts[2])
    cursor.execute("SELECT user_id FROM users WHERE username=?", (target_username,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(message.chat.id, f"❌ Игрок @{target_username} не найден.")
        return
    target_id = row[0]
    target_balance = get_balance(target_id)
    update_balance(target_id, target_balance + amount)
    bot.send_message(message.chat.id, f"👑 Выдано {amount} монет пользователю @{target_username}")

# ---------------- Запуск ----------------
bot.infinity_polling()