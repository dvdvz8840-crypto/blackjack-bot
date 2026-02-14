import telebot
from telebot import types
import random
import time
import threading

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"
bot = telebot.TeleBot(TOKEN)

START_BALANCE = 1000
WAIT_TIME = 120
MAX_PLAYERS = 9

games = {}
balances = {}
cooldowns = {}


# ================= ВСПОМОГАТЕЛЬНЫЕ =================

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


def player_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("доб", "стоп", "кэш")
    return markup


# ================= СТАРТ И БАЛАНС =================

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "б")
def start_cmd(message):
    uid = message.from_user.id
    if uid not in balances:
        balances[uid] = START_BALANCE
    bot.send_message(message.chat.id,
                     f"🎮 Добро пожаловать!\n💰 Баланс: {balances[uid]}")


@bot.message_handler(func=lambda m: m.text and m.text.lower() == "бал")
def balance_cmd(message):
    uid = message.from_user.id
    if uid not in balances:
        balances[uid] = START_BALANCE
    bot.send_message(message.chat.id, f"💰 Баланс: {balances[uid]}")


@bot.message_handler(func=lambda m: m.text and m.text.lower() == "бкоманды")
def help_cmd(message):
    bot.send_message(message.chat.id,
                     "🎲 Команды:\n"
                     "б - старт\n"
                     "бал - баланс\n"
                     "блек - начать игру\n"
                     "доб - взять карту\n"
                     "стоп - остановиться\n"
                     "кэш - кэшаут 60%\n"
                     "п (сумма) - перевод через reply")


# ================= НАЧАТЬ НАБОР =================

@bot.message_handler(func=lambda m: m.text and m.text.lower() == "блек")
def blackjack_cmd(message):
    chat_id = message.chat.id
    uid = message.from_user.id

    if chat_id not in games:
        games[chat_id] = {
            "players": [],
            "deck": create_deck(),
            "started": False
        }

    if games[chat_id]["started"]:
        bot.send_message(chat_id, "Игра уже идёт.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Сесть за стол")

    bot.send_message(chat_id,
                     "🪑 Нажмите кнопку, чтобы сесть за стол.",
                     reply_markup=markup)


# ================= СЕСТЬ ЗА СТОЛ =================

@bot.message_handler(func=lambda m: m.text == "Сесть за стол")
def sit_table(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    name = message.from_user.first_name

    game = games.get(chat_id)
    if not game or game["started"]:
        return

    if any(p["id"] == uid for p in game["players"]):
        bot.send_message(chat_id, "Вы уже за столом.")
        return

    if len(game["players"]) >= MAX_PLAYERS:
        bot.send_message(chat_id, "Стол заполнен.")
        return

    if balances.get(uid, START_BALANCE) <= 0:
        bot.send_message(chat_id, "Недостаточно средств.")
        return

    bot.send_message(chat_id, "Введите сумму ставки:",
                     reply_markup=types.ReplyKeyboardRemove())

    msg = bot.send_message(chat_id, "💰 Ваша ставка?")
    bot.register_next_step_handler(msg, set_bet)


def set_bet(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    name = message.from_user.first_name

    game = games.get(chat_id)
    if not game:
        return

    try:
        bet = int(message.text)
        if bet <= 0 or bet > balances.get(uid, START_BALANCE):
            raise ValueError
    except:
        msg = bot.send_message(chat_id, "Введите корректную сумму.")
        bot.register_next_step_handler(msg, set_bet)
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

    bot.send_message(chat_id, f"{name} сел за стол со ставкой {bet}")

    if len(game["players"]) == 1:
        threading.Thread(target=wait_start, args=(chat_id,)).start()


# ================= ТАЙМЕР ОЖИДАНИЯ =================

def wait_start(chat_id):
    time.sleep(WAIT_TIME)
    if chat_id in games and not games[chat_id]["started"]:
        start_game(chat_id)


# ================= СТАРТ ИГРЫ =================

def start_game(chat_id):
    game = games[chat_id]
    game["started"] = True

    game["dealer"] = [game["deck"].pop(), game["deck"].pop()]

    bot.send_message(chat_id,
                     f"🃏 Дилер: [{game['dealer'][0]}, ?]")

    for p in game["players"]:
        p["hand"] = [game["deck"].pop(), game["deck"].pop()]
        bot.send_message(chat_id,
                         f"{p['name']} карты: {p['hand']} "
                         f"({calculate_score(p['hand'])})",
                         reply_markup=player_keyboard())


# ================= ИГРОВЫЕ КОМАНДЫ =================

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["доб", "стоп", "кэш"])
def game_actions(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    cmd = message.text.lower()

    game = games.get(chat_id)
    if not game or not game["started"]:
        return

    player = next((p for p in game["players"] if p["id"] == uid), None)
    if not player or player["stand"]:
        return

    if cmd == "доб":
        player["hand"].append(game["deck"].pop())
        score = calculate_score(player["hand"])

        if score > 21:
            player["stand"] = True
            bot.send_message(chat_id, f"{player['name']} перебор ({score})",
                             reply_markup=types.ReplyKeyboardRemove())
        else:
            bot.send_message(chat_id,
                             f"{player['name']} карты: {player['hand']} ({score})")

    elif cmd == "стоп":
        player["stand"] = True
        bot.send_message(chat_id, f"{player['name']} остановился.",
                         reply_markup=types.ReplyKeyboardRemove())

    elif cmd == "кэш":
        player["stand"] = True
        player["cashout"] = True
        refund = int(player["bet"] * 0.6)
        balances[uid] += refund
        bot.send_message(chat_id,
                         f"{player['name']} сделал кэшаут и получил {refund}",
                         reply_markup=types.ReplyKeyboardRemove())

    if all(p["stand"] for p in game["players"]):
        end_game(chat_id)


# ================= КОНЕЦ ИГРЫ =================

def end_game(chat_id):
    game = games[chat_id]

    dealer = game["dealer"]
    dealer_score = calculate_score(dealer)

    while dealer_score < 17:
        dealer.append(game["deck"].pop())
        dealer_score = calculate_score(dealer)

    result = f"🃏 Дилер: {dealer} ({dealer_score})\n\n"

    for p in game["players"]:
        score = calculate_score(p["hand"])
        result += f"{p['name']}: {score}\n"

        if p["cashout"]:
            continue

        if score > 21:
            continue

        if dealer_score > 21:
            balances[p["id"]] += p["bet"] * 2

        elif dealer_score == 21:
            if score == 21:
                balances[p["id"]] += p["bet"]
            else:
                continue

        else:
            if score > dealer_score:
                balances[p["id"]] += p["bet"] * 2
            elif score == dealer_score:
                balances[p["id"]] += p["bet"]

    bot.send_message(chat_id, result)
    del games[chat_id]


# ================= ПЕРЕВОД МОНЕТ =================

@bot.message_handler(func=lambda m: m.text and m.text.startswith("п "))
def transfer(message):
    if not message.reply_to_message:
        return

    sender = message.from_user.id
    receiver = message.reply_to_message.from_user.id

    try:
        amount = int(message.text.split()[1])
    except:
        return

    if balances.get(sender, START_BALANCE) < amount:
        bot.send_message(message.chat.id,
                         f"У вас нет {amount}, чтобы передать.")
        return

    balances[sender] -= amount
    balances[receiver] = balances.get(receiver, START_BALANCE) + amount

    bot.send_message(message.chat.id,
                     f"Перевод {amount} выполнен.")


# ================= ЗАПУСК =================

bot.infinity_polling()