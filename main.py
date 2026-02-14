import telebot
from telebot import types
import random
import threading
import time

TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
bot = telebot.TeleBot(TOKEN)

games = {}
balances = {}
START_BALANCE = 500
MAX_PLAYERS = 9
WAIT_TIME = 120  # 2 минуты ожидания набора игроков

SUITS = ['♠️','♥️','♦️','♣️']

# ================== Карты ==================
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
    elif card[0]=='A1':
        return 1
    else:
        return int(card[0])

def calculate_score(hand):
    score = sum(card_value(c) for c in hand)
    while score>21 and any(c[0]=='A' for c in hand):
        for c in hand:
            if c[0]=='A':
                hand[hand.index(c)] = ('A1', c[1])
                break
        score = sum(card_value(c) for c in hand)
    return score

def format_hand(hand):
    return ' '.join(f"{c[0]}{c[1]}" for c in hand)

# ================== Регистрация ==================
@bot.message_handler(func=lambda m: m.text.lower() == "б")
def register(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"🎮 Привет, {message.from_user.first_name}! Баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances[user_id]} монет.")

# ================== Начало набора ==================
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def start_black(message):
    chat_id = message.chat.id
    if chat_id in games and not games[chat_id].get("ended",True):
        bot.send_message(chat_id, "🚫 Игра уже идёт!")
        return
    games[chat_id] = {"players":[],"deck":create_deck(),"started":False,"votes":{},"ended":False}
    bot.send_message(chat_id,"🎲 Набор игроков. Если хочешь сесть за стол, напиши 'да'.")

# ================== Игрок пишет "да" ==================
@bot.message_handler(func=lambda m: m.text.lower() == "да")
def want_to_join(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game: return
    if any(p['id']==user_id for p in game["players"]):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Присоединиться к столу"))
    bot.send_message(chat_id, "Нажмите кнопку чтобы присоединиться за стол", reply_markup=markup)

# ================== Присоединение ==================
@bot.message_handler(func=lambda m: m.text.lower() == "присоединиться к столу")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    game = games.get(chat_id)
    if not game: return
    if len(game["players"]) >= MAX_PLAYERS:
        bot.send_message(chat_id,"🚫 Стол уже заполнен!")
        return
    if balances.get(user_id,0)<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        bot.send_message(chat_id,"", reply_markup=types.ReplyKeyboardRemove())
        return
    msg = bot.send_message(chat_id,f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)

def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet<=0 or bet>balances[user_id]:
            bot.send_message(message.chat.id,"❌ Ставка должна быть числом и не превышать баланс.")
            return
    except:
        bot.send_message(message.chat.id,"❌ Ставка должна быть числом.")
        return
    balances[user_id]-=bet
    game["players"].append({"id":user_id,"name":user_name,"hand":[],"bet":bet,"stand":False,"cashout=False})
    bot.send_message(message.chat.id,f"🪑 {user_name} присоединился за стол со ставкой {bet}.")
    bot.send_message(message.chat.id,"", reply_markup=types.ReplyKeyboardRemove())
    send_vote_buttons(chat_id, user_id)
    if len(game["players"]) == MAX_PLAYERS:
        bot.send_message(chat_id,"Игра скоро начнется, дилер раздает карты…")
        threading.Timer(10, start_game, args=[chat_id]).start()
    else:
        threading.Thread(target=wait_and_start, args=[chat_id]).start()

# ================== Таймер ожидания ==================
def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    time.sleep(WAIT_TIME)
    if not game["started"] and len(game["players"])>0:
        start_game(chat_id)

# ================== Голосование ==================
def send_vote_buttons(chat_id, user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Да"), types.KeyboardButton("Нет, ждать других участников"))
    bot.send_message(chat_id,"Хотите начать игру сразу?", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text.lower() in ["да","нет, ждать других участников"])
def vote(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game: return
    if not any(p['id']==user_id for p in game["players"]):
        return
    game["votes"][user_id] = message.text.lower()
    bot.send_message(chat_id,"Вы проголосовали.", reply_markup=types.ReplyKeyboardRemove())
    votes = list(game["votes"].values())
    if len(votes)==len(game["players"]):
        yes = votes.count("да")
        no = votes.count("нет, ждать других участников")
        if yes>no:
            bot.send_message(chat_id,"Игра скоро начнется, дилер раздает карты…")
            threading.Timer(10, start_game, args=[chat_id]).start()
        else:
            bot.send_message(chat_id,"🕒 Игроки выбрали ждать других участников.")

# ================== Начало игры ==================
def start_game(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    game["started"] = True
    deck = game["deck"]
    for p in game["players"]:
        p["hand"].append(deck.pop())
        p["hand"].append(deck.pop())
    game["dealer"] = {"hand":[deck.pop(),deck.pop()]}
    bot.send_message(chat_id,"🃏 Игра началась!")
    for p in game["players"]:
        send_player_buttons(chat_id, p["id"])
    send_game_state(chat_id)

# ================== Добор, Стоп, Кэш ==================
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def player_action(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    action = message.text.lower()
    game = games.get(chat_id)
    if not game: return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player: return
    if player["stand"] or player.get("cashout"): return
    deck = game["deck"]
    if action=="доб":
        player["hand"].append(deck.pop())
        score = calculate_score(player["hand"])
        bot.send_message(chat_id,f"{player['name']} добрал карту. Очки: {score}")
        if score>21:
            bot.send_message(chat_id,f"💥 {player['name']} перебор! Выбывает.")
            player["stand"]=True
            player["cashout"]=True
            bot.send_message(chat_id,"", reply_markup=types.ReplyKeyboardRemove())
    elif action=="стоп":
        player["stand"]=True
        bot.send_message(chat_id,f"✋ {player['name']} остановился.", reply_markup=types.ReplyKeyboardRemove())
    elif action=="кэш":
        player["cashout"]=True
        refund = int(player["bet"]*0.7)
        balances[user_id]+=refund
        bot.send_message(chat_id,f"{player['name']} забрал кэш 70%: {refund} монет.", reply_markup=types.ReplyKeyboardRemove())
    # Проверяем окончание игры
    if all(p["stand"] or p.get("cashout") for p in game["players"]):
        threading.Timer(5,end_game,args=[chat_id]).start()

# ================== Завершение игры ==================
def end_game(chat_id):
    game = games.get(chat_id)
    if not game: return
    deck = game["deck"]
    dealer = game["dealer"]
    # Дилер добирает карты
    while calculate_score(dealer["hand"])<17:
        dealer["hand"].append(deck.pop())
    dealer_score = calculate_score(dealer["hand"])
    bot.send_message(chat_id,f"Дилер: {format_hand(dealer['hand'])} (Очки: {dealer_score})")
    for p in game["players"]:
        if p.get("cashout"):
            continue
        score = calculate_score(p["hand"])
        if score>21:
            bot.send_message(chat_id,f"{p['name']} перебор и проиграл.")
        elif dealer_score>21 and score<=21:
            balances[p["id"]]+=p["bet"]*2
            bot.send_message(chat_id,f"{p['name']} выигрывает! (Дилер перебор)")
        elif score==dealer_score:
            balances[p["id"]]+=p["bet"]
            bot.send_message(chat_id,f"{p['name']} ничья с дилером.")
        elif score>dealer_score:
            balances[p["id"]]+=p["bet"]*2
            bot.send_message(chat_id,f"{p['name']} выигрывает!")
        else:
            bot.send_message(chat_id,f"{p['name']} проиграл.")
    game["ended"]=True
    games.pop(chat_id)