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

# ---------------- Баланс и username ----------------
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
games = {}  # соло-игра
cooldowns = {}  # для бкоманды

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
                     "🎮 <b>создать_игру сумма</b> — создать мульти-игру\n"
                     "📜 <b>бкоманды</b> — список команд",
                     parse_mode="HTML")

@bot.message_handler(commands=['bdbalance'])
def balance_command(message):
    send_balance(message)

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance_text(message):
    send_balance(message)

def send_balance(message):
    user_id = message.from_user.id
    username = message.from_user.username
    balance = get_balance(user_id)

    # Если нет юзернейма — используем имя
    if username:
        name = f"@{username}"
    else:
        name = message.from_user.first_name

    bot.send_message(
        message.chat.id,
        f"{name} 💰 <b>Ваш баланс:</b> {balance} монет",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text.lower() == "деньги")
def daily_reward(message):
    ensure_username(message)
    user_id = message.from_user.id
    success, result = claim_daily(user_id)
    if success:
        bot.send_message(message.chat.id, f"🎁 Ты получил ежедневную награду: {result} монет!")
    else:
        bot.send_message(message.chat.id, f"⏳ Ежедневная награда уже получена.\nДоступно через: {result}")

# ---------------- Соло-игра BlackJack ----------------
@bot.message_handler(func=lambda m: m.text.lower().startswith("блек"))
def blackjack(message):
    ensure_username(message)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "❗ Используй: <b>блек сумма</b>", parse_mode="HTML")
        return

    bet = int(parts[1])
    if bet < 100:
        bot.send_message(message.chat.id, "❌ Минимальная ставка — 100 монет.")
        return

    user_id = message.from_user.id
    balance = get_balance(user_id)
    if bet > balance:
        bot.send_message(message.chat.id, "❌ Недостаточно монет.")
        return

    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    games[user_id] = {"deck": deck, "player": player, "dealer": dealer, "bet": bet, "doubled": False}
    update_balance(user_id, balance - bet)

    bot.send_message(message.chat.id,
                     f"🎰 <b>BlackJack!</b>\n\n🃏 Твои карты: {player} ({hand_value(player)})\n🎴 Карта дилера: {dealer[0]} + ❓\n💰 Ставка: {bet}",
                     parse_mode="HTML",
                     reply_markup=game_keyboard(can_double=True))

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
            win = bet * 2
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
    
# ---------------- Мульти-плеер через текстовые команды ----------------
import threading

multi_games = {}  # словарь для мульти-игр: chat_id -> игра

# Создание комнаты
@bot.message_handler(func=lambda m: m.text.lower().startswith("создать_игру"))
def create_multi_game(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "❗ Используй: создать_игру сумма")
        return
    bet = int(parts[1])
    if bet < 100:
        bot.send_message(message.chat.id, "❌ Минимальная ставка — 100 монет")
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    balance = get_balance(user_id)
    if bet > balance:
        bot.send_message(chat_id, "❌ Недостаточно монет.")
        return
    update_balance(user_id, balance - bet)

    if chat_id in multi_games and multi_games[chat_id]['status'] == 'waiting':
        bot.send_message(chat_id, "⚠ Комната уже создана! Ожидайте завершения.")
        return

    multi_games[chat_id] = {
        'players': {user_id: {'hand': [], 'bet': bet, 'done': False, 'doubled': False, 'username': username}},
        'deck': create_deck(),
        'status': 'waiting',
        'turn_order': [],
        'current': 0,
        'timer_thread': None
    }

    bot.send_message(chat_id,
        f"🎮 <b>Новая мульти-игра BlackJack!</b>\n"
        f"💰 Ставка: {bet}\n"
        f"🧍 Создатель: @{username} (уже в игре)\n"
        f"Ожидаем игроков (максимум 9).\n\n"
        f"✋ Чтобы присоединиться, напиши в чат «бда».",
        parse_mode="HTML"
    )

    # Таймер автостарт через 2 минуты
    def auto_start():
        time.sleep(120)
        if chat_id in multi_games and multi_games[chat_id]['status'] == 'waiting':
            if len(multi_games[chat_id]['players']) >= 1:
                multi_games[chat_id]['status'] = 'playing'
                start_multi_game(chat_id)

    t = threading.Thread(target=auto_start)
    multi_games[chat_id]['timer_thread'] = t
    t.start()

