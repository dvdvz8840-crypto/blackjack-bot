import telebot
from telebot import types
import random
import sqlite3
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
ADMIN_ID = 6151671553

bot = telebot.TeleBot(TOKEN)

# ------------------- База данных -------------------
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

# ------------------- Баланс -------------------
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

# ------------------- Общие функции -------------------
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

# ------------------- Соло-игра -------------------
solo_games = {}  # user_id -> game

@bot.message_handler(func=lambda m: m.text.lower().startswith("блек"))
def solo_blackjack(message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "❗ Используй: блек <ставка>")
        return
    bet = int(parts[1])
    if bet < 100:
        bot.send_message(message.chat.id, "❌ Минимальная ставка 100 монет!")
        return
    balance = get_balance(user_id)
    if bet > balance:
        bot.send_message(message.chat.id, "❌ Недостаточно монет.")
        return

    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    solo_games[user_id] = {
        "deck": deck,
        "player": player_hand,
        "dealer": dealer_hand,
        "bet": bet,
        "doubled": False
    }

    update_balance(user_id, balance - bet)

    bot.send_message(
        message.chat.id,
        f"🎰 Соло BlackJack!\n\n"
        f"🃏 Твои карты: {player_hand} ({hand_value(player_hand)})\n"
        f"🎴 Карта дилера: [{dealer_hand[0]}, ?]\n"
        f"💰 Ставка: {bet}",
        reply_markup=game_keyboard(can_double=True)
    )

# ------------------- Мульти-плеер -------------------
multiplayer_games = {}  # chat_id -> game

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
        "players": {},  # user_id -> {"hand": [], "finished": False, "message_id": None}
        "deck": create_deck(),
        "dealer": [],
        "bet": bet,
        "turn_order": [],
        "current_turn": 0
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Присоединиться", callback_data=f"join_{chat_id}"))
    bot.send_message(chat_id, f"🎲 Новая мульти-игра! Ставка {bet} монет.\nНажмите 'Присоединиться'!", reply_markup=markup)

    threading.Timer(120, lambda: start_multiplayer_game(chat_id)).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("join_"))
def join_game(callback):
    user_id = callback.from_user.id
    chat_id = int(callback.data.split("_")[1])
    game = multiplayer_games.get(chat_id)
    if not game:
        callback.answer("Игра не найдена.", show_alert=True)
        return
    if user_id in game["players"]:
        callback.answer("Вы уже в игре!", show_alert=True)
        return
    if len(game["players"]) >= 9:
        callback.answer("⚠ Комната заполнена! Максимум 9 игроков.", show_alert=True)
        return
    bet = game["bet"]
    balance = get_balance(user_id)
    if balance < bet:
        callback.answer("❌ Недостаточно монет!", show_alert=True)
        return

    update_balance(user_id, balance - bet)
    game["players"][user_id] = {"hand": [], "finished": False, "message_id": None}
    callback.answer(f"✅ Вы присоединились! Ожидайте начала игры.")

    bot.edit_message_text(
        chat_id=chat_id,
        message_id=callback.message.message_id,
        text=f"🎲 Игра создана! Присоединились {len(game['players'])} игроков.\nНажмите 'Присоединиться', чтобы вступить!",
        reply_markup=callback.message.reply_markup
    )

def start_multiplayer_game(chat_id):
    game = multiplayer_games.get(chat_id)
    if not game:
        return
    if len(game["players"]) == 0:
        bot.send_message(chat_id, "⚠ Игра отменена — никто не присоединился.")
        del multiplayer_games[chat_id]
        return

    game["dealer"] = [game["deck"].pop(), game["deck"].pop()]
    game["turn_order"] = list(game["players"].keys())
    game["current_turn"] = 0

    # Раздать карты игрокам
    for uid in game["players"]:
        hand = [game["deck"].pop(), game["deck"].pop()]
        game["players"][uid]["hand"] = hand
        text = f"🎰 @[{uid}] Ваши карты: {hand} ({hand_value(hand)})\n🎴 Карта дилера: [{game['dealer'][0]}, ?]\n💰 Ставка: {game['bet']}\n⏳ Сейчас ходит: @{game['turn_order'][0]}"
        msg = bot.send_message(chat_id, text, reply_markup=game_keyboard(can_double=True))
        game["players"][uid]["message_id"] = msg.message_id

# ------------------- Остальные команды (баланс, перевод, награда, админ) -------------------
# ... можно вставить код из предыдущего варианта

# ------------------- Запуск -------------------
bot.infinity_polling()