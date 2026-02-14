import telebot
from telebot import types
import random
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

games = {}
balances = {}
cooldowns = {}

START_BALANCE = 500
COOLDOWN_TIME = 120
WAIT_TIME = 120
ACTION_TIMEOUT = 180
MAX_PLAYERS = 9

# ================= КАРТЫ =================

def create_deck():
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    return deck

def calculate_score(hand):
    score = sum(hand)
    while score > 21 and 11 in hand:
        hand[hand.index(11)] = 1
        score = sum(hand)
    return score

# ================= КНОПКИ =================

def player_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("доб","стоп","кэш")
    return markup

# ================= ОСНОВНЫЕ КОМАНДЫ =================

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="б")
def start_cmd(m):
    uid = m.from_user.id
    if uid not in balances:
        balances[uid] = START_BALANCE
    bot.send_message(m.chat.id,f"🎮 Баланс: {balances[uid]}")

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="бал")
def bal_cmd(m):
    uid = m.from_user.id
    balances.setdefault(uid, START_BALANCE)
    bot.send_message(m.chat.id,f"💰 Баланс: {balances[uid]}")

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="бкоманды")
def help_cmd(m):
    bot.send_message(m.chat.id,"Команды:\nб\nбал\nблек\nп (сумма)")

# ================= ПЕРЕВОД =================

@bot.message_handler(func=lambda m: m.text and m.text.startswith("п "))
def transfer(m):
    if not m.reply_to_message:
        return
    sender = m.from_user.id
    receiver = m.reply_to_message.from_user.id

    try:
        amount = int(m.text.split()[1])
    except:
        return

    if balances.get(sender,0) < amount:
        bot.send_message(m.chat.id,"Недостаточно средств.")
        return

    balances[sender] -= amount
    balances[receiver] = balances.get(receiver,START_BALANCE)+amount
    bot.send_message(m.chat.id,f"Перевод {amount} выполнен.")

# ================= НАЧАТЬ ИГРУ =================

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="блек")
def start_black(m):
    chat_id = m.chat.id
    if chat_id in games:
        bot.send_message(chat_id,"Игра уже идет.")
        return

    games[chat_id] = {
        "players": [],
        "deck": create_deck(),
        "started": False,
        "turn": 0,
        "last_action": time.time()
    }

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True,one_time_keyboard=True)
    markup.add("Сесть за стол")
    bot.send_message(chat_id,"Набор игроков начат (макс 9).",reply_markup=markup)

    threading.Thread(target=wait_start,args=(chat_id,)).start()

# ================= СЕСТЬ =================

@bot.message_handler(func=lambda m: m.text=="Сесть за стол")
def join(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    name = m.from_user.first_name

    game = games.get(chat_id)
    if not game or game["started"]:
        return

    bot.send_message(chat_id,"Введите ставку:",reply_markup=types.ReplyKeyboardRemove())
    msg = bot.send_message(chat_id,"💰 Ваша ставка?")
    bot.register_next_step_handler(msg,set_bet,chat_id,uid,name)

def set_bet(message,chat_id,uid,name):
    game = games.get(chat_id)
    if not game:
        return

    try:
        bet = int(message.text)
    except:
        msg = bot.send_message(chat_id,"Введите число:")
        bot.register_next_step_handler(msg,set_bet,chat_id,uid,name)
        return

    balances.setdefault(uid,START_BALANCE)

    if bet > balances[uid]:
        msg = bot.send_message(chat_id,"🛑 Недостаточно средств, чтобы поставить такую ставку")
        bot.register_next_step_handler(msg,set_bet,chat_id,uid,name)
        return

    if bet <= 0:
        msg = bot.send_message(chat_id,"Введите корректную ставку:")
        bot.register_next_step_handler(msg,set_bet,chat_id,uid,name)
        return

    balances[uid] -= bet

    game["players"].append({
        "id": uid,
        "name": name,
        "hand": [],
        "bet": bet,
        "stand": False,
        "cashout": False
    })

    bot.send_message(chat_id,f"{name} сел за стол со ставкой {bet}")
    bot.send_message(chat_id,
                     "Ожидание ставок других участников.\n"
                     "Если никто не присоединится, игра начнется через 2 минуты.")

    if len(game["players"]) == MAX_PLAYERS:
        bot.send_message(chat_id,"Игра скоро начнется… Дилер раздает карты")
        time.sleep(10)
        start_game(chat_id)

# ================= ТАЙМЕР ОЖИДАНИЯ =================

def wait_start(chat_id):
    time.sleep(WAIT_TIME)
    game = games.get(chat_id)
    if game and not game["started"] and len(game["players"]) > 0:
        start_game(chat_id)

# ================= СТАРТ =================

def start_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return

    game["started"] = True

    for p in game["players"]:
        p["hand"] = [game["deck"].pop(), game["deck"].pop()]

    game["dealer"] = {"hand":[game["deck"].pop(),game["deck"].pop()]}

    bot.send_message(chat_id,f"Дилер: {game['dealer']['hand'][0]} ❓")
    next_turn(chat_id)
    threading.Thread(target=action_timeout,args=(chat_id,)).start()

# ================= ХОДЫ =================

def next_turn(chat_id):
    game = games.get(chat_id)
    if not game:
        return

    players = game["players"]

    if game["turn"] >= len(players):
        finish_game(chat_id)
        return

    player = players[game["turn"]]

    if player["stand"] or player["cashout"]:
        game["turn"] += 1
        next_turn(chat_id)
        return

    score = calculate_score(player["hand"])
    bot.send_message(chat_id,
                     f"Ход {player['name']} ({score})",
                     reply_markup=player_keyboard())

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["доб","стоп","кэш"])
def action(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    game = games.get(chat_id)

    if not game or not game["started"]:
        return

    if game["turn"] >= len(game["players"]):
        return

    player = game["players"][game["turn"]]

    if player["id"] != uid:
        return

    game["last_action"] = time.time()

    if m.text.lower()=="доб":
        player["hand"].append(game["deck"].pop())
        if calculate_score(player["hand"])>21:
            player["stand"]=True

    elif m.text.lower()=="стоп":
        player["stand"]=True

    elif m.text.lower()=="кэш":
        refund=int(player["bet"]*0.6)
        balances[uid]+=refund
        player["cashout"]=True
        player["stand"]=True

    bot.send_message(chat_id,"Ход завершен.",reply_markup=types.ReplyKeyboardRemove())
    game["turn"]+=1
    next_turn(chat_id)

# ================= АВТО ОТМЕНА =================

def action_timeout(chat_id):
    while chat_id in games:
        time.sleep(5)
        game = games.get(chat_id)
        if not game or not game["started"]:
            return
        if time.time()-game["last_action"] > ACTION_TIMEOUT:
            for p in game["players"]:
                balances[p["id"]] += p["bet"]
            bot.send_message(chat_id,"⛔ Игра отменена из-за бездействия. Ставки возвращены.")
            del games[chat_id]
            return

# ================= ФИНИШ =================

def finish_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return

    dealer = game["dealer"]

    while calculate_score(dealer["hand"]) < 17:
        dealer["hand"].append(game["deck"].pop())

    dealer_score = calculate_score(dealer["hand"])
    text = f"Дилер: {dealer['hand']} ({dealer_score})\n\n"

    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {score}\n"

        if p["cashout"]:
            continue

        if dealer_score > 21 and score <= 21:
            balances[p["id"]] += p["bet"]*2
        elif dealer_score == 21:
            if score == 21:
                balances[p["id"]] += p["bet"]
        else:
            if score <= 21 and score > dealer_score:
                balances[p["id"]] += p["bet"]*2
            elif score == dealer_score:
                balances[p["id"]] += p["bet"]

        cooldowns[p["id"]] = time.time()+COOLDOWN_TIME

    bot.send_message(chat_id,text)
    del games[chat_id]

bot.infinity_polling()