# Присоединение к комнате через команду "бда"
@bot.message_handler(func=lambda m: m.text.lower() == "бда")
def join_multi(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    update_username(user_id, username)

    if chat_id not in multi_games or multi_games[chat_id]['status'] != 'waiting':
        bot.send_message(chat_id, "⚠ Игра неактивна или уже началась.")
        return
    if user_id in multi_games[chat_id]['players']:
        bot.send_message(chat_id, "⚠ Ты уже в игре.")
        return

    bet = list(multi_games[chat_id]['players'].values())[0]['bet']
    balance = get_balance(user_id)
    if balance < bet:
        bot.send_message(chat_id, "❌ Недостаточно средств для присоединения.")
        return
    update_balance(user_id, balance - bet)
    multi_games[chat_id]['players'][user_id] = {'hand': [], 'bet': bet, 'done': False, 'doubled': False, 'username': username}

    bot.send_message(chat_id, f"✅ @{username} присоединился к игре!")

    # Автостарт, если набрался максимум 9 игроков
    if len(multi_games[chat_id]['players']) >= 9:
        multi_games[chat_id]['status'] = 'playing'
        start_multi_game(chat_id)

# Запуск мульти-игры
def start_multi_game(chat_id):
    game = multi_games[chat_id]
    deck = game['deck']
    for uid in game['players']:
        game['players'][uid]['hand'] = [deck.pop(), deck.pop()]
    game['turn_order'] = list(game['players'].keys())
    game['current'] = 0
    game['status'] = 'playing'
    update_multi_message(chat_id)

# Обновление состояния игры в чате
def update_multi_message(chat_id):
    game = multi_games[chat_id]
    deck = game['deck']
    dealer = [deck[0], "❓"]
    text = f"🎴 Дилер: {dealer}\n\n🧍 Игроки:\n"
    for idx, uid in enumerate(game['turn_order']):
        pdata = game['players'][uid]
        name = f"@{pdata['username']}"
        val = hand_value(pdata['hand'])
        marker = "⬅️ (ход)" if idx == game['current'] else ""
        text += f"{idx+1}. {name}: {pdata['hand']} = {val} {marker}\n"
    current_id = game['turn_order'][game['current']]
    text += f"\n@{game['players'][current_id]['username']}, какой делаешь выбор: доб, стоп, кэш или дабл?"
    bot.send_message(chat_id, text)

# Обработка команд игроков во время хода
@bot.message_handler(func=lambda m: m.text.lower() in ["доб", "стоп", "кэш", "дабл"])
def multi_player_turn(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.lower()

    if chat_id not in multi_games:
        return
    game = multi_games[chat_id]
    if game['status'] != 'playing':
        return
    if user_id != game['turn_order'][game['current']]:
        bot.send_message(chat_id, f"⚠ @{get_username(user_id)}, сейчас не твой ход!")
        return

    pdata = game['players'][user_id]
    deck = game['deck']

    if text == "доб":
        pdata['hand'].append(deck.pop())
        if hand_value(pdata['hand']) > 21:
            pdata['done'] = True
            bot.send_message(chat_id, f"💥 @{pdata['username']} перебор!")
            next_turn(chat_id)
        else:
            bot.send_message(chat_id, f"🃏 @{pdata['username']} добрал карту: {pdata['hand']}")
    elif text == "стоп":
        pdata['done'] = True
        bot.send_message(chat_id, f"✋ @{pdata['username']} завершил ход.")
        next_turn(chat_id)
    elif text == "кэш":
        refund = int(pdata['bet'] * 0.6)
        update_balance(user_id, get_balance(user_id) + refund)
        pdata['done'] = True
        bot.send_message(chat_id, f"💰 @{pdata['username']} сделал кэш-аут! Возврат {refund} монет.")
        next_turn(chat_id)
    elif text == "дабл":
        if get_balance(user_id) < pdata['bet']:
            bot.send_message(chat_id, f"❌ @{pdata['username']} недостаточно средств для дабла.")
            return
        update_balance(user_id, get_balance(user_id) - pdata['bet'])
        pdata['bet'] *= 2
        pdata['doubled'] = True
        pdata['hand'].append(deck.pop())
        if hand_value(pdata['hand']) > 21:
            pdata['done'] = True
        bot.send_message(chat_id, f"🔥 @{pdata['username']} сделал дабл! Новая рука: {pdata['hand']}")
        next_turn(chat_id)

    update_multi_message(chat_id)

def next_turn(chat_id):
    game = multi_games[chat_id]
    while True:
        game['current'] += 1
        if game['current'] >= len(game['turn_order']):
            end_multi_game(chat_id)
            return
        current_id = game['turn_order'][game['current']]
        if not game['players'][current_id]['done']:
            break
    update_multi_message(chat_id)

def end_multi_game(chat_id):
    game = multi_games[chat_id]
    deck = game['deck']
    dealer = [deck.pop(), deck.pop()]
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())
    text = f"🎴 Дилер: {dealer} = {hand_value(dealer)}\n\n🧍 Игроки:\n"
    for uid in game['turn_order']:
        pdata = game['players'][uid]
        val = hand_value(pdata['hand'])
        name = f"@{pdata['username']}"
        bet = pdata['bet']
        balance = get_balance(uid)
        if val > 21:
            result = f"💥 Перебор! Проиграл {bet} монет"
        elif hand_value(dealer) > 21 or val > hand_value(dealer):
            win = bet * 2
            update_balance(uid, balance + win)
            result = f"🎉 Победа! +{win} монет"
        elif val == hand_value(dealer):
            update_balance(uid, balance + bet)
            result = f"🤝 Ничья. Ставка возвращена"
        else:
            result = f"😢 Проигрыш {bet} монет"
        text += f"{name}: {pdata['hand']} = {val} → {result}\n"
    bot.send_message(chat_id, text)
    bot.send_message(chat_id, "🎮 Мульти-игра завершена!")
    del multi_games[chat_id]

# ---------------- Запуск ----------------
bot.infinity_polling()