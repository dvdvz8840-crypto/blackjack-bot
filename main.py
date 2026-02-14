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
COOLDOWN_TIME = 120  # 2 минуты
MAX_PLAYERS = 9

SUITS = ['♦️', '♣️', '♥️', '♠️']

# ------------------------ КОЛОДА ------------------------
def create_deck():
    deck = []
    for suit in SUITS:
        for card in range(2,12):  # 2-11
            deck.append(f"{card}{suit}")
    random.shuffle(deck)
    return deck

def card_value(card):
    value = int(card[:-2])  # удаляем символ масти
    return value

def calculate_score(hand):
    score = sum(card_value(c) for c in hand)
    while score > 21 and any(c.startswith('11') for c in hand):
        for i,c in enumerate(hand):
            if c.startswith('11'):
                hand[i] = '1'+c[2:]
                break
        score = sum(card_value(c) for c in hand)
    return score

# ------------------------ СТИЛЬ ------------------------
def format_game_state(game, hide_dealer=True):
    text = ""
    # дилер
    if hide_dealer:
        text += f"Дилер: [{game['dealer']['hand'][0]}, ❓]\n"
    else:
        text += f"Дилер: {', '.join(game['dealer']['hand'])} (Очки: {calculate_score(game['dealer']['hand'])})\n"
    # игроки
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {' '.join(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]}\n"
    return text

# ------------------------ КНОПКИ ------------------------
def player_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("доб"), types.KeyboardButton("стоп"), types.KeyboardButton("кэш"))
    return markup

# ------------------------ КОМАНДЫ ------------------------
@bot.message_handler(func=lambda m: m.text.lower() == "б")
def cmd_register(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"🎮 Привет, {message.from_user.first_name}!\n💰 Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def cmd_balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances[user_id]} монет.")

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def cmd_commands(message):
    text = (
        "📋 Список команд:\n\n"
        "б - Регистрация и приветствие\n"
        "бал - Показать ваш баланс\n"
        "блек - Начать набор игроков для игры Blackjack\n"
        "п (сумма) + reply to игрока - Передача монет через ответ на сообщение\n"
        "доб - Добрать карту во время игры\n"
        "стоп - Остановить ход\n"
        "кэш - Кэш-аут (60% от ставки) во время игры\n"
    )
    bot.send_message(message.chat.id,text)

# ------------------------ НАБОР ИГРОКОВ ------------------------
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def cmd_black(message):
    chat_id = message.chat.id
    if chat_id in games:
        bot.send_message(chat_id, "🚫 Игра уже идет!")
        return

    games[chat_id] = {
        "players": [],
        "deck": create_deck(),
        "started": False,
        "turn": 0
    }

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("Сесть за стол")
    markup.add(btn)
    bot.send_message(chat_id, "🎲 Набор игроков начат! Нажмите кнопку чтобы присоединиться за стол.", reply_markup=markup)
    # автостарт через 2 минуты
    threading.Thread(target=wait_and_start, args=(chat_id,)).start()

