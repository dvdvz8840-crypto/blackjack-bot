import telebot
from telebot import types
import random
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 6151671553  # твой Telegram ID, только он сможет выдавать монеты

games = {}
balances = {}
cooldowns = {}

START_BALANCE = 500
COOLDOWN_TIME = 120  # 2 минуты
MAX_PLAYERS = 9

SUITS = ['♠️', '♥️', '♦️', '♣️']

# ==================== Игровая логика ====================
def create_deck():
    deck = []
    for suit in SUITS:
        for card in [2,3,4,5,6,7,8,9,10,'J','Q','K','A']:
            deck.append((str(card), suit))
    random.shuffle(deck)
    return deck

def card_value(card):
    if card[0] in ['J','Q','K']:
        return 10
    elif card[0]=='A':
        return 11
    else:
        return int(card[0])

def calculate_score(hand):
    score = sum(card_value(c) for c in hand)
    while score>21 and any(c[0]=='A' for c in hand):
        for c in hand:
            if c[0]=='A':
                hand[hand.index(c)] = ('A1', c[1])
                break
        score = sum(card_value(c) if c[0]!='A1' else 1 for c in hand)
    return score

def format_hand(hand):
    return ' '.join(f"{c[0]}{c[1]}" for c in hand)

def format_game_state(game, hide_dealer=True):
    text = ""
    if hide_dealer:
        text += f"Дилер: [{format_hand([game['dealer']['hand'][0]])}, ❓]\n"
    else:
        dealer_score = calculate_score(game['dealer']['hand'])
        text += f"Дилер: {format_hand(game['dealer']['hand'])} (Очки: {dealer_score})\n"
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {format_hand(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]}\n"
    return text

# ==================== Основные команды ====================
@bot.message_handler(func=lambda m: m.text.lower() == "б")
def register(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"🎮 Привет, {message.from_user.first_name}! 💰 Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def show_commands(message):
    text = (
        "📜 Доступные команды:\n"
        "б — регистрация и баланс\n"
        "бал — показать баланс\n"
        "блек — начать набор игроков за стол\n"
        "п (сумма) — передать монеты (ответ на сообщение пользователя)\n"
        "кэш — выход из игры с 60% возврата ставки\n"
        "доб — взять карту\n"
        "стоп — остановиться\n"
    )
    bot.send_message(message.chat.id, text)

# ==================== Блекджек ====================
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def start_black(message):
    chat_id = message.chat.id
    if chat_id in games and games[chat_id]["started"]:
        bot.send_message(chat_id, "🚫 Игра уже идет!")
        return

    games[chat_id] = {
        "players": [],
        "deck": create_deck(),
        "started": False
    }

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_join = types.KeyboardButton("Сесть за стол")
    markup.add(btn_join)
    bot.send_message(chat_id, "🎲 Набор игроков начат! Максимум 9 игроков.\nНажмите кнопку чтобы присоединиться за стол.", reply_markup=markup)

    threading.Thread(target=wait_and_start, args=(chat_id,)).start()

@bot.message_handler(func=lambda m: m.text.lower() == "сесть за стол")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id not in games:
        bot.send_message(chat_id, "Сначала напишите 'блек', чтобы начать игру.")
        return
    game = games[chat_id]

    for p in game["players"]:
        if p["id"] == user_id:
            bot.send_message(chat_id, "❌ Вы уже за столом.")
            return

    if user_id not in balances or balances[user_id] <= 0:
        bot.send_message(chat_id, "❌ У вас недостаточно средств, чтобы присоединиться.")
        return

    # Скрываем кнопку у игрока
    bot.send_message(chat_id, f"🪑 {user_name} присоединился за стол.")
    msg = bot.send_message(chat_id, f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)

def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet <=0 or bet > balances[user_id]:
            bot.send_message(message.chat.id, f"🛑 Недостаточно средств, чтобы поставить такую ставку.")
            msg = bot.send_message(message.chat.id, f"{user_name}, введите вашу ставку:")
            bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)
            return
    except:
        bot.send_message(message.chat.id, f"❌ Ставка должна быть числом.")
        msg = bot.send_message(message.chat.id, f"{user_name}, введите вашу ставку:")
        bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)
        return

    balances[user_id] -= bet
    game["players"].append({
        "id": user_id,
        "name": user_name,
        "hand": [],
        "bet": bet,
        "stand": False,
        "cashout": False
    })
    bot.send_message(message.chat.id, f"🪑 {user_name} присоединился за стол со ставкой 🪙 {bet} монет.\n💰 Ваш баланс: {balances[user_id]} монет.\nОжидание ставок других участников... Если никто не присоединится, игра начнется через 2 минуты.")

    if len(game["players"]) == MAX_PLAYERS:
        start_game(message.chat.id)

def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    time.sleep(120)
    if not game["started"] and len(game["players"])>0:
        start_game(chat_id)

def start_game(chat_id):
    game = games[chat_id]
    game["started"] = True
    deck = game["deck"]

    for player in game["players"]:
        player["hand"].append(deck.pop())
        player["hand"].append(deck.pop())

    game["dealer"] = {"hand":[deck.pop(),deck.pop()]}

    # Начинаем ход первого игрока
    next_turn(chat_id, 0)

