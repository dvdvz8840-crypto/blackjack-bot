import os
import telebot
import random
import threading
import time

API_TOKEN = os.getenv("8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4")
bot = telebot.TeleBot(API_TOKEN)

# Балансы игроков
players_balance = {}

# Активные игры по chat_id
active_games = {}

# Карты и значения
cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
card_values = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8,
               '9':9, '10':10, 'J':10, 'Q':10, 'K':10, 'A':11}

# ===================== Команды =====================

# /блек - приветствие и баланс
@bot.message_handler(commands=['блек'])
def start_blackjack(message):
    user_id = message.from_user.id
    if user_id not in players_balance:
        players_balance[user_id] = 500
    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Ваш баланс: {players_balance[user_id]} монет.")

# /баланс - проверка баланса
@bot.message_handler(commands=['баланс'])
def check_balance(message):
    balance = players_balance.get(message.from_user.id, 0)
    bot.send_message(message.chat.id, f"Ваш баланс: {balance} монет.")

# /игра - начать набор игроков
@bot.message_handler(commands=['игра'])
def create_game(message):
    chat_id = message.chat.id
    if chat_id in active_games:
        bot.send_message(chat_id, "Игра уже идет!")
        return

    active_games[chat_id] = {
        "players": {},
        "deck": cards * 4,
        "started": False
    }

    bot.send_message(chat_id,
        "Набор игроков начат! Максимум 3 игрока.\nЧтобы присоединиться, напишите 'присоединиться' в чат.\nСтавка обязательна.")

# ===================== Присоединение к игре =====================
@bot.message_handler(func=lambda message: message.text.lower() == "присоединиться")
def join_game(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id not in active_games:
        bot.send_message(chat_id, "Сначала начните игру командой /игра.")
        return

    game = active_games[chat_id]

    if user_id in game["players"]:
        bot.send_message(chat_id, f"{user_name}, вы уже присоединились!")
        return

    if len(game["players"]) >= 3:
        bot.send_message(chat_id, "Стол уже полон!")
        return

    # Запрос ставки
    bot.send_message(chat_id, f"{user_name}, введите вашу ставку:")

    # Ожидание ставки через обработчик сообщений
    @bot.message_handler(func=lambda m: m.from_user.id == user_id and m.chat.id == chat_id)
    def receive_bet(msg):
        try:
            bet = int(msg.text)
            if bet <= 0 or bet > players_balance.get(user_id, 0):
                bot.send_message(chat_id, f"{user_name}, неверная ставка. Попробуйте присоединиться заново.")
                return
        except ValueError:
            bot.send_message(chat_id, f"{user_name}, ставка должна быть числом. Попробуйте присоединиться заново.")
            return

        # Ставка принята
        players_balance[user_id] -= bet
        game["players"][user_id] = {
            "name": user_name,
            "bet": bet,
            "cards": [],
            "stand": False,
            "cashout": False
        }
        bot.send_message(chat_id, f"{user_name} присоединился со ставкой {bet} монет.")

        # Если набралось 3 игрока, запускаем игру
        if len(game["players"]) == 3:
            start_round(chat_id)

        # Запускаем таймер на 3 минуты для автоматического старта
        threading.Thread(target=wait_and_start, args=(chat_id,)).start()

# ===================== Таймер ожидания =====================
def wait_and_start(chat_id):
    game = active_games.get(chat_id)
    if not game or game["started"]:
        return
    time.sleep(180)  # ждем 3 минуты
    if not game["started"] and len(game["players"]) > 0:
        start_round(chat_id)

# ===================== Игровой раунд =====================
def start_round(chat_id):
    game = active_games[chat_id]
    if game["started"]:
        return
    game["started"] = True
    deck = game["deck"]
    random.shuffle(deck)

    # Раздача карт игрокам
    for player in game["players"].values():
        player["cards"].append(deck.pop())
        player["cards"].append(deck.pop())

    # Дилер
    game["dealer"] = {"cards": [deck.pop(), deck.pop()]}

    bot.send_message(chat_id, "Игра начинается! Дилер раздает карты.\nИспользуйте команды /добор, /стоп или /кэш.")

# ===================== Команды хода =====================
@bot.message_handler(commands=['добор'])
def hit_card(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)

    if not game or user_id not in game["players"]:
        bot.send_message(chat_id, "Вы не участвуете в игре.")
        return

    player = game["players"][user_id]
    if player["stand"]:
        bot.send_message(chat_id, "Вы уже остановились.")
        return

    card = game["deck"].pop()
    player["cards"].append(card)
    total = calculate_total(player["cards"])
    bot.send_message(chat_id, f"{player['name']}, вам выпала карта {card}. Всего очков: {total}")
    if total > 21:
        bot.send_message(chat_id, f"{player['name']}, перебор! Вы выбыли.")
        player["stand"] = True
        check_finish(chat_id)

@bot.message_handler(commands=['стоп'])
def stand(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)
    if not game or user_id not in game["players"]:
        bot.send_message(chat_id, "Вы не участвуете в игре.")
        return
    game["players"][user_id]["stand"] = True
    bot.send_message(chat_id, f"{game['players'][user_id]['name']} остановился.")
    check_finish(chat_id)

@bot.message_handler(commands=['кэш'])
def cashout(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)
    if not game or user_id not in game["players"]:
        bot.send_message(chat_id, "Вы не участвуете в игре.")
        return
    bet = game["players"][user_id]["bet"]
    payout = int(bet * 0.7)
    players_balance[user_id] += payout
    game["players"][user_id]["cashout"] = True
    bot.send_message(chat_id, f"{game['players'][user_id]['name']} забрал 70% ставки: {payout} монет.")
    check_finish(chat_id)

# ===================== Проверка завершения игры =====================
def check_finish(chat_id):
    game = active_games.get(chat_id)
    if not game:
        return

    if all(p["stand"] or p["cashout"] for p in game["players"].values()):
        finish_game(chat_id)

# ===================== Подсчет очков =====================
def calculate_total(cards_list):
    total = 0
    aces = 0
    for c in cards_list:
        total += card_values[c]
        if c == 'A':
            aces += 1
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

# ===================== Завершение игры =====================
def finish_game(chat_id):
    game = active_games.get(chat_id)
    if not game:
        return

    dealer_total = calculate_total(game["dealer"]["cards"])
    # Дилер берет карты пока <17
    while dealer_total < 17:
        game["dealer"]["cards"].append(game["deck"].pop())
        dealer_total = calculate_total(game["dealer"]["cards"])

    result_text = f"Дилер имеет {dealer_total} очков, карты: {game['dealer']['cards']}\n"
    for uid, p in game["players"].items():
        total = calculate_total(p["cards"])
        if p["cashout"]:
            continue
        if total > 21:
            result_text += f"{p['name']}: Перебор, проигрыш\n"
        elif dealer_total > 21 or total > dealer_total:
            players_balance[uid] += p["bet"]*2
            result_text += f"{p['name']}: Победа! Баланс +{p['bet']*2}\n"
        elif total == dealer_total:
            players_balance[uid] += p["bet"]
            result_text += f"{p['name']}: Ничья. Ставка возвращена\n"
        else:
            result_text += f"{p['name']}: Проигрыш\n"

    bot.send_message(chat_id, result_text)
    del active_games[chat_id]

# ===================== Запуск бота =====================
if __name__ == "__main__":
    print("Бот запущен")
    bot.polling()