@bot.message_handler(func=lambda m: m.text.lower() == "сесть за стол")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    game = games.get(chat_id)
    if not game:
        bot.send_message(chat_id,"Сначала начните игру командой 'блек'.")
        return

    for p in game["players"]:
        if p["id"] == user_id:
            bot.send_message(chat_id,"❌ Вы уже за столом.")
            return

    if len(game["players"]) >= MAX_PLAYERS:
        bot.send_message(chat_id,"🚫 Стол уже заполнен!")
        return

    if user_id not in balances or balances[user_id]<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return

    bot.send_message(chat_id,f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(message,set_bet,user_id,user_name,chat_id)

def set_bet(message,user_id,user_name,chat_id):
    game = games.get(chat_id)
    if not game:
        return
    try:
        bet = int(message.text)
        if bet<=0 or bet>balances[user_id]:
            bot.send_message(chat_id,f"🛑 Недостаточно средств, чтобы поставить такую ставку")
            return
    except:
        bot.send_message(chat_id,"❌ Ставка должна быть числом.")
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

    bot.send_message(chat_id,f"🪑 {user_name} присоединился за стол со ставкой 🪙 {bet} монет.\n💰 Ваш баланс: {balances[user_id]} монет.\nОжидание ставок других участников... Если никто не присоединится, игра начнется через 2 минуты.")

# ------------------------ ТАЙМЕР НАБОР ------------------------
def wait_and_start(chat_id):
    time.sleep(120)
    game = games.get(chat_id)
    if game and not game["started"] and len(game["players"])>0:
        start_game(chat_id)

# ------------------------ СТАРТ ИГРЫ ------------------------
def start_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    game["started"] = True
    deck = game["deck"]

    # Раздача карт с анимацией
    for p in game["players"]:
        p["hand"] = [deck.pop()]
        time.sleep(0.5)
        p["hand"].append(deck.pop())
        time.sleep(0.5)

    game["dealer"] = {"hand":[deck.pop(),deck.pop()]}

    # Отправка текущего состояния
    show_game_state(chat_id)
    next_turn(chat_id)

def show_game_state(chat_id,hide_dealer=True):
    game = games.get(chat_id)
    if not game: return
    text = "📊 Текущее состояние игры:\n━━━━━━━━━━━━━━\n"
    # дилер
    if hide_dealer:
        text += f"Дилер: [{game['dealer']['hand'][0]}, ❓]\n"
    else:
        text += f"Дилер: {', '.join(game['dealer']['hand'])} (Очки: {calculate_score(game['dealer']['hand'])})\n"
    # игроки
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {' '.join(p['hand'])} (Очки: {score}) | Баланс: {balances[p['id']]}\n"
    bot.send_message(chat_id,text)

# ------------------------ ХОД ------------------------
def next_turn(chat_id):
    game = games.get(chat_id)
    if not game: return
    while game["turn"] < len(game["players"]):
        player = game["players"][game["turn"]]
        if not player["stand"] and not player["cashout"]:
            bot.send_message(chat_id,f"✋ Сейчас ход: {player['name']}")
            try:
                bot.send_message(player["id"],"Ваш ход. Выберите действие:",reply_markup=player_keyboard())
            except:
                bot.send_message(chat_id,f"{player['name']} напишите боту в личку для продолжения игры.")
            return
        else:
            game["turn"] += 1
    finish_game(chat_id)

# ------------------------ ДЕЙСТВИЯ ------------------------
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def player_action(m):
    uid = m.from_user.id
    # ищем игру и игрока
    for chat_id,game in games.items():
        if game["started"] and game["turn"] < len(game["players"]):
            player = game["players"][game["turn"]]
            if player["id"]==uid:
                break
    else:
        return

    if m.text.lower()=="доб":
        player["hand"].append(game["deck"].pop())
        score = calculate_score(player["hand"])
        if score>21:
            player["stand"]=True
            bot.send_message(chat_id,f"💥 {player['name']} перебор! Очки: {score}")
        else:
            bot.send_message(chat_id,f"🃏 {player['name']} взял карту. Очки: {score}")

    elif m.text.lower()=="стоп":
        player["stand"]=True
        bot.send_message(chat_id,f"✋ {player['name']} остановился.")

    elif m.text.lower()=="кэш":
        player["cashout"]=True
        player["stand"]=True
        payout = int(player["bet"]*0.6)
        balances[uid]+=payout
        bot.send_message(chat_id,f"💸 {player['name']} забрал {payout} монет (60% ставки)")

    game["turn"]+=1
    show_game_state(chat_id)
    next_turn(chat_id)

# ------------------------ ОКОНЧАНИЕ ------------------------
def finish_game(chat_id):
    game = games.get(chat_id)
    if not game: return
    deck = game["deck"]
    dealer = game["dealer"]
    dealer_total = calculate_score(dealer["hand"])
    while dealer_total<17:
        dealer["hand"].append(deck.pop())
        dealer_total = calculate_score(dealer["hand"])

    text = f"🏁 Игра окончена!\nДилер: {', '.join(dealer['hand'])} (Очки: {dealer_total})\n\n"
    winners = []
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {' '.join(p['hand'])} (Очки: {score})\n"
        if not p["cashout"]:
            if dealer_total>21 and score<=21:
                winners.append(p)
            elif score==21 and dealer_total==21:
                text += "(Ничья)\n"
            elif score>dealer_total and score<=21:
                winners.append(p)

    for w in winners:
        balances[w["id"]] += w["bet"]*2
        text += f"🏆 Победил {w['name']}! Выигрыш: {w['bet']*2}\n"

    # кулдаун
    for p in game["players"]:
        cooldowns[p["id"]] = time.time()+COOLDOWN_TIME

    bot.send_message(chat_id,text,reply_markup=types.ReplyKeyboardRemove())
    del games[chat_id]

bot.infinity_polling()