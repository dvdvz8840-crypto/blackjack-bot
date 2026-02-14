import telebot
from telebot import types
import random
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

# ================= Настройки =================
ADMIN_ID = 6151671553
START_BALANCE = 500
MAX_PLAYERS = 9
WAIT_TIME = 120  # время ожидания ставок 2 минуты
COOLDOWN_TIME = 120  # кулдаун после игры 2 минуты
SUITS = ['♠️', '♥️', '♦️', '♣️']

# ================= Данные =================
games = {}
balances = {}  # {user_id: {"balance": int, "username": str}}
cooldowns = {}

# ================= Карты =================
def create_deck():
    deck = [(str(n), s) for s in SUITS for n in [2,3,4,5,6,7,8,9,10,'J','Q','K','A']]
    random.shuffle(deck)
    return deck

def card_value(card):
    if card[0] in ['J','Q','K']: return 10
    if card[0]=='A': return 11
    if card[0]=='A1': return 1
    return int(card[0])

def calculate_score(hand):
    score = sum(card_value(c) for c in hand)
    while score > 21 and any(c[0]=='A' for c in hand):
        for i,c in enumerate(hand):
            if c[0]=='A':
                hand[i] = ('A1', c[1])
                break
        score = sum(card_value(c) for c in hand)
    return score

def format_hand(hand):
    return ' '.join(f"{c[0]}{c[1]}" for c in hand)

# ================= Состояние игры =================
def format_game_state(game, hide_dealer=True):
    text = ""
    # дилер
    if hide_dealer:
        text += f"Дилер: [{format_hand([game['dealer']['hand'][0]])}, ❓]\n"
    else:
        dealer_score = calculate_score(game['dealer']['hand'])
        text += f"Дилер: {format_hand(game['dealer']['hand'])} (Очки: {dealer_score})\n"
    # игроки
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {format_hand(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]['balance']}\n"
    return text

