import telebot
import random
import time
from threading import Timer

TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"

bot = telebot.TeleBot(TOKEN)

# Игровые данные
games = {}
balances = {}
cooldowns = {}

START_BALANCE = 1000
COOLDOWN_TIME = 180  # 3 минуты


def create_deck():
    deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    random.shuffle(deck)
    return deck


def calculate_score(hand):
    score = sum(hand)
    while score > 21 and 11 in hand:
        hand[hand.index(11)] = 1
        score = sum(hand)
    return score


@bot.message_handler(commands=['блек'])
def start(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.reply_to(message, f"🎮 Добро пожаловать в Blackjack!\n💰 Твой баланс: {balances[user_id]}")


@bot.message_handler(commands=['баланс'])
def balance(message):
    user_id = message.from_user.id
    if user_id not in balances:
        balances[user_id] = START_BALANCE
    bot.reply_to(message, f"💰 Твой баланс: {balances[user_id]}")


@bot.message_handler(commands=['игра'])
def blackjack(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if user_id in cooldowns and time.time() < cooldowns[user_id]:
        bot.reply_to(message, "⏳ Подожди 3 минуты перед новой игрой.")
        return

    if chat_id not in games:
        games[chat_id] = {
            "players": [],
            "deck": create_deck(),
            "started": False
        }

    game = games[chat_id]

    if len(game["players"]) >= 3:
        bot.reply_to(message, "🚫 Стол уже заполнен (макс 3 игрока).")
        return

    if user_id not in balances:
        balances[user_id] = START_BALANCE

    game["players"].append({
        "id": user_id,
        "name": message.from_user.first_name,
        "hand": [],
        "bet": 100,
        "stand": False
    })

    bot.reply_to(message, f"🪑 {message.from_user.first_name} сел за стол.")

    if len(game["players"]) == 3:
        start_game(chat_id)


def start_game(chat_id):
    game = games[chat_id]
    game["started"] = True

    for player in game["players"]:
        player["hand"].append(game["deck"].pop())
        player["hand"].append(game["deck"].pop())

    message_text = "🃏 Игра началась!\n\n"
    for player in game["players"]:
        message_text += f"{player['name']}: {player['hand']} (Очки: {calculate_score(player['hand'])})\n"

    message_text += "\nПишите /доб или /стоп"

    bot.send_message(chat_id, message_text)


@bot.message_handler(commands=['доб'])
def hit(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in games:
        return

    game = games[chat_id]

    for player in game["players"]:
        if player["id"] == user_id and not player["stand"]:
            player["hand"].append(game["deck"].pop())
            score = calculate_score(player["hand"])

            if score > 21:
                player["stand"] = True
                bot.reply_to(message, f"💥 Перебор! У тебя {score}")

            else:
                bot.reply_to(message, f"🃏 Твои карты: {player['hand']} (Очки: {score})")

    check_end(chat_id)


@bot.message_handler(commands=['стоп'])
def stand(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in games:
        return

    game = games[chat_id]

    for player in game["players"]:
        if player["id"] == user_id:
            player["stand"] = True
            bot.reply_to(message, "✋ Ты остановился.")

    check_end(chat_id)


def check_end(chat_id):
    game = games[chat_id]

    if all(player["stand"] for player in game["players"]):
        end_game(chat_id)


def end_game(chat_id):
    game = games[chat_id]

    best_score = 0
    winner = None

    for player in game["players"]:
        score = calculate_score(player["доб"])
        if score <= 21 and score > best_score:
            best_score = score
            winner = player

    result_text = "🏁 Игра окончена!\n\n"

    for player in game["players"]:
        score = calculate_score(player["доб"])
        result_text += f"{player['name']}: {score}\n"

    if winner:
        balances[winner["id"]] += 200
        result_text += f"\n🏆 Победил {winner['name']} (+200)"
    else:
        result_text += "\nНикто не выиграл."

    for player in game["players"]:
        cooldowns[player["id"]] = time.time() + COOLDOWN_TIME

    bot.send_message(chat_id, result_text)
    del games[chat_id]


bot.infinity_polling()