def next_turn(chat_id, index):
    game = games.get(chat_id)
    if not game: return
    if index >= len(game["players"]):
        finish_game(chat_id)
        return

    player = game["players"][index]
    if player["stand"] or player["cashout"]:
        next_turn(chat_id, index+1)
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("доб"), types.KeyboardButton("стоп"), types.KeyboardButton("кэш"))
    bot.send_message(chat_id, f"✋ Сейчас ход {player['name']}", reply_markup=markup)

    # Сохраняем кто сейчас ходит
    game["current_player_index"] = index

# ==================== Игровые действия ====================
@bot.message_handler(func=lambda m: m.text.lower() == "доб")
def handle_hit(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    game = games.get(chat_id)
    if not game: return
    idx = game.get("current_player_index", 0)
    player = game["players"][idx]
    if player["id"] != user_id:
        return  # только текущий игрок может нажимать кнопки
    player["hand"].append(game["deck"].pop())
    score = calculate_score(player["hand"])
    if score>21:
        player["stand"]=True
        bot.send_message(chat_id,f"💥 {player['name']} перебор! Очки: {score}")
        next_turn(chat_id, idx+1)
    else:
        bot.send_message(chat_id,f"🃏 {player['name']} взял карту. Очки: {score}")

@bot.message_handler(func=lambda m: m.text.lower() == "стоп")
def handle_stand(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    game = games.get(chat_id)
    if not game: return
    idx = game.get("current_player_index", 0)
    player = game["players"][idx]
    if player["id"] != user_id:
        return
    player["stand"] = True
    bot.send_message(chat_id,f"✋ {player['name']} остановился.")
    next_turn(chat_id, idx+1)

@bot.message_handler(func=lambda m: m.text.lower() == "кэш")
def handle_cash(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    game = games.get(chat_id)
    if not game: return
    idx = game.get("current_player_index", 0)
    player = game["players"][idx]
    if player["id"] != user_id:
        return
    payout = int(player["bet"]*0.6)
    balances[user_id] += payout
    player["cashout"] = True
    player["stand"] = True
    bot.send_message(chat_id,f"💸 {player['name']} забрал {payout} монет (60% ставки).")
    next_turn(chat_id, idx+1)

# ==================== Завершение игры ====================
def finish_game(chat_id):
    game = games.get(chat_id)
    if not game: return
    deck = game["deck"]
    dealer = game["dealer"]
    dealer_total = calculate_score(dealer["hand"])
    while dealer_total<17:
        dealer["hand"].append(deck.pop())
        dealer_total = calculate_score(dealer["hand"])

    text = f"🏁 Игра окончена!\nДилер: {format_hand(dealer['hand'])} (Очки: {dealer_total})\n\n"
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {format_hand(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]}\n"

    for p in game["players"]:
        # Победа если дилер перебрал
        player_score = calculate_score(p["hand"])
        if player_score <=21 and dealer_total>21:
            balances[p["id"]] += p["bet"]*2
            text += f"🏆 {p['name']} выигрывает, дилер перебрал!\n"
        elif player_score == dealer_total == 21:
            balances[p["id"]] += p["bet"]
            text += f"⚖️ {p['name']} ничья с дилером!\n"
        elif player_score>dealer_total and player_score<=21:
            balances[p["id"]] += p["bet"]*2
            text += f"🏆 {p['name']} побеждает!\n"
        # проигрыш автоматически, ставка не возвращается если < дилер

    for p in game["players"]:
        cooldowns[p["id"]] = time.time() + COOLDOWN_TIME

    bot.send_message(chat_id,text,reply_markup=types.ReplyKeyboardRemove())
    del games[chat_id]

# ==================== Передача монет ====================
@bot.message_handler(func=lambda m: m.text.lower().startswith("п "))
def transfer_coins(message):
    user_id = message.from_user.id
    if not message.reply_to_message:
        bot.send_message(message.chat.id, "❌ Чтобы передать монеты, ответьте на сообщение игрока.")
        return
    try:
        amount = int(message.text.split()[1])
        if amount <=0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0.")
            return
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат команды. Используйте: п (сумма) и ответ на сообщение игрока")
        return
    target_id = message.reply_to_message.from_user.id
    if balances.get(user_id,0)<amount:
        bot.send_message(message.chat.id,f"❌ У вас нет {amount} монет, чтобы передать.")
        return
    balances[user_id]-=amount
    balances[target_id] = balances.get(target_id, START_BALANCE)+amount
    bot.send_message(message.chat.id,f"💰 {message.from_user.first_name} передал {amount} монет {message.reply_to_message.from_user.first_name}")

# ==================== Админская выдача монет ====================
@bot.message_handler(func=lambda m: m.text.lower().startswith("деньги "))
def give_money(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав на выдачу монет.")
        return
    try:
        amount = int(message.text.split()[1])
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше 0.")
            return
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат. Используйте: деньги (сумма)")
        return
    balances[user_id] = balances.get(user_id,0)+amount
    bot.send_message(message.chat.id, f"💰 Вы получили {amount} монет. Баланс: {balances[user_id]}")

# ==================== Запуск бота ====================
bot.infinity_polling()