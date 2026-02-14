import telebot
from telebot import types
import random
import sqlite3
import time

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

# ---------------- Блэкджек ----------------
games = {}
cooldowns = {}

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
    markup.row("блек 100", "деньги")  # кнопка для ежедневной награды
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
    if now - last >= 86400:  # 24 часа
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
                     "🎰 <b>блек сумма</b> — начать игру\n"
                     "💸 <b>перевод ID сумма</b> — перевести монеты\n"
                     "🎁 <b>деньги</b> — ежедневная награда\n"
                     "📜 <b>бкоманды</b> — список команд", parse_mode="HTML")

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

@bot.message_handler(func=lambda m: m.text.lower().startswith("блек"))
def blackjack(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "❗ Используй: <b>блек сумма</b>", parse_mode="HTML")
        return
    bet = int(parts[1])
    user_id = message.from_user.id
    balance = get_balance(user_id)
    if bet <= 0 or bet > balance:
        bot.send_message(message.chat.id, "❌ Недостаточно монет.")
        return
    deck = create_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    games[user_id] = {"deck": deck, "player": player, "dealer": dealer, "bet": bet, "doubled": False}
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

# ---------------- Игровые кнопки ----------------
@bot.callback_query_handler(func=lambda c: True)
def game_actions(callback):
    user_id = callback.from_user.id
    if user_id not in games:
        callback.answer("Игра не найдена.", show_alert=True)
        return
    game = games[user_id]
    player = game["player"]
    dealer = game["dealer"]
    deck = game["deck"]
    bet = game["bet"]

    if callback.data == "hit":
        player.append(deck.pop())
        if hand_value(player) > 21:
            del games[user_id]
            bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                  text=f"💥 <b>Перебор!</b>\n\nТвои карты: {player} ({hand_value(player)})\n\nТы проиграл {bet} монет.",
                                  parse_mode="HTML")
            return
        bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                              text=f"🃏 Твои карты: {player} ({hand_value(player)})\n🎴 Карта дилера: {dealer[0]} + ❓",
                              reply_markup=game_keyboard(), parse_mode="HTML")

    elif callback.data == "stand":
        while hand_value(dealer) < 17:
            dealer.append(deck.pop())
        player_val = hand_value(player)
        dealer_val = hand_value(dealer)
        balance = get_balance(user_id)
        if dealer_val > 21 or player_val > dealer_val:
            win = int(bet * 2)
            update_balance(user_id, balance + win)
            text = f"🎉 <b>Ты выиграл!</b>\n+{win} монет"
        elif player_val == dealer_val:
            update_balance(user_id, balance + bet)
            text = "🤝 Ничья. Ставка возвращена."
        else:
            text = f"😢 Ты проиграл {bet} монет."
        del games[user_id]
        bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                              text=f"{text}\n\n🃏 {player} ({player_val})\n🎴 {dealer} ({dealer_val})", parse_mode="HTML")

    elif callback.data == "cash":
        balance = get_balance(user_id)
        refund = int(bet * 0.6)
        update_balance(user_id, balance + refund)
        del games[user_id]
        bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                              text=f"💰 Ты сделал кэшаут!\nВозвращено {refund} монет.", parse_mode="HTML")

    elif callback.data == "double":
        balance = get_balance(user_id)
        if balance < bet:
            callback.answer("Недостаточно средств для дабла.", show_alert=True)
            return
        update_balance(user_id, balance - bet)
        game["bet"] *= 2
        game["doubled"] = True
        player.append(deck.pop())
        if hand_value(player) > 21:
            del games[user_id]
            bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                  text=f"💥 Перебор после дабла!\nТы проиграл {game['bet']} монет.", parse_mode="HTML")
            return
        callback.data = "stand"
        game_actions(callback)

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