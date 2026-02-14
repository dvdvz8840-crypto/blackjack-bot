import telebot
from telebot import types
import random
import threading
import time
from functools import partial

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

# Игровые данные
games = {}
balances = {}
cooldowns = {}
commands_cd = {}

START_BALANCE = 500
MAX_PLAYERS = 9
WAIT_TIME = 120  # 2 минуты
COOLDOWN_TIME = 20  # КД для бкоманды

# ================== Базовые функции ==================
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

# ================== Команды ==================
@bot.message_handler(func=lambda m: m.text.lower() == "б")
def cmd_start(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id,f"🎮 Добро пожаловать в Blackjack!\n💰 Твой баланс: {balances[user_id]}")

@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def cmd_balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.send_message(message.chat.id,f"💰 Твой баланс: {balances[user_id]}")

@bot.message_handler(func=lambda m: m.text.lower() == "бкоманды")
def cmd_commands(message):
    user_id = message.from_user.id
    now = time.time()
    if commands_cd.get(user_id,0) > now:
        bot.send_message(message.chat.id,f"⏳ Подождите {int(commands_cd[user_id]-now)} секунд перед повтором.")
        return
    commands_cd[user_id] = now + COOLDOWN_TIME
    text = """
🎮 Доступные команды:

б — старт/получить баланс
бал — проверить баланс
блек — начать набор игроков
доб — добрать карту (во время игры)
стоп — остановиться (во время игры)
кэш — забрать 70% ставки (во время игры)
выйти — выйти со стола (возвращает ставку)
п (reply) — передать монеты другому игроку
"""
    bot.send_message(message.chat.id,text)

# ================== Блек ==================
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def cmd_blackjack(message):
    chat_id = message.chat.id
    if chat_id not in games:
        games[chat_id] = {"players": [], "deck": create_deck(), "started": False, "wait_timer": False}
    bot.send_message(chat_id,"🎲 Набор игроков. Если хочешь сесть за стол, напиши 'да'.")

# ================== Присоединение ==================
@bot.message_handler(func=lambda m: m.text.lower() == "да")
def join_request(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game or game["started"]:
        return
    # Показываем кнопку только для этого игрока
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Присоединиться к столу")
    bot.send_message(chat_id,f"{message.from_user.first_name}, нажмите кнопку чтобы присоединиться к столу", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text.lower() == "присоединиться к столу")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    game = games.get(chat_id)
    if not game or game["started"]:
        bot.send_message(chat_id,"🚫 Игра не началась или уже идет.")
        return
    if any(p['id']==user_id for p in game["players"]):
        bot.send_message(chat_id,"🚫 Вы уже за столом.")
        return
    if balances.get(user_id,START_BALANCE)<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return
    # убираем кнопку
    bot.send_message(chat_id,"", reply_markup=types.ReplyKeyboardRemove())
    # добавляем игрока с пустой ставкой
    game["players"].append({"id":user_id,"name":user_name,"hand":[],"bet":None,"stand":False,"cashout":False})
    msg = bot.send_message(chat_id,f"🪙 {user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, partial(set_bet, game=game, user_id=user_id))

# ================== Ставка ==================
def set_bet(message, game, user_id):
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player: return
    user_name = message.from_user.first_name
    try:
        bet = int(message.text)
        if bet<=0 or bet>balances.get(user_id,START_BALANCE):
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id,f"❌ Ставка должна быть числом и не больше баланса, {user_name}")
        bot.register_next_step_handler(msg, partial(set_bet, game=game, user_id=user_id))
        return
    balances[user_id]-=bet
    player["bet"]=bet
    bot.send_message(message.chat.id,f"💰 {user_name}, ваша ставка принята: {bet} монет.")

    # Показываем кнопки голосования
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Да","Нет, ждать других участников")
    bot.send_message(message.chat.id,"Хотите начать игру сразу?", reply_markup=markup)

# ================== Таймер ожидания ==================
def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]: return
    start = time.time()
    while time.time()-start<WAIT_TIME:
        if len(game["players"])>=MAX_PLAYERS:
            break
        time.sleep(1)
    if not game["started"]:
        bot.send_message(chat_id,"🕒 Время ожидания истекло. Игра начинается с текущими игроками!")
        start_game(chat_id)

# ================== Старт игры ==================
def start_game(chat_id):
    game = games.get(chat_id)
    if not game: return
    game["started"]=True
    # раздаем карты дилеру
    game["dealer_hand"]=[game["deck"].pop(),game["deck"].pop()]
    # раздаем карты игрокам
    for p in game["players"]:
        p["hand"]=[game["deck"].pop(),game["deck"].pop()]
        # показываем их карты
        bot.send_message(chat_id,f"{p['name']} карты: {p['hand']} (Очки: {calculate_score(p['hand'])})")
    bot.send_message(chat_id,"🃏 Игра началась! Используйте команды: доб / стоп / кэш")

# ================== Доб / Стоп / Кэш ==================
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def game_commands(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    cmd = message.text.lower()
    game = games.get(chat_id)
    if not game or not game["started"]: return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player: return
    if cmd=="доб":
        player["hand"].append(game["deck"].pop())
        score = calculate_score(player["hand"])
        if score>21:
            bot.send_message(chat_id,f"{player['name']} перебор! {score}. Вы проиграли.")
            player["stand"]=True
        else:
            bot.send_message(chat_id,f"{player['name']} карты: {player['hand']} (Очки: {score})")
    elif cmd=="стоп":
        player["stand"]=True
        bot.send_message(chat_id,f"{player['name']} остановился.")
    elif cmd=="кэш":
        player["stand"]=True
        cash = int(player["bet"]*0.7)
        balances[user_id]+=cash
        bot.send_message(chat_id,f"{player['name']} забрал 70% ставки: {cash}")
    # проверяем конец игры
    if all(p["stand"] for p in game["players"]):
        end_game(chat_id)

# ================== Конец игры ==================
def end_game(chat_id):
    game = games.get(chat_id)
    if not game: return
    dealer_score = calculate_score(game["dealer_hand"])
    text = f"🃏 Дилер карты: {game['dealer_hand']} (Очки: {dealer_score})\n"
    winners = []
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text+=f"{p['name']}: {score}\n"
        if score<=21:
            if dealer_score>21 or score>dealer_score:
                winners.append(p)
            elif score==dealer_score:
                bot.send_message(chat_id,f"{p['name']} ничья с дилером!")
    for w in winners:
        balances[w["id"]]+=w["bet"]*2
        text+=f"🏆 Победил {w['name']} (+{w['bet']*2})\n"
    bot.send_message(chat_id,text)
    del games[chat_id]

# ================== Передача монет ==================
@bot.message_handler(func=lambda m: m.text.lower().startswith("п"))
def transfer_coins(message):
    user_id = message.from_user.id
    if any(user_id==p["id"] for g in games.values() for p in g["players"]):
        bot.send_message(message.chat.id,"🚫 Нельзя передавать монеты во время игры!")
        return
    if not message.reply_to_message:
        bot.send_message(message.chat.id,"❌ Ответьте на сообщение игрока, которому хотите передать.")
        return
    try:
        amount = int(message.text.split()[1])
        if amount<=0 or amount>balances.get(user_id,0):
            bot.send_message(message.chat.id,f"❌ У вас нет {amount} монет для передачи.")
            return
    except:
        bot.send_message(message.chat.id,"❌ Укажите корректную сумму. Пример: п 50")
        return
    target_id = message.reply_to_message.from_user.id
    balances[user_id]-=amount
    balances[target_id]=balances.get(target_id,START_BALANCE)+amount
    bot.send_message(message.chat.id,f"✅ {amount} монет переданы {message.reply_to_message.from_user.first_name}")

bot.infinity_polling()