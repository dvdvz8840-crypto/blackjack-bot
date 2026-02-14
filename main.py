import telebot
from telebot import types
import random
import sqlite3
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"  # <-- вставь сюда свой токен
ADMIN_ID = 6151671553

bot = telebot.TeleBot(TOKEN)

# ---------------- База данных ----------------
conn = sqlite3.connect("blackjack.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
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

# ---------------- Баланс ----------------
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

# ---------------- Соло-игра ----------------
solo_games = {}

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

# ---------------- Мульти-плеер ----------------
multiplayer_games = {}  # key = chat_id

def game_keyboard_multiplayer(can_double=False):
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
cooldowns = {}

@bot.message_handler(commands=["start"])
def start(message):
    get_balance(message.from_user.id)
    bot.send_message(message.chat.id,
                     "🎰 Добро пожаловать в BlackJack!\n\n"
                     "Используй кнопки или пиши команды.\n"
                     "Нажми <b>бкоманды</b> чтобы увидеть все команды.",
                     parse_mode="HTML",
                     reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def commands(message):
    user_id = message.from_user.id
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 60:
        bot.send_message(message.chat.id, "⏳ Подожди 1 минуту перед повторным использованием команды.")
        return
    cooldowns[user_id] = now
    bot.send_message(message.chat.id,
                     "📜 <b>Команды BlackJack:</b>\n\n"
                     "💰 <b>бал</b> — проверить баланс\n"
                     "🎰 <b>блек сумма</b> — начать соло-игру\n"
                     "💸 <b>перевод ID сумма</b> — перевести монеты\n"
                     "🎁 <b>деньги</b> — ежедневная награда\n"
                     "📜 <b>бкоманды</b> — список команд\n"
                     "🎲 <b>создать_игру сумма</b> — мульти-плеер", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance_cmd(message):
    bal = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 <b>Твой баланс:</b> {bal} монет", parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text.lower() == "деньги")
def daily_reward(message):
    user_id = message.from_user.id
    success, result = claim_daily(user_id)
    if success:
        bot.send_message(message.chat.id, f"🎁 Ты получил ежедневную награду: {result} монет!")
    else:
        bot.send_message(message.chat.id, f"⏳ Ежедневная награда уже получена.\nДоступно через: {result}")

# ---------------- Соло-игра ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("блек"))
def blackjack(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "❗ Используй: <b>блек сумма</b>", parse_mode="HTML")
        return
    bet = int(parts[1])
    if bet < 100:
        bot.send_message(message.chat.id, "❌ Минимальная ставка 100 монет!")
        return
    user_id = message.from_user.id
    balance = get_balance(user_id)
    if bet <= 0 or bet > balance:
        bot.send_message(message.chat.id, "❌ Недостаточно монет.")
        return
    deck = create_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    solo_games[user_id] = {"deck": deck, "player": player, "dealer": dealer, "bet": bet, "doubled": False}
    update_balance(user_id, balance - bet)
    bot.send_message(
        message.chat.id,
        f"🎰 <b>BlackJack!</b>\n\n"
        f"🃏 Твои карты: {player} ({hand_value(player)})\n"
        f"🎴 Карта дилера: {dealer[0]} + ❓\n\n"
        f"💰 Ставка: {bet}",
        parse_mode="HTML",
        reply_markup=game_keyboard(can_double=True)
    )

# ---------------- Мульти-плеер: создать комнату ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("создать_игру"))
def create_multiplayer(message):
    chat_id = message.chat.id
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        bot.send_message(chat_id, "Используй: создать_игру <ставка>")
        return
    bet = int(parts[1])
    if bet < 100:
        bot.send_message(chat_id, "❌ Минимальная ставка 100 монет!")
        return
    if chat_id in multiplayer_games:
        bot.send_message(chat_id, "⚠ Комната уже создана! Ожидайте завершения текущей игры.")
        return

    multiplayer_games[chat_id] = {
        "players": {},
        "deck": create_deck(),
        "dealer": [],
        "bet": bet,
        "turn_order": [],
        "current_turn": 0
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"join_{chat_id}"))
    bot.send_message(chat_id, f"🎲 Новая игра создана с ставкой {bet} монет.\nНажмите кнопку 'Присоединиться', чтобы вступить!", reply_markup=markup)

    # Авто-старт через 2 минуты
    threading.Timer(120, lambda: start_multiplayer_game(chat_id)).start()

# ---------------- Мульти-плеер: присоединение ----------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("join_"))
def join_game(callback):
    user_id = callback.from_user.id
    chat_id = int(callback.data.split("_")[1])
    game = multiplayer_games.get(chat_id)
    if not game:
        callback.answer("Игра не найдена или завершена.", show_alert=True)
        return
    if len(game["players"]) >= 9:
        callback.answer("⚠ Комната заполнена! Максимум 9 игроков.", show_alert=True)
        return
    if user_id in game["players"]:
        callback.answer("Вы уже в игре! Ожидайте начала.", show_alert=True)
        return
    bet = game["bet"]
    balance = get_balance(user_id)
    if balance < bet:
        callback.answer("❌ Недостаточно монет для присоединения!", show_alert=True)
        return
    # Добавляем игрока
    update_balance(user_id, balance - bet)
    game["players"][user_id] = {"hand": [], "finished": False}
    callback.answer(f"✅ Вы присоединились! Ожидайте начала игры.")
    bot.send_message(user_id, f"🎲 Вы присоединились к игре с ставкой {bet} монет. Ожидайте начала игры!")

    # Обновляем сообщение в чате (для других)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=callback.message.message_id,
        text=f"🎲 Игра создана! Ставка {bet} монет.\nПрисоединились {len(game['players'])} игроков.\nНажмите 'Присоединиться', чтобы вступить!",
        reply_markup=callback.message.reply_markup
    )

# ---------------- Мульти-плеер: авто-старт ----------------
def start_multiplayer_game(chat_id):
    game = multiplayer_games.get(chat_id)
    if not game:
        return
    if len(game["players"]) == 0:
        bot.send_message(chat_id, "⚠ Игра отменена — никто не присоединился.")
        del multiplayer_games[chat_id]
        return
    bot.send_message(chat_id, f"🎲 Игра начинается! {len(game['players'])} игроков присоединились.")
    game["dealer"] = [game["deck"].pop(), game["deck"].pop()]
    game["turn_order"] = list(game["players"].keys())
    game["current_turn"] = 0
    # Начало первого хода
    first_player = game["turn_order"][0]
    player_data = game["players"][first_player]
    player_data["hand"] = [game["deck"].pop(), game["deck"].pop()]
    bot.send_message(first_player, "🎰 Ваш ход!", reply_markup=game_keyboard_multiplayer(can_double=True))

# ---------------- TODO: Ходы и подсчёт для мульти-плеера ----------------
# Логику кнопок Доб/Стоп/Дабл/Кэш для мульти-плеера можно вставить аналогично соло-игре,
# проверяя очередь: user_id == turn_order[current_turn]

# ---------------- Перевод ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("перевод"))
def transfer(message):
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❗ Используй: перевод ID сумма")
        return
    target_id = int(parts[1])
    amount = int(parts[2])
    sender_id = message.from_user.id
    sender_balance = get_balance(sender_id)
    if amount <= 0 or amount > sender_balance:
        bot.send_message(message.chat.id, "❌ Недостаточно средств.")
        return
    get_balance(target_id)
    target_balance = get_balance(target_id)
    update_balance(sender_id, sender_balance - amount)
    update_balance(target_id, target_balance + amount)
    bot.send_message(message.chat.id, f"💸 Переведено {amount} монет игроку {target_id}")

# ---------------- Админская выдача ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("админвыдать"))
def admin_give(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        return
    target_id = int(parts[1])
    amount = int(parts[2])
    get_balance(target_id)
    balance = get_balance(target_id)
    update_balance(target_id, balance + amount)
    bot.send_message(message.chat.id, f"👑 Выдано {amount} монет пользователю {target_id}")

# ---------------- Запуск ----------------
bot.infinity_polling()