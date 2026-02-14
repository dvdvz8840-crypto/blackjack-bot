import telebot
from telebot import types
import random
import threading
import time

TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"
bot = telebot.TeleBot(TOKEN)

# ================== Глобальные данные ==================
games = {}
balances = {}
START_BALANCE = 500
MAX_PLAYERS = 9
WAIT_TIME = 120  # 2 минуты ожидания набора игроков
SUITS = ['♠️','♥️','♦️','♣️']
cooldowns_commands = {}

# ================== Карты ==================
def create_deck():
    deck = []
    for suit in SUITS:
        for card in [2,3,4,5,6,7,8,9,10,'J','Q','K','A']:
            deck.append((str(card), suit))
    random.shuffle(deck)
    return deck

def card_value(card):
    if card[0] in ['J','Q','K']: return 10
    if card[0] in ['A']: return 11
    if card[0] == 'A1': return 1
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
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {balances.get(user_id, START_BALANCE)} монет.")

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
    user_name = message.from_user.first_name
    game = games.get(chat_id)
    if not game:
        return
    if any(p['id']==user_id for p in game["players"]):
        bot.send_message(chat_id, "🚫 Вы уже за столом.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("Присоединиться к столу"))
    bot.send_message(chat_id, f"{user_name}, нажмите кнопку чтобы присоединиться за стол", reply_markup=markup)

# ================== Присоединение к столу ==================
@bot.message_handler(func=lambda m: m.text.lower() == "присоединиться к столу")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    game = games.get(chat_id)
    if not game:
        bot.send_message(chat_id, "🚫 Игра еще не началась. Напишите 'блек', чтобы начать набор игроков.")
        return
    if any(p['id']==user_id for p in game["players"]):
        bot.send_message(chat_id, "🚫 Вы уже присоединились к столу или игра уже идет.")
        return
    bot.send_message(chat_id, "", reply_markup=types.ReplyKeyboardRemove())
    if balances.get(user_id,0)<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return
    msg = bot.send_message(chat_id, f"{user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, set_bet, game, user_id, user_name)

# ================== Установка ставки ==================
def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet <= 0 or bet > balances[user_id]:
            bot.send_message(message.chat.id, "❌ Ставка должна быть числом и не превышать баланс.")
            return
    except:
        bot.send_message(message.chat.id, "❌ Ставка должна быть числом.")
        return
    game["players"].append({
        "id": user_id,
        "name": user_name,
        "hand": [],
        "bet": bet,
        "stand": False,
        "cashout": False
    })
    balances[user_id] -= bet
    bot.send_message(message.chat.id, f"🪑 {user_name} присоединился за стол со ставкой {bet}.")
    send_vote_buttons(message.chat.id, user_id)
    if len(game["players"]) == MAX_PLAYERS:
        bot.send_message(message.chat.id, "Игра скоро начнется, дилер раздает карты…")
        threading.Timer(10, start_game, args=[message.chat.id]).start()
    else:
        threading.Thread(target=wait_and_start, args=[message.chat.id]).start()

# ================== Таймер ожидания ==================
def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    start_time = time.time()
    while time.time() - start_time < WAIT_TIME:
        votes = list(game["votes"].values())
        if len(votes) == len(game["players"]) and votes.count("да") > votes.count("нет, ждать других участников"):
            bot.send_message(chat_id, "Игра скоро начнется, дилер раздает карты…")
            threading.Timer(10, start_game, args=[chat_id]).start()
            return
        time.sleep(1)
    if not game["started"] and len(game["players"])>0:
        bot.send_message(chat_id, "Время ожидания истекло. Игра начинается с текущими игроками…")
        threading.Timer(1, start_game, args=[chat_id]).start()

# ================== Голосование ==================
def send_vote_buttons(chat_id, user_id):
    game = games.get(chat_id)
    if not game: return
    if user_id not in [p['id'] for p in game['players']]:
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
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
    bot.send_message(chat_id, "✅ Ваш голос учтён.", reply_markup=types.ReplyKeyboardRemove())

# ================== Доб/Стоп/Кэш ==================
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def game_commands(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game or game.get("ended",True):
        return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player:
        return
    cmd = message.text.lower()
    if cmd=="доб":
        player["hand"].append(game["deck"].pop())
        score = calculate_score(player["hand"])
        bot.send_message(chat_id,f"{player['name']} добрал карту. Рука: {format_hand(player['hand'])} (Очки: {score})")
        if score>21:
            player["stand"]=True
            bot.send_message(chat_id,f"💥 {player['name']} перебор! Кнопки убраны.")
    elif cmd=="стоп":
        player["stand"]=True
        bot.send_message(chat_id,f"✋ {player['name']} остановился. Кнопки убраны.")
    elif cmd=="кэш":
        player["cashout"]=True
        refund = int(player["bet"]*0.7)
        balances[user_id]+=refund
        player["stand"]=True
        bot.send_message(chat_id,f"💰 {player['name']} забрал 70% ставки ({refund} монет). Кнопки убраны.")
    check_end(chat_id)

# ================== Выйти ==================
@bot.message_handler(func=lambda m: m.text.lower()=="выйти")
def leave_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game:
        bot.send_message(chat_id,"🚫 Игры нет.")
        return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player:
        bot.send_message(chat_id,"🚫 Вы не за столом.")
        return
    balances[user_id]+=player["bet"]
    game["players"].remove(player)
    bot.send_message(chat_id,f"❌ {player['name']} вышел со стола. Ставка возвращена ({player['bet']} монет).")

# ================== Передача монет ==================
@bot.message_handler(func=lambda m: m.text.lower().startswith("п "))
def transfer_coins(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    game = games.get(chat_id)
    
    # Проверяем, что игрок не за столом
    if game and any(p['id']==user_id for p in game.get("players",[])):
        bot.send_message(chat_id, "❌ Вы не можете передавать монеты во время игры!")
        return

    try:
        parts = message.text.split()
        if len(parts) != 3:
            raise ValueError
        amount = int(parts[1])
        target_id = int(parts[2])
        
        # Проверка баланса
        if balances.get(user_id,0) < amount:
            bot.send_message(chat_id, f"❌ У вас нет {amount} монет для передачи.")
            return

        # Перевод монет
        balances[user_id] -= amount
        balances[target_id] = balances.get(target_id, START_BALANCE) + amount
        bot.send_message(chat_id, f"✅ {amount} монет передано пользователю {target_id}.")
    except:
        bot.send_message(chat_id, "❌ Неправильный формат команды. Пример: п 300 123456789")

# ================== Бкоманды с кд ==================
@bot.message_handler(func=lambda m: m.text.lower()=="бкоманды")
def commands_list(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    now = time.time()
    if cooldowns_commands.get(user_id,0)>now:
        bot.send_message(chat_id,"⏳ Подождите 20 секунд перед повторным вызовом команд.")
        return
    cooldowns_commands[user_id]=now+20
    commands_text = """
🎮 **Команды Blackjack:**

🔹 б — регистрация и получение стартового баланса  
🔹 бал — проверка баланса  
🔹 блек — начать набор игроков за стол  
🔹 да — показать кнопку «Присоединиться к столу» (только после блек)  
🔹 присоединиться к столу — присоединиться к игре (после «да»)  
🔹 доб — добрать карту (только за столом)  
🔹 стоп — остановиться (только за столом)  
🔹 кэш — забрать 70% ставки и выйти из игры (только за столом)  
🔹 выйти — выйти со стола и вернуть ставку (только за столом)  
🔹 п СУММА @айди_пользователя — передать монеты (только вне игры)  
🔹 бкоманды — список команд (кулдаун 20 сек)
"""
    bot.send_message(chat_id, commands_text, parse_mode="Markdown")

bot.infinity_polling()