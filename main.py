import asyncio
import random
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

API_TOKEN = "8370621833:AAHFQZDvE0Rn-bmUwvXeB5H2IF6wv9BZbj4"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Игроки и баланс
players_balance = {}
active_games = {}

# Карты
cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
card_values = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8,
               '9':9, '10':10, 'J':10, 'Q':10, 'K':10, 'A':11}

# Команда /блек
@dp.message_handler(commands=['блек'])
async def start_blackjack(message: types.Message):
    if message.from_user.id not in players_balance:
        players_balance[message.from_user.id] = 500
    await message.answer(f"Привет! Ваш баланс: {players_balance[message.from_user.id]} монет.")

# Команда /баланс
@dp.message_handler(commands=['баланс'])
async def check_balance(message: types.Message):
    balance = players_balance.get(message.from_user.id, 0)
    await message.answer(f"Ваш баланс: {balance} монет.")

# Команда /игра
@dp.message_handler(commands=['игра'])
async def create_game(message: types.Message):
    chat_id = message.chat.id
    if chat_id in active_games:
        await message.answer("Игра уже идет в этом чате!")
        return

    active_games[chat_id] = {
        "players": {},
        "deck": cards * 4,
        "started": False,
        "bets_done": False
    }

    join_button = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Присоединиться к столу", callback_data="join_game")
    )

    await message.answer("Набор игроков начат! Максимум 3 игрока.\nНажмите кнопку, чтобы присоединиться.", reply_markup=join_button)

# Игрок нажал "Присоединиться"
@dp.callback_query_handler(lambda c: c.data == "join_game")
async def join_game(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name

    game = active_games.get(chat_id)
    if not game:
        await callback_query.answer("Ошибка: игра не найдена.")
        return

    if user_id in game["players"]:
        await callback_query.answer("Вы уже присоединились!")
        return

    if len(game["players"]) >= 3:
        await callback_query.answer("Стол уже полон!")
        return

    await callback_query.answer()
    await bot.send_message(chat_id, f"{user_name} присоединился! Введите ставку:")

    # Ожидаем ставку
    def check(msg: types.Message):
        return msg.from_user.id == user_id and msg.chat.id == chat_id

    try:
        msg = await dp.bot.wait_for('message', timeout=180, check=check)
        bet = int(msg.text)
        if bet <= 0 or bet > players_balance.get(user_id, 0):
            await msg.reply("Неверная ставка! Попробуйте снова командой /игра")
            del game["players"][user_id]
            return
        game["players"][user_id] = {"name": user_name, "bet": bet, "cards": [], "stand": False, "cashout": False}
        players_balance[user_id] -= bet
        await msg.reply(f"Ставка принята: {bet} монет.")
    except asyncio.TimeoutError:
        await bot.send_message(chat_id, f"{user_name} не успел поставить ставку и не участвует.")
        return

    # Если набралось 3 игрока или прошло 3 минуты
    if len(game["players"]) == 3:
        await start_round(chat_id)

async def start_round(chat_id):
    game = active_games[chat_id]
    if game["started"]:
        return
    game["started"] = True

    # Раздаём карты
    deck = game["deck"]
    random.shuffle(deck)
    for player in game["players"].values():
        player["cards"].append(deck.pop())
        player["cards"].append(deck.pop())

    game["dealer"] = {"cards": [deck.pop(), deck.pop()]}
    await bot.send_message(chat_id, "Игра начинается! Дилер раздает карты.\nИспользуйте команды /добор или /стоп или /кэш.")

# Команда /добор
@dp.message_handler(commands=['добор'])
async def hit_card(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)
    if not game or user_id not in game["players"]:
        await message.answer("Вы не участвуете в игре.")
        return
    if game["players"][user_id]["stand"]:
        await message.answer("Вы уже остановились.")
        return
    card = game["deck"].pop()
    game["players"][user_id]["cards"].append(card)
    total = calculate_total(game["players"][user_id]["cards"])
    await message.answer(f"Вам выпала карта {card}. Всего: {total}")
    if total > 21:
        await message.answer("Перебор! Вы выбыли.")
        game["players"][user_id]["stand"] = True

# Команда /стоп
@dp.message_handler(commands=['стоп'])
async def stand(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)
    if not game or user_id not in game["players"]:
        await message.answer("Вы не участвуете в игре.")
        return
    game["players"][user_id]["stand"] = True
    await message.answer("Вы остановились.")
    if all(p["stand"] or p["cashout"] for p in game["players"].values()):
        await finish_game(chat_id)

# Команда /кэш
@dp.message_handler(commands=['кэш'])
async def cashout(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    game = active_games.get(chat_id)
    if not game or user_id not in game["players"]:
        await message.answer("Вы не участвуете в игре.")
        return
    bet = game["players"][user_id]["bet"]
    payout = int(bet * 0.7)
    players_balance[user_id] += payout
    game["players"][user_id]["cashout"] = True
    await message.answer(f"Вы забрали 70% ставки: {payout} монет.")
    if all(p["stand"] or p["cashout"] for p in game["players"].values()):
        await finish_game(chat_id)

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

async def finish_game(chat_id):
    game = active_games[chat_id]
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

    await bot.send_message(chat_id, result_text)
    del active_games[chat_id]

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)