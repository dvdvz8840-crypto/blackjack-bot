import telebot
from telebot import types
import random
import time
import threading

TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
bot = telebot.TeleBot(TOKEN)

games = {}
balances = {}
cooldowns = {}

START_BALANCE = 500
COOLDOWN_TIME = 180
MAX_PLAYERS = 3

SUITS = ['♠️', '♥️', '♦️', '♣️']

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
    # Дилер
    if hide_dealer:
        text += f"Дилер: [{format_hand([game['dealer']['hand'][0]])}, ❓]\n"
    else:
        dealer_score = calculate_score(game['dealer']['hand'])
        text += f"Дилер: {format_hand(game['dealer']['hand'])} (Очки: {dealer_score})\n"
    # Игроки
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {format_hand(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]}\n"
    return text

# ================= Команды =================

@bot.message_handler(func=lambda m: m.text.lower() == "б")
def register(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"🎮 Привет, {message.from_user.first_name}! Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def start_black(message):
    chat_id = message.chat.id
    if chat_id in games:
        bot.send_message(chat_id, "🚫 Игра уже идет!")
        return

    games[chat_id] = {
        "players": [],
        "deck": create_deck(),
        "started": False
    }

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_join = types.KeyboardButton("Присоединиться к столу")
    markup.add(btn_join)
    bot.send_message(chat_id, "Набор игроков начат! Максимум 3 игрока.\nНажмите кнопку чтобы присоединиться за стол.", reply_markup=markup)

    threading.Thread(target=wait_and_start, args=(chat_id,)).start()

@bot.message_handler(func=lambda m: m.text.lower() == "присоединиться к столу")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id not in games:
        bot.send_message(chat_id, "Сначала начните игру командой 'блек'.")
        return
    game = games[chat_id]

    if len(game["players"]) >= MAX_PLAYERS:
        bot.send_message(chat_id, "🚫 Стол уже заполнен!")
        return

    if user_id not in balances or balances[user_id] <= 0:
        bot.send_message(chat_id, "❌ У вас недостаточно средств, чтобы присоединиться.")
        return

    msg = bot.send_message(chat_id, f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)

def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet <=0 or bet > balances[user_id]:
            bot.send_message(message.chat.id, f"❌ У вас недостаточно средств или неверная ставка.")
            return
    except:
        bot.send_message(message.chat.id, f"❌ Ставка должна быть числом.")
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

    bot.send_message(message.chat.id, f"🪑 {user_name} присоединился за стол со ставкой {bet}.")

    if len(game["players"]) == MAX_PLAYERS:
        start_game(message.chat.id)

def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    time.sleep(180)
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

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("доб"), types.KeyboardButton("стоп"), types.KeyboardButton("кэш"))

    text = "🃏 Игра началась!\n\n"
    text += format_game_state(game, hide_dealer=True)
    bot.send_message(chat_id, text, reply_markup=markup)

def hit_card(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game: return
    for player in game["players"]:
        if player["id"]==user_id and not player["stand"]:
            player["hand"].append(game["deck"].pop())
            score = calculate_score(player["hand"])
            if score>21:
                player["stand"]=True
                bot.send_message(chat_id,f"💥 {player['name']} перебор! Очки: {score}")
            else:
                bot.send_message(chat_id,f"🃏 {player['name']} взял карту. Очки: {score}")
    send_game_state(chat_id)
    check_finish(chat_id)

def stand_card(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game: return
    for player in game["players"]:
        if player["id"]==user_id:
            player["stand"]=True
            bot.send_message(chat_id,f"✋ {player['name']} остановился.")
    send_game_state(chat_id)
    check_finish(chat_id)

def cash(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game: return
    for player in game["players"]:
        if player["id"]==user_id and not player["cashout"]:
            payout = int(player["bet"]*0.7)
            balances[user_id] += payout
            player["cashout"] = True
            player["stand"] = True
            bot.send_message(chat_id,f"💸 {player['name']} забрал {payout} монет (70% ставки).")
    send_game_state(chat_id)
    check_finish(chat_id)

def send_game_state(chat_id, hide_dealer=True):
    game = games.get(chat_id)
    if not game: return
    text = "📊 Текущее состояние игры:\n"
    text += format_game_state(game, hide_dealer)
    bot.send_message(chat_id,text)

def check_finish(chat_id):
    game = games.get(chat_id)
    if not game: return
    if all(p["stand"] or p["cashout"] for p in game["players"]):
        finish_game(chat_id)

def finish_game(chat_id):
    game = games.get(chat_id)
    deck = game["deck"]
    dealer = game["dealer"]
    dealer_total = calculate_score(dealer["hand"])
    while dealer_total<17:
        dealer["hand"].append(deck.pop())
        dealer_total = calculate_score(dealer["hand"])

    text = f"🏁 Игра окончена!\nДилер: {format_hand(dealer['hand'])} (Очки: {dealer_total})\n\n"
    winner = None
    best_score = 0
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {format_hand(p['hand'])} (Очки: {score})\n"
        if not p["cashout"] and score<=21 and score>best_score:
            best_score=score
            winner=p

    if winner:
        balances[winner["id"]] += winner["bet"]*2
        text += f"\n🏆 Победил {winner['name']}! Выигрыш: {winner['bet']*2}"
    else:
        text += "\nНикто не выиграл."

    for p in game["players"]:
        cooldowns[p["id"]] = time.time() + COOLDOWN_TIME

    bot.send_message(chat_id,text,reply_markup=types.ReplyKeyboardRemove())
    del games[chat_id]

# ================= Обработчики команд =================
@bot.message_handler(func=lambda m: m.text.lower()=="доб")
def handle_hit(m):
    hit_card(m)

@bot.message_handler(func=lambda m: m.text.lower()=="стоп")
def handle_stand(m):
    stand_card(m)

@bot.message_handler(func=lambda m: m.text.lower()=="кэш")
def handle_cash(m):
    cash(m)

bot.infinity_polling()