# ================= Команды =================
@bot.message_handler(func=lambda m: m.text.lower() == "б")
def register(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    if user_id not in balances:
        balances[user_id] = {"balance": START_BALANCE, "username": username}
    bot.send_message(message.chat.id, f"🎮 Привет, {message.from_user.first_name}! 💰 Ваш баланс: {balances[user_id]['balance']} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def balance(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    if user_id not in balances:
        balances[user_id] = {"balance": START_BALANCE, "username": username}
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances[user_id]['balance']} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def list_commands(message):
    cmds = "📜 Доступные команды:\n\n" \
           "б - зарегистрироваться\n" \
           "бал - показать баланс\n" \
           "блек - начать набор игроков\n" \
           "п (сумма) - передать монеты (через reply на сообщение)\n" \
           "кэш - забрать 60% ставки во время игры"
    bot.send_message(message.chat.id, cmds)

@bot.message_handler(func=lambda m: m.text.lower().startswith("п "))
def transfer_coins(message):
    user_id = message.from_user.id
    if user_id not in balances: return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Чтобы передать монеты, ответьте на сообщение того, кому хотите передать.")
        return
    try:
        amount = int(message.text.split()[1])
    except:
        bot.reply_to(message, "❌ Неверная сумма.")
        return
    if balances[user_id]["balance"] < amount:
        bot.reply_to(message, f"❌ У вас нет {amount}, чтобы передать.")
        return
    target_user = message.reply_to_message.from_user
    if target_user.id not in balances:
        balances[target_user.id] = {"balance": START_BALANCE, "username": target_user.username or target_user.first_name}
    balances[user_id]["balance"] -= amount
    balances[target_user.id]["balance"] += amount
    bot.reply_to(message, f"✅ {amount} монет передано @{target_user.username or target_user.first_name}.")

@bot.message_handler(func=lambda m: m.text.lower().startswith("деньги "))
def admin_add_money(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав.")
        return
    parts = message.text.split()
    if len(parts)<3:
        bot.reply_to(message,"❌ Используйте: деньги (сумма) @username")
        return
    try:
        amount = int(parts[1])
    except:
        bot.reply_to(message,"❌ Неверная сумма")
        return
    username = parts[2].lstrip("@").lower()
    target_id = None
    for uid,data in balances.items():
        if data.get("username","").lower()==username:
            target_id = uid
            break
    if not target_id:
        bot.reply_to(message,f"❌ Пользователь @{username} не найден")
        return
    balances[target_id]["balance"] += amount
    bot.reply_to(message,f"💰 Выдали {amount} монет @{username}. Новый баланс: {balances[target_id]['balance']}")

# ================= Начало игры =================
@bot.message_handler(func=lambda m: m.text.lower()=="блек")
def start_black(message):
    chat_id = message.chat.id
    if chat_id in games:
        bot.send_message(chat_id, "🚫 Игра уже идет!")
        return
    games[chat_id] = {
        "players": [],
        "deck": create_deck(),
        "started": False,
        "current": 0
    }
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("Сесть за стол")
    markup.add(btn)
    bot.send_message(chat_id,"🎲 Набор игроков! Нажмите кнопку, чтобы присоединиться за стол.", reply_markup=markup)
    threading.Thread(target=wait_and_start, args=(chat_id,)).start()

@bot.message_handler(func=lambda m: m.text.lower()=="сесть за стол")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    if chat_id not in games:
        bot.send_message(chat_id,"Сначала напишите 'блек' чтобы начать игру.")
        return
    game = games[chat_id]
    if any(p["id"]==user_id for p in game["players"]):
        bot.send_message(chat_id,"❌ Вы уже за столом.")
        return
    if balances[user_id]["balance"]<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return
    msg = bot.send_message(chat_id,f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg,set_bet,game,user_id,user_name)

def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet<=0 or bet>balances[user_id]["balance"]:
            bot.send_message(message.chat.id,"🛑 Недостаточно средств, чтобы поставить такую ставку.")
            msg = bot.send_message(message.chat.id,f"{user_name}, введите вашу ставку:")
            bot.register_next_step_handler(msg,set_bet,game,user_id,user_name)
            return
    except:
        bot.send_message(message.chat.id,"❌ Ставка должна быть числом.")
        msg = bot.send_message(message.chat.id,f"{user_name}, введите вашу ставку:")
        bot.register_next_step_handler(msg,set_bet,game,user_id,user_name)
        return
    balances[user_id]["balance"] -= bet
    game["players"].append({"id":user_id,"name":user_name,"hand":[],"bet":bet,"stand":False,"cashout":False})
    bot.send_message(message.chat.id,f"🪑 {user_name} присоединился за стол со ставкой 🪙 {bet} монет.\n💰 Ваш баланс: {balances[user_id]['balance']} монет.\nОжидание ставок других участников... Если никто не присоединится, игра начнется через 2 минуты.")
    # убрать кнопку
    markup = types.ReplyKeyboardRemove()
    bot.send_message(message.chat.id,"",reply_markup=markup)

def wait_and_start(chat_id):
    time.sleep(WAIT_TIME)
    game = games.get(chat_id)
    if game and not game["started"] and len(game["players"])>0:
        start_game(chat_id)

def start_game(chat_id):
    game = games[chat_id]
    game["started"]=True
    deck = game["deck"]
    # дилер
    game["dealer"]={"hand":[deck.pop(),deck.pop()]}
    # каждому игроку 2 карты
    for p in game["players"]:
        p["hand"].append(deck.pop())
        p["hand"].append(deck.pop())
    # начать первый ход
    bot.send_message(chat_id,"🃏 Игра началась!")
    send_state(chat_id, hide_dealer=True)
    start_turn(chat_id)

def send_state(chat_id, hide_dealer=True):
    game = games.get(chat_id)
    if not game: return
    text = "📊 Текущее состояние игры:\n"
    text += format_game_state(game, hide_dealer)
    bot.send_message(chat_id,text)

def start_turn(chat_id):
    game = games.get(chat_id)
    if not game: return
    while game["current"]<len(game["players"]):
        p = game["players"][game["current"]]
        if p["stand"] or p["cashout"]:
            game["current"] +=1
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("доб"), types.KeyboardButton("стоп"), types.KeyboardButton("кэш"))
            bot.send_message(chat_id,f"✋ Сейчас ход {p['name']}", reply_markup=markup)
            return
    # все игроки сделали ходы
    finish_game(chat_id)

def handle_hit(message):
    chat_id = message.chat.id
    game = games.get(chat_id)
    if not game: return
    p = game["players"][game["current"]]
    if message.from_user.id != p["id"]: return
    p["hand"].append(game["deck"].pop())
    score = calculate_score(p["hand"])
    bot.send_message(chat_id,f"🃏 {p['name']} взял карту. Очки: {score}")
    send_state(chat_id)
    if score>21:
        bot.send_message(chat_id,f"💥 {p['name']} перебор! Очки: {score}")
        p["stand"]=True
    game["current"]+=1
    start_turn(chat_id)

def handle_stand(message):
    chat_id = message.chat.id
    game = games.get(chat_id)
    if not game: return
    p = game["players"][game["current"]]
    if message.from_user.id != p["id"]: return
    p["stand"]=True
    bot.send_message(chat_id,f"✋ {p['name']} остановился.")
    game["current"]+=1
    start_turn(chat_id)

def handle_cash(message):
    chat_id = message.chat.id
    game = games.get(chat_id)
    if not game: return
    p = game["players"][game["current"]]
    if message.from_user.id != p["id"]: return
    payout = int(p["bet"]*0.6)
    balances[p["id"]]["balance"]+=payout
    p["cashout"]=True
    p["stand"]=True
    bot.send_message(chat_id,f"💸 {p['name']} забрал {payout} монет (60% ставки).")
    game["current"]+=1
    start_turn(chat_id)

@bot.message_handler(func=lambda m: m.text.lower()=="доб")
def m_hit(m): handle_hit(m)
@bot.message_handler(func=lambda m: m.text.lower()=="стоп")
def m_stand(m): handle_stand(m)
@bot.message_handler(func=lambda m: m.text.lower()=="кэш")
def m_cash(m): handle_cash(m)

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
        result=""
        if p["cashout"]:
            result="💸 Забрал 60% ставки"
        elif score>21:
            result="❌ Перебор"
        elif dealer_total>21:
            result="🏆 Победа"
            balances[p["id"]]["balance"]+=p["bet"]*2
        elif score==dealer_total:
            result="🤝 Ничья"
            balances[p["id"]]["balance"]+=p["bet"]
        elif score>dealer_total:
            result="🏆 Победа"
            balances[p["id"]]["balance"]+=p["bet"]*2
        else:
            result="❌ Проигрыш"
        text+=f"{p['name']}: {format_hand(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]['balance']} | {result}\n"
    for p in game["players"]:
        cooldowns[p["id"]]=time.time()+COOLDOWN_TIME
    bot.send_message(chat_id,text,reply_markup=types.ReplyKeyboardRemove())
    del games[chat_id]

bot.infinity_polling()