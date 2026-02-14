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
WAIT_TIME = 120  # 2 минуты
COOLDOWN_COMMANDS = {}  # cooldown для бкоманды

# ================== Данные игры ==================
games = {}
balances = {}

# ================== Дек и очки ==================
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

# ================== Блек: набор игроков ==================
@bot.message_handler(func=lambda m: m.text.lower() == "блек")
def start_blackjack(message):
    chat_id = message.chat.id
    if chat_id not in games:
        games[chat_id] = {"players": [], "deck": create_deck(), "started": False, "wait_timer": False, "votes": {}}

    bot.send_message(chat_id,"🎲 Набор игроков. Если хочешь сесть за стол, напиши 'да'.")

# ================== Да: показать кнопку присоединиться ==================
@bot.message_handler(func=lambda m: m.text.lower() == "да")
def show_join_button(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game:
        bot.send_message(chat_id,"🚫 Игра ещё не началась. Напишите 'блек'")
        return
    # проверка, чтобы игрок не был уже за столом
    if any(p['id']==user_id for p in game["players"]):
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("Присоединиться к столу"))
    bot.send_message(chat_id,"Нажмите кнопку, чтобы присоединиться к столу", reply_markup=markup)

# ================== Присоединение к столу ==================
@bot.message_handler(func=lambda m: m.text.lower() == "присоединиться к столу")
def join_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    game = games.get(chat_id)

    if not game:
        bot.send_message(chat_id,"🚫 Игра не началась.")
        return

    if any(p['id']==user_id for p in game.get("players", [])):
        bot.send_message(chat_id,"🚫 Вы уже за столом.")
        return

    if balances.get(user_id, START_BALANCE) <= 0:
        bot.send_message(chat_id,"❌ У вас недостаточно средств.")
        return

    # убираем кнопку только у игрока
    bot.send_message(chat_id,"", reply_markup=types.ReplyKeyboardRemove())

    # запрашиваем ставку
    msg = bot.send_message(chat_id,f"🪙 {user_name}, введите вашу ставку:")
    bot.register_next_step_handler(msg, partial(set_bet, game=game, user_id=user_id, user_name=user_name))

# ================== Ставка ==================
def set_bet(message, game, user_id, user_name):
    try:
        bet = int(message.text)
        if bet <=0 or bet>balances.get(user_id, START_BALANCE):
            raise ValueError
    except:
        msg = bot.send_message(message.chat.id,f"❌ Введите корректную ставку {user_name}:")
        bot.register_next_step_handler(msg, partial(set_bet, game=game, user_id=user_id, user_name=user_name))
        return

    # добавляем игрока
    game["players"].append({"id":user_id,"name":user_name,"hand":[],"bet":bet,"stand":False,"cashout":False})
    balances[user_id] = balances.get(user_id, START_BALANCE) - bet
    bot.send_message(message.chat.id,f"🪑 {user_name} присоединился за стол со ставкой {bet} монет.")

    # показываем кнопки голосования только игроку
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("Да"), types.KeyboardButton("Нет, ждать других участников"))
    bot.send_message(message.chat.id,"Хотите начать игру сразу?", reply_markup=markup)

    # запуск таймера или старта
    if len(game["players"]) >= MAX_PLAYERS:
        bot.send_message(message.chat.id,"Игра скоро начнется, дилер раздает карты…")
        threading.Timer(10, start_game, args=[message.chat.id]).start()
    else:
        if not game.get("wait_timer"):
            game["wait_timer"] = True
            threading.Thread(target=wait_and_start,args=[message.chat.id]).start()

# ================== Таймер ожидания старта ==================
def wait_and_start(chat_id):
    time.sleep(WAIT_TIME)
    game = games.get(chat_id)
    if game and not game["started"]:
        bot.send_message(chat_id,"🕒 Время ожидания завершено, игра начинается с текущими игроками.")
        start_game(chat_id)

# ================== Старт игры ==================
def start_game(chat_id):
    game = games.get(chat_id)
    if not game or game["started"]:
        return
    game["started"] = True
    game["deck"] = create_deck()

    for player in game["players"]:
        player["hand"].append(game["deck"].pop())
        player["hand"].append(game["deck"].pop())

    msg = "🃏 Игра началась!\n\n"
    for player in game["players"]:
        msg += f"{player['name']}: {player['hand']} (Очки: {calculate_score(player['hand'])})\n"

    msg += "\nПишите 'доб', 'стоп' или 'кэш'."
    bot.send_message(chat_id,msg)

