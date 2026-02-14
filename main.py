import telebot
from telebot import types
import random
import threading
import time
from functools import partial

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

# ================== Настройки ==================
START_BALANCE = 500
MAX_PLAYERS = 9
WAIT_TIME = 120  # 2 минуты ожидания
games = {}       # Данные по играм
balances = {}    # Баланс пользователей
cooldowns = {}   # КД на команды

# ================== Вспомогательные функции ==================
def create_deck():
    deck = [2,3,4,5,6,7,8,9,10,10,10,10,11]*4
    random.shuffle(deck)
    return deck

def calculate_score(hand):
    score = sum(hand)
    while score>21 and 11 in hand:
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
def cmd_help(message):
    user_id = message.from_user.id
    now = time.time()
    if user_id in cooldowns and now < cooldowns[user_id]:
        bot.send_message(message.chat.id,f"⏳ Подождите {int(cooldowns[user_id]-now)} секунд перед повтором команды.")
        return
    cooldowns[user_id] = now + 20
    help_text = (
        "🎲 Команды бота:\n"
        "б - приветствие и баланс по умолчанию\n"
        "бал - проверить баланс\n"
        "блек - начать набор за стол\n"
        "доб - взять карту\n"
        "стоп - остановиться\n"
        "кэш - забрать 70% ставки\n"
        "п - передача монет (использовать через reply на сообщение игрока)\n"
        "выйти - выйти со стола и вернуть ставку"
    )
    bot.send_message(message.chat.id,help_text)

# ================== Набор игроков ==================
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def cmd_blackjack(message):
    chat_id = message.chat.id
    if chat_id not in games:
        games[chat_id] = {"players": [], "deck": create_deck(), "started": False, "wait_timer": False}
    bot.send_message(chat_id,"🎲 Набор игроков. Если хочешь сесть за стол, напиши 'да'.")

@bot.message_handler(func=lambda m: m.text.lower() == "да")
def join_request(message):
    chat_id = message.chat.id
    game = games.get(chat_id)
    if not game or game["started"]:
        return
    user_id = message.from_user.id
    if any(p['id']==user_id for p in game["players"]):
        bot.send_message(chat_id,"🚫 Вы уже за столом.")
        return
    if balances.get(user_id, START_BALANCE)<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Присоединиться к столу")
    bot.send_message(chat_id,f"{message.from_user.first_name}, нажмите кнопку чтобы присоединиться к столу", reply_markup=markup)

# ================== Присоединение к столу ==================
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
    if balances.get(user_id, START_BALANCE)<=0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств, чтобы присоединиться.")
        return
    # убираем кнопку только у этого игрока
    bot.send_message(chat_id,"", reply_markup=types.ReplyKeyboardRemove())
    # Добавляем игрока с пустой ставкой
    game["players"].append({
        "id": user_id,
        "name": user_name,
        "hand": [],
        "bet": None,
        "stand": False,
        "cashout": False
    })
    # Запрос ставки
    msg = bot.send_message(chat_id,f"🪙 {user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, partial(set_bet, game=game, user_index=len(game["players"])-1))

# ================== Установка ставки ==================
def set_bet(message, game, user_index):
    player = game["players"][user_index]
    user_id = player["id"]
    user_name = player["name"]
    try:
        bet = int(message.text)
        if bet<=0 or bet>balances.get(user_id, START_BALANCE):
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id,f"❌ Ставка должна быть числом и не больше вашего баланса, {user_name}")
        bot.register_next_step_handler(msg, partial(set_bet, game=game, user_index=user_index))
        return
    balances[user_id] -= bet
    player["bet"] = bet
    bot.send_message(message.chat.id,f"💰 {user_name}, ваша ставка принята: {bet} монет.\nОжидание других участников…")
    # Запуск таймера ожидания
    if not game.get("wait_timer"):
        game["wait_timer"]=True
        threading.Thread(target=wait_and_start, args=[message.chat.id]).start()

# ================== Таймер ожидания ==================
def wait_and_start(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]:
        return
    start = time.time()
    while time.time()-start < WAIT_TIME:
        if len(game["players"])>=MAX_PLAYERS:
            break
        time.sleep(1)
    if not game["started"]:
        bot.send_message(chat_id,"🕒 Время ожидания истекло. Игра начинается с текущими игроками!")
        start_game(chat_id)

# ================== Старт игры ==================
def start_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    game["started"]=True
    game["dealer_hand"]=[game["deck"].pop(),game["deck"].pop()]
    for p in game["players"]:
        p["hand"]=[game["deck"].pop(),game["deck"].pop()]
        bot.send_message(chat_id,f"{p['name']} карты: {p['hand']} (Очки: {calculate_score(p['hand'])})")
    bot.send_message(chat_id,"🃏 Игра началась! Используйте команды: доб / стоп / кэш")

# ================== Доб / Стоп / Кэш ==================
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def game_commands(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    cmd = message.text.lower()
    game = games.get(chat_id)
    if not game or not game["started"]:
        return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player:
        return
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
    if all(p["stand"] for p in game["players"]):
        end_game(chat_id)

# ================== Конец игры ==================
def end_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    dealer_score = calculate_score(game["dealer_hand"])
    text = f"🃏 Дилер карты: {game['dealer_hand']} (Очки: {dealer_score})\n"
    winners = []
    for p in game["players"]:
        score = calculate_score(p["hand"])
        text += f"{p['name']}: {score}\n"
        if score<=21:
            if dealer_score>21 or score>dealer_score:
                winners.append(p)
            elif score==dealer_score:
                bot.send_message(chat_id,f"{p['name']} ничья с дилером!")
    for w in winners:
        balances[w["id"]]+=w["bet"]*2
        text += f"🏆 Победил {w['name']} (+{w['bet']*2})\n"
    bot.send_message(chat_id,text)
    del games[chat_id]

# ================== Запуск ==================
bot.infinity_polling()