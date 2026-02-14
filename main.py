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
MAX_PLAYERS = 9

SUITS = ['♠️','♥️','♦️','♣️']

# ================= КАРТЫ =================

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
    if card[0] == 'A':
        return 11
    if card[0] == 'A1':
        return 1
    return int(card[0])

def calculate_score(hand):
    score = sum(card_value(c) for c in hand)
    while score > 21 and any(c[0]=='A' for c in hand):
        for i,c in enumerate(hand):
            if c[0]=='A':
                hand[i]=('A1',c[1])
                break
        score = sum(card_value(c) for c in hand)
    return score

def format_hand(hand):
    return ' '.join(f"{c[0]}{c[1]}" for c in hand)

# ================= КНОПКИ =================

def player_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("доб","стоп","кэш")
    return markup

# ================= ОСНОВНЫЕ КОМАНДЫ =================

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="б")
def start_cmd(m):
    uid=m.from_user.id
    if uid not in balances:
        balances[uid]=START_BALANCE
    bot.send_message(m.chat.id,f"🎮 Привет! Баланс: {balances[uid]}")

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="бал")
def bal_cmd(m):
    uid=m.from_user.id
    if uid not in balances:
        balances[uid]=START_BALANCE
    bot.send_message(m.chat.id,f"💰 Баланс: {balances[uid]}")

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="бкоманды")
def help_cmd(m):
    bot.send_message(m.chat.id,
                     "Команды:\n"
                     "б\n"
                     "бал\n"
                     "блек\n"
                     "п (сумма)")

# ================= ПЕРЕВОД =================

@bot.message_handler(func=lambda m: m.text and m.text.startswith("п "))
def transfer(m):
    if not m.reply_to_message:
        return
    sender=m.from_user.id
    receiver=m.reply_to_message.from_user.id
    try:
        amount=int(m.text.split()[1])
    except:
        return
    if balances.get(sender,0)<amount:
        bot.send_message(m.chat.id,f"У вас нет {amount}, чтобы передать.")
        return
    balances[sender]-=amount
    balances[receiver]=balances.get(receiver,START_BALANCE)+amount
    bot.send_message(m.chat.id,f"Перевод {amount} выполнен.")

# ================= НАЧАТЬ ИГРУ =================

@bot.message_handler(func=lambda m: m.text and m.text.lower()=="блек")
def start_black(m):
    chat_id=m.chat.id
    now=time.time()
    if chat_id in games:
        bot.send_message(chat_id,"Игра уже идет.")
        return
    if m.from_user.id in cooldowns and now<cooldowns[m.from_user.id]:
        bot.send_message(chat_id,"Подождите 2 минуты перед новой игрой.")
        return

    games[chat_id]={
        "players":[],
        "deck":create_deck(),
        "started":False,
        "turn":0
    }

    markup=types.ReplyKeyboardMarkup(resize_keyboard=True,one_time_keyboard=True)
    markup.add("Сесть за стол")
    bot.send_message(chat_id,"Набор игроков начат (макс 9).",reply_markup=markup)

    threading.Thread(target=wait_start,args=(chat_id,)).start()

# ================= СЕСТЬ =================

@bot.message_handler(func=lambda m: m.text=="Сесть за стол")
def join(m):
    chat_id=m.chat.id
    uid=m.from_user.id
    name=m.from_user.first_name

    game=games.get(chat_id)
    if not game or game["started"]:
        return
    if len(game["players"])>=MAX_PLAYERS:
        return
    if balances.get(uid,0)<=0:
        bot.send_message(chat_id,"Недостаточно средств.")
        return

    bot.send_message(chat_id,"Введите ставку:",reply_markup=types.ReplyKeyboardRemove())
    msg=bot.send_message(chat_id,"💰 Ваша ставка?")
    bot.register_next_step_handler(msg,set_bet,game,uid,name)

def set_bet(message,game,uid,name):
    try:
        bet=int(message.text)
        if bet<=0 or bet>balances[uid]:
            return
    except:
        return

    balances[uid]-=bet
    game["players"].append({
        "id":uid,
        "name":name,
        "hand":[],
        "bet":bet,
        "stand":False,
        "cashout":False
    })

    bot.send_message(message.chat.id,f"{name} сел за стол со ставкой {bet}")
    bot.send_message(message.chat.id,
                     "Ожидание ставок других участников.\n"
                     "Если никто не присоединится, игра начнется через 2 минуты.")

    if len(game["players"])==MAX_PLAYERS:
        bot.send_message(message.chat.id,
                         "Игра скоро начнется… Дилер раздает карты")
        time.sleep(10)
        start_game(message.chat.id)

# ================= ТАЙМЕР =================

def wait_start(chat_id):
    time.sleep(WAIT_TIME)
    game=games.get(chat_id)
    if game and not game["started"] and len(game["players"])>0:
        start_game(chat_id)

# ================= СТАРТ =================

def start_game(chat_id):
    game=games[chat_id]
    game["started"]=True

    deck=game["deck"]
    for p in game["players"]:
        p["hand"]=[deck.pop(),deck.pop()]

    game["dealer"]={"hand":[deck.pop(),deck.pop()]}

    bot.send_message(chat_id,
                     f"Дилер: {format_hand([game['dealer']['hand'][0]])} ❓")

    next_turn(chat_id)

# ================= ХОДЫ =================

def next_turn(chat_id):
    game=games.get(chat_id)
    if not game:
        return
    players=game["players"]

    while game["turn"]<len(players):
        p=players[game["turn"]]
        if not p["stand"] and not p["cashout"]:
            score=calculate_score(p["hand"])
            bot.send_message(chat_id,
                             f"Ход {p['name']}\n"
                             f"{format_hand(p['hand'])} ({score})",
                             reply_markup=player_keyboard())
            return
        game["turn"]+=1

    finish_game(chat_id)

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["доб","стоп","кэш"])
def actions(m):
    chat_id=m.chat.id
    uid=m.from_user.id
    game=games.get(chat_id)
    if not game or not game["started"]:
        return

    player=game["players"][game["turn"]]
    if player["id"]!=uid:
        return

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

# ================= ФИНИШ =================

def finish_game(chat_id):
    game=games[chat_id]
    dealer=game["dealer"]
    deck=game["deck"]

    while calculate_score(dealer["hand"])<17:
        dealer["hand"].append(deck.pop())

    dealer_score=calculate_score(dealer["hand"])
    text=f"Дилер: {format_hand(dealer['hand'])} ({dealer_score})\n\n"

    for p in game["players"]:
        score=calculate_score(p["hand"])
        text+=f"{p['name']}: {format_hand(p['hand'])} ({score})\n"

        if p["cashout"]:
            continue

        if dealer_score>21 and score<=21:
            balances[p["id"]]+=p["bet"]*2
        elif dealer_score==21:
            if score==21:
                balances[p["id"]]+=p["bet"]
        else:
            if score<=21 and score>dealer_score:
                balances[p["id"]]+=p["bet"]*2
            elif score==dealer_score:
                balances[p["id"]]+=p["bet"]

        cooldowns[p["id"]]=time.time()+COOLDOWN_TIME

    bot.send_message(chat_id,text)
    del games[chat_id]

# ================= ЗАПУСК =================

bot.infinity_polling()