# ================== Команды игры ==================
@bot.message_handler(func=lambda m: m.text.lower() in ["доб","стоп","кэш"])
def game_commands(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game or not game["started"]:
        return

    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player:
        return

    if message.text.lower() == "доб":
        player["hand"].append(game["deck"].pop())
        score = calculate_score(player["hand"])
        bot.send_message(chat_id,f"{player['name']} добрал карту: {player['hand']} (Очки: {score})")
        if score>21:
            player["stand"]=True
            bot.send_message(chat_id,f"💥 {player['name']} перебор! Карты сброшены.")
    elif message.text.lower() == "стоп":
        player["stand"]=True
        bot.send_message(chat_id,f"{player['name']} остановился.")
    elif message.text.lower() == "кэш":
        player["cashout"]=True
        return_amount = int(player["bet"]*0.7)
        balances[user_id]+=return_amount
        bot.send_message(chat_id,f"{player['name']} забрал 70% ставки: {return_amount}.")
        player["stand"]=True

    # Проверяем конец игры
    if all(p["stand"] or p.get("cashout",False) for p in game["players"]):
        end_game(chat_id)

# ================== Конец игры ==================
def end_game(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    best_score = 0
    winners=[]
    dealer_score = random.randint(17,23)  # дилер случайно
    msg = f"🏁 Игра окончена! (Дилер: {dealer_score})\n"
    for player in game["players"]:
        score = calculate_score(player["hand"])
        msg+=f"{player['name']}: {score}\n"
        if score<=21 and dealer_score>21:
            winners.append(player)
        elif score<=21 and score>best_score and dealer_score<=21:
            best_score = score
            winners=[player]
        elif score==dealer_score:
            winners.append(player)
    for w in winners:
        balances[w["id"]]+=w["bet"]*2
        msg+=f"🏆 {w['name']} выиграл {w['bet']*2}!\n"
    bot.send_message(chat_id,msg)
    del games[chat_id]

# ================== Передача монет через reply ==================
@bot.message_handler(func=lambda m: m.text.lower().startswith("п "))
def transfer_coins(message):
    sender_id = message.from_user.id
    # проверяем, что не за столом
    for game in games.values():
        if any(p['id']==sender_id for p in game.get("players", [])):
            bot.send_message(message.chat.id,"❌ Нельзя передавать монеты во время игры.")
            return
    if not message.reply_to_message:
        bot.send_message(message.chat.id,"❌ Ответьте на сообщение получателя, чтобы передать монеты.")
        return

    receiver = message.reply_to_message.from_user
    receiver_id = receiver.id
    receiver_name = receiver.first_name

    try:
        amount = int(message.text.split()[1])
    except:
        bot.send_message(message.chat.id,"❌ Укажите корректную сумму: п 50")
        return

    if balances.get(sender_id,START_BALANCE)<amount:
        bot.send_message(message.chat.id,f"❌ У вас нет {amount} монет для передачи.")
        return

    balances[sender_id]-=amount
    balances[receiver_id]=balances.get(receiver_id,START_BALANCE)+amount
    bot.send_message(message.chat.id,f"💸 {message.from_user.first_name} передал {amount} монет {receiver_name}.")

# ================== Баланс ==================
@bot.message_handler(func=lambda m: m.text.lower() == "бал")
def show_balance(message):
    user_id = message.from_user.id
    balances[user_id]=balances.get(user_id,START_BALANCE)
    bot.send_message(message.chat.id,f"💰 {message.from_user.first_name}, ваш баланс: {balances[user_id]}")

# ================== Бкоманды ==================
@bot.message_handler(func=lambda m: m.text.lower()=="бкоманды")
def show_commands(message):
    user_id = message.from_user.id
    now = time.time()
    if COOLDOWN_COMMANDS.get(user_id,0)>now:
        bot.send_message(message.chat.id,"⏳ Подождите перед повторным вызовом команды.")
        return
    COOLDOWN_COMMANDS[user_id]=now+20

    text = ("📜 Доступные команды:\n"
            "блек — начать набор игроков\n"
            "да — показать кнопку присоединиться к столу\n"
            "Присоединиться к столу — присоединиться к столу\n"
            "доб — добрать карту\n"
            "стоп — остановиться\n"
            "кэш — забрать 70% ставки\n"
            "бал — проверить баланс\n"
            "п <сумма> (reply на сообщение) — передать монеты\n"
            "выйти — выйти со стола и вернуть ставку")
    bot.send_message(message.chat.id,text)

# ================== Выйти со стола ==================
@bot.message_handler(func=lambda m: m.text.lower()=="выйти")
def leave_table(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = games.get(chat_id)
    if not game:
        bot.send_message(chat_id,"🚫 Вы не за столом.")
        return
    player = next((p for p in game["players"] if p["id"]==user_id), None)
    if not player:
        bot.send_message(chat_id,"🚫 Вы не за столом.")
        return
    # возвращаем ставку
    balances[user_id]+=player["bet"]
    bot.send_message(chat_id,f"{player['name']} вышел со стола, ставка возвращена ({player['bet']}).")
    game["players"].remove(player)

bot.infinity_polling()