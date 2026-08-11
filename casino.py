import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import os
import random
import asyncio
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, log_financial_transaction
from utils import format_money, parse_amount, maybe_send_channel_reminder
from main_menu import show_work_menu, show_main_menu, show_settings, show_main_settings
from shit_cleaner import start_shit_cleaning, cancel_cleaning
from milker import start_milking, cancel_milking
from jobs import show_stats

USE_PHOTOS = True

# кэш для проверки существования фото файлов
photo_cache = {}

def cached_photo_exists(filename):
    """Кэшированная проверка существования файла"""
    if filename not in photo_cache:
        photo_cache[filename] = os.path.exists(filename)
    return photo_cache[filename]

def get_card_value(card):
    if card in ['J', 'Q', 'K']:
        return 10
    elif card == 'A':
        return 11
    else:
        return int(card)

def format_card(card, suit):
    return f"[{card}{suit}]"

def get_points_text(score):
    if score % 10 == 1 and score != 11:
        return f"{score} очко"
    elif score % 10 in [2, 3, 4] and score not in [12, 13, 14]:
        return f"{score} очка"
    else:
        return f"{score} очков"


# Функция для парсинга суммы ставки
def parse_bet_amount(bet_str: str, user_balance: int) -> int:
    """Парсит сумму ставки с поддержкой форматирования и дробных сокращений (напр. 1.5кк)"""
    return parse_amount(bet_str, max_amount=user_balance)

# Главное меню казино
async def show_casino_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await maybe_send_channel_reminder(update, context)
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await update.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    nickname = user[2]
    user_id_val = user[0]

    # Создаем ссылку на профиль пользователя с жирным шрифтом
    profile_link = f'<a href="tg://user?id={user_id_val}"><b>{nickname}</b></a>'

    message_text = f"""🎰 <b>казино дырявые трусы</b> 🎰

привет, {profile_link}! добро пожаловать в самое рискованное казино города!

выбери игру:"""

    # Клавиатура с кнопкой назад
    keyboard = [
        [KeyboardButton("назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Инвалидируем предыдущее сообщение главного меню
    if 'main_menu_message_id' in context.user_data and 'main_menu_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['main_menu_chat_id'],
                message_id=context.user_data['main_menu_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['main_menu_message_id']
        del context.user_data['main_menu_chat_id']

    # Отправляем фото с текстом приветствия казино
    casino_photo = 'images/casino_welcome.jpg'
    if USE_PHOTOS and cached_photo_exists(casino_photo):
        try:
            message1 = await update.message.reply_photo(
                photo=open(casino_photo, 'rb'),
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            message1 = await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        message1 = await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    # Сохраняем id первого сообщения казино
    context.user_data['casino_header_message_id'] = message1.message_id
    context.user_data['casino_header_chat_id'] = message1.chat_id

    # Второе сообщение с выбором игр (кнопки со строчной буквы)
    games_text = "🎮 <b>доступные игры:</b>"

    inline_keyboard = [
        [InlineKeyboardButton("🎰 автомат", callback_data="casino_slot")],
        [InlineKeyboardButton("🃏 блэкджек", callback_data="casino_blackjack")]
    ]
    inline_reply_markup = InlineKeyboardMarkup(inline_keyboard)

    message2 = await update.message.reply_text(
        games_text,
        reply_markup=inline_reply_markup,
        parse_mode='HTML'
    )

    # Сохраняем id второго сообщения казино
    context.user_data['casino_games_message_id'] = message2.message_id
    context.user_data['casino_games_chat_id'] = message2.chat_id

# Игровой автомат
async def show_slot_machine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)

    if not user:
        return

    # Проверяем, есть ли сохраненная ставка для этого автомата
    last_bet = context.user_data.get('last_slot_bet')
    if last_bet:
        # Показываем подтверждение с последней ставкой
        await show_bet_confirmation(update, context, last_bet)
        return

    message_text = f"""🎰 <b>автомат</b>

правила:
• 3 одинаковых символа = выигрыш x5

введи сумму ставки:
• можно использовать: 1000, 1к, 1.5к, 1кк, 1ккк
• или напиши "все" чтобы поставить весь баланс"""

    # Сохраняем состояние для обработки ставки
    context.user_data['waiting_for_bet'] = 'slot'

    # Редактируем сообщение вместо отправки нового
    try:
        await query.edit_message_text(
            message_text,
            reply_markup=None,
            parse_mode='HTML'
        )
    except Exception:
        message = await query.message.reply_text(
            message_text,
            parse_mode='HTML'
        )
        # Сохраняем id сообщения слот-машины
        if message:
            context.user_data['slot_machine_message_id'] = message.message_id
            context.user_data['slot_machine_chat_id'] = message.chat_id

# Блэкджек
async def show_blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)

    if not user:
        return

    # Проверяем, есть ли сохраненная ставка для блэкджека
    last_bet = context.user_data.get('last_blackjack_bet')
    if last_bet:
        # Показываем подтверждение с последней ставкой
        context.user_data['waiting_for_bet'] = 'blackjack'
        await show_bet_confirmation(update, context, last_bet)
        return

    message_text = f"""🃏 <b>блэкджек</b>

правила:
• цель: набрать 21 очко или ближе к 21 чем дилер
• туз = 1 или 11 очков
• картинки = 10 очков

введи сумму ставки:
• можно использовать: 1000, 1к, 1.5к, 1кк, 1ккк
• или напиши "все" чтобы поставить весь баланс"""

    # Очищаем предыдущее состояние и сохраняем для блэкджека
    if 'waiting_for_bet' in context.user_data:
        del context.user_data['waiting_for_bet']
    context.user_data['waiting_for_bet'] = 'blackjack'

    # Редактируем сообщение вместо отправки нового
    try:
        await query.edit_message_text(
            message_text,
            reply_markup=None,
            parse_mode='HTML'
        )
    except Exception:
        message = await query.message.reply_text(
            message_text,
            parse_mode='HTML'
        )
        # Сохраняем id сообщения блэкджека
        if message:
            context.user_data['blackjack_message_id'] = message.message_id
            context.user_data['blackjack_chat_id'] = message.chat_id



# Игра в автомат
async def play_slot_machine(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_amount: int):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        return

    # Сохраняем ставку для следующей игры
    context.user_data['last_slot_bet'] = bet_amount

    # Снимаем ставку
    new_balance = update_user_money(user_id, -bet_amount, check_balance=True)

    if new_balance is None:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="❌ недостаточно средств!"
        )
        return

    log_financial_transaction(user_id, "casino_loss", -bet_amount, "казино: ставка в слоты")

    # Отправляем анимированный стикер автомата из Telegram
    try:
        dice_message = await context.bot.send_dice(
            chat_id=update.effective_chat.id,
            emoji="🎰"
        )

        # Ждем завершения анимации (dice.value содержит результат 1-64)
        await asyncio.sleep(2)  # Даем время на анимацию

        dice_value = dice_message.dice.value

        # Инициализируем переменные перед проверками
        win_amount = 0
        win_text = ""

        # Определяем результат на основе dice_value
        # Выигрышные комбинации в Telegram slots:
        # 64 = 7️⃣7️⃣7️⃣ (супер джекпот) - проверяем первым
        # 1, 22, 43 = 3 одинаковых фрукта (джекпот)
        # 16, 32, 48 = BAR (выигрыш)

        if dice_value == 64:  # 777 - супер джекпот
            win_amount = bet_amount * 10
            win_text = "💎 СУПЕР ДЖЕКПОТ! 777 = x10!"
        elif dice_value in [1, 22, 43]:  # 3 одинаковых фрукта
            win_amount = bet_amount * 5
            win_text = "🎉 ДЖЕКПОТ! 3 одинаковых фрукта = x5!"
        elif dice_value in [16, 32, 48]:  # BAR
            win_amount = bet_amount * 3
            win_text = "✅ BAR = x3!"

    except Exception as e:
        print(f"Не удалось отправить dice: {e}")
        # Fallback - случайный результат
        win_amount = 0
        win_text = "❌ ошибка автомата"
        dice_value = 0

    # Выдаем выигрыш
    if win_amount > 0:
        update_user_money(user_id, win_amount)
        log_financial_transaction(user_id, "casino_win", win_amount, f"казино: выигрыш в слоты ({win_text})")
        new_balance += win_amount

    # Определяем заголовок результата
    if win_amount > 0:
        result_header = "✅ <b>ВЫИГРЫШ!</b>"
    else:
        result_header = "❌ <b>ПРОИГРЫШ!</b>"

    # Строим сообщение без лишних пробелов
    message_parts = [
        result_header,
        "",
        f"ставка: <b>{format_money(bet_amount)}</b>"
    ]

    if win_text.strip():
        message_parts.append(win_text)

    if win_amount > 0:
        message_parts.append(f"💰 выигрыш: <b>{format_money(win_amount)}</b>")

    message_parts.append(f"💰 баланс: <b>{format_money(new_balance)}</b>")

    message_text = "\n".join(message_parts)

    inline_keyboard = [
        [InlineKeyboardButton("играть еще", callback_data="slot_play_again")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    # Инвалидируем сообщение подтверждения ставки
    if 'current_bet_message_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=update.effective_user.id,
                message_id=context.user_data['current_bet_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['current_bet_message_id']

    message = await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    # Сохраняем ID сообщения для проверки кнопок
    context.user_data['casino_games_message_id'] = message.message_id
    context.user_data['casino_games_chat_id'] = message.chat_id

# Взять еще карту в блэкджеке
async def blackjack_hit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.message.message_id != context.user_data.get('current_blackjack_message_id'):
        await query.answer("❌ кнопка недействительна!", show_alert=True)
        return

    user_id = query.from_user.id
    user = get_user(user_id)

    if not user or 'blackjack_game' not in context.user_data:
        return

    game_state = context.user_data['blackjack_game']
    if not game_state['game_active']:
        return

    # Добавляем карту игроку
    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['♠️', '♥️', '♦️', '♣️']
    new_card = (random.choice(cards), random.choice(suits))
    game_state['player_cards'].append(new_card)

    # Пересчитываем очки игрока
    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    player_score = sum(get_card_value(card) for card, suit in game_state['player_cards'])

    # Корректируем тузы
    aces = sum(1 for card, suit in game_state['player_cards'] if card == 'A')
    while player_score > 21 and aces > 0:
        player_score -= 10
        aces -= 1

    # Проверяем перебор
    if player_score > 21:
        # Игра окончена - проигрыш
        await blackjack_end_game(update, context, "💥 ПЕРЕБОР! ПРОИГРЫШ!", 0)
        return

    # Обновляем сообщение
    await blackjack_update_message(update, context, game_state, player_score)

# Пас в блэкджеке
async def blackjack_stand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.message.message_id != context.user_data.get('current_blackjack_message_id'):
        await query.answer("❌ кнопка недействительна!", show_alert=True)
        return

    user_id = query.from_user.id
    user = get_user(user_id)

    if not user or 'blackjack_game' not in context.user_data:
        return

    game_state = context.user_data['blackjack_game']
    if not game_state['game_active']:
        return

    # Ход дилера
    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    dealer_cards = game_state['dealer_cards']
    dealer_score = sum(get_card_value(card) for card, suit in dealer_cards)

    # Корректируем тузы дилера
    aces = sum(1 for card, suit in dealer_cards if card == 'A')
    while dealer_score > 21 and aces > 0:
        dealer_score -= 10
        aces -= 1

    # Дилер берет карты пока меньше 17
    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['♠️', '♥️', '♦️', '♣️']

    while dealer_score < 17:
        new_card = (random.choice(cards), random.choice(suits))
        dealer_cards.append(new_card)
        dealer_score = sum(get_card_value(card) for card, suit in dealer_cards)

        # Корректируем тузы
        aces = sum(1 for card, suit in dealer_cards if card == 'A')
        while dealer_score > 21 and aces > 0:
            dealer_score -= 10
            aces -= 1

    # Определяем победителя
    player_score = sum(get_card_value(card) for card, suit in game_state['player_cards'])
    aces = sum(1 for card, suit in game_state['player_cards'] if card == 'A')
    while player_score > 21 and aces > 0:
        player_score -= 10
        aces -= 1

    if dealer_score > 21:
        await blackjack_end_game(update, context, "✅ ДИЛЕР ПЕРЕБРАЛ! ВЫИГРЫШ!", game_state['bet_amount'] * 2)
    elif player_score > dealer_score:
        await blackjack_end_game(update, context, "✅ ВЫ ПОБЕДИЛИ! ВЫИГРЫШ!", game_state['bet_amount'] * 2)
    elif player_score == dealer_score:
        await blackjack_end_game(update, context, "⚖️ НИЧЬЯ! ВОЗВРАТ СТАВКИ!", game_state['bet_amount'])
    else:
        await blackjack_end_game(update, context, "❌ ДИЛЕР ПОБЕДИЛ! ПРОИГРЫШ!", 0)

# Удвоить ставку в блэкджеке
async def blackjack_double(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.message.message_id != context.user_data.get('current_blackjack_message_id'):
        await query.answer("❌ кнопка недействительна!", show_alert=True)
        return

    user_id = query.from_user.id
    user = get_user(user_id)

    if not user or 'blackjack_game' not in context.user_data:
        return

    game_state = context.user_data['blackjack_game']
    if not game_state['game_active']:
        return

    # Удваиваем ставку
    game_state['bet_amount'] *= 2
    
    # Проверяем и снимаем баланс атомарно (в одной транзакции)
    new_balance = update_user_money(user_id, -game_state['bet_amount'] // 2, check_balance=True)
    
    if new_balance is None:
        await query.answer("❌ недостаточно средств для удвоения!", show_alert=True)
        game_state['bet_amount'] //= 2
        return

    game_state['current_balance'] = new_balance

    # Добавляем одну карту и завершаем ход
    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['♠️', '♥️', '♦️', '♣️']
    new_card = (random.choice(cards), random.choice(suits))
    game_state['player_cards'].append(new_card)

    # Пересчитываем очки
    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    player_score = sum(get_card_value(card) for card, suit in game_state['player_cards'])
    aces = sum(1 for card, suit in game_state['player_cards'] if card == 'A')
    while player_score > 21 and aces > 0:
        player_score -= 10
        aces -= 1

    if player_score > 21:
        await blackjack_end_game(update, context, "💥 ПЕРЕБОР! ПРОИГРЫШ!", 0)
        return

    # Ход дилера (как в stand)
    dealer_cards = game_state['dealer_cards']
    dealer_score = sum(get_card_value(card) for card, suit in dealer_cards)

    aces = sum(1 for card, suit in dealer_cards if card == 'A')
    while dealer_score > 21 and aces > 0:
        dealer_score -= 10
        aces -= 1

    while dealer_score < 17:
        new_card = (random.choice(cards), random.choice(suits))
        dealer_cards.append(new_card)
        dealer_score = sum(get_card_value(card) for card, suit in dealer_cards)

        aces = sum(1 for card, suit in dealer_cards if card == 'A')
        while dealer_score > 21 and aces > 0:
            dealer_score -= 10
            aces -= 1

    # Определяем победителя
    if dealer_score > 21:
        await blackjack_end_game(update, context, "✅ ДИЛЕР ПЕРЕБРАЛ! ВЫИГРЫШ!", game_state['bet_amount'] * 2)
    elif player_score > dealer_score:
        await blackjack_end_game(update, context, "✅ ВЫ ПОБЕДИЛИ! ВЫИГРЫШ!", game_state['bet_amount'] * 2)
    elif player_score == dealer_score:
        await blackjack_end_game(update, context, "⚖️ НИЧЬЯ! ВОЗВРАТ СТАВКИ!", game_state['bet_amount'])
    else:
        await blackjack_end_game(update, context, "❌ ДИЛЕР ПОБЕДИЛ! ПРОИГРЫШ!", 0)

# Обновление сообщения блэкджека
async def blackjack_update_message(update: Update, context: ContextTypes.DEFAULT_TYPE, game_state, player_score):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        return

    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    def format_card(card, suit):
        return f"[{card}{suit}]"

    def get_points_text(score):
        if score % 10 == 1 and score != 11:
            return f"{score} очко"
        elif score % 10 in [2, 3, 4] and score not in [12, 13, 14]:
            return f"{score} очка"
        else:
            return f"{score} очков"

    # Показываем все карты дилера кроме второй (если игра активна)
    dealer_cards = game_state['dealer_cards']
    if game_state['game_active']:
        dealer_cards_text = f"<b>{format_card(dealer_cards[0][0], dealer_cards[0][1])}</b> <b>[XX]</b>"
        dealer_visible_score = get_card_value(dealer_cards[0][0])
        dealer_score_text = get_points_text(dealer_visible_score)
    else:
        dealer_cards_text = ' '.join(f"<b>{format_card(card, suit)}</b>" for card, suit in dealer_cards)
        dealer_score = sum(get_card_value(card) for card, suit in dealer_cards)
        aces = sum(1 for card, suit in dealer_cards if card == 'A')
        while dealer_score > 21 and aces > 0:
            dealer_score -= 10
            aces -= 1
        dealer_score_text = get_points_text(dealer_score)

    player_cards_text = ' '.join(f"<b>{format_card(card, suit)}</b>" for card, suit in game_state['player_cards'])

    nickname = user[2]
    user_id_val = user[0]
    profile_link = f'<a href="tg://user?id={user_id_val}"><b>{nickname}</b></a>'

    message_text = f"""🃏 <b>блэкджек</b>

рука дилера ({dealer_score_text})
{dealer_cards_text}

рука {profile_link} ({get_points_text(player_score)})
{player_cards_text}

текущая ставка - <b>{format_money(game_state['bet_amount'])}</b>
баланс - <b>{format_money(game_state['current_balance'])}</b>"""

    if game_state['game_active']:
        inline_keyboard = [
            [InlineKeyboardButton("удвоить", callback_data="blackjack_double")],
            [InlineKeyboardButton("взять еще", callback_data="blackjack_hit")],
            [InlineKeyboardButton("пас", callback_data="blackjack_stand")]
        ]
    else:
        inline_keyboard = [
            [InlineKeyboardButton("играть еще", callback_data="blackjack_play_again")]
        ]

    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    try:
        await update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        message_id = update.callback_query.message.message_id
    except:
        message = await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        message_id = message.message_id
    context.user_data['current_blackjack_message_id'] = message_id

# Завершение игры в блэкджек
async def blackjack_end_game(update: Update, context: ContextTypes.DEFAULT_TYPE, result_text: str, win_amount: int):
    user_id = update.effective_user.id
    game_state = context.user_data['blackjack_game']

    # Выдаем выигрыш
    if win_amount > 0:
        game_state['current_balance'] = update_user_money(user_id, win_amount)
        log_financial_transaction(user_id, "casino_win", win_amount, f"казино: выигрыш в блэкджек ({result_text})")

    # Сохраняем финальную ставку для следующей игры
    context.user_data['last_blackjack_bet'] = game_state['bet_amount']

    game_state['game_active'] = False

    # Очищаем состояние игры после завершения
    if 'blackjack_game' in context.user_data:
        del context.user_data['blackjack_game']
    if 'current_blackjack_message_id' in context.user_data:
        del context.user_data['current_blackjack_message_id']

    # Показываем финальные карты
    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    player_score = sum(get_card_value(card) for card, suit in game_state['player_cards'])
    aces = sum(1 for card, suit in game_state['player_cards'] if card == 'A')
    while player_score > 21 and aces > 0:
        player_score -= 10
        aces -= 1

    await blackjack_update_message(update, context, game_state, player_score)

    # Добавляем результат сверху
    user = get_user(user_id)
    if user:
        nickname = user[2]
        user_id_val = user[0]
        profile_link = f'<a href="tg://user?id={user_id_val}"><b>{nickname}</b></a>'

        def get_points_text(score):
            if score % 10 == 1 and score != 11:
                return f"{score} очко"
            elif score % 10 in [2, 3, 4] and score not in [12, 13, 14]:
                return f"{score} очка"
            else:
                return f"{score} очков"

        dealer_score = sum(get_card_value(card) for card, suit in game_state['dealer_cards'])
        aces = sum(1 for card, suit in game_state['dealer_cards'] if card == 'A')
        while dealer_score > 21 and aces > 0:
            dealer_score -= 10
            aces -= 1

        def format_card(card, suit):
            return f"[{card}{suit}]"

        dealer_cards_text = ' '.join(f"<b>{format_card(card, suit)}</b>" for card, suit in game_state['dealer_cards'])
        player_cards_text = ' '.join(f"<b>{format_card(card, suit)}</b>" for card, suit in game_state['player_cards'])

        final_message = f"""{result_text}

🃏 <b>блэкджек</b>

рука дилера ({get_points_text(dealer_score)})
{dealer_cards_text}

рука {profile_link} ({get_points_text(player_score)})
{player_cards_text}

текущая ставка - <b>{format_money(game_state['bet_amount'])}</b>
баланс - <b>{format_money(game_state['current_balance'])}</b>"""

        inline_keyboard = [
            [InlineKeyboardButton("🃏 играть еще", callback_data="blackjack_play_again")]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard)

        try:
            await update.callback_query.edit_message_text(
                text=final_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=final_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

# Игра в блэкджек
async def play_blackjack(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_amount: int):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        return

    # Сохраняем ставку для следующей игры
    context.user_data['last_blackjack_bet'] = bet_amount

    # Снимаем ставку
    new_balance = update_user_money(user_id, -bet_amount, check_balance=True)

    if new_balance is None:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="❌ недостаточно средств!"
        )
        return

    log_financial_transaction(user_id, "casino_loss", -bet_amount, "казино: ставка в блэкджек")

    # Генерируем начальные карты
    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    suits = ['♠️', '♥️', '♦️', '♣️']

    def get_card_value(card):
        if card in ['J', 'Q', 'K']:
            return 10
        elif card == 'A':
            return 11
        else:
            return int(card)

    def format_card(card, suit):
        return f"[{card}{suit}]"

    # Начальные карты
    player_cards = [(random.choice(cards), random.choice(suits)), (random.choice(cards), random.choice(suits))]
    dealer_cards = [(random.choice(cards), random.choice(suits)), (random.choice(cards), random.choice(suits))]

    player_score = sum(get_card_value(card) for card, suit in player_cards)
    dealer_visible_score = get_card_value(dealer_cards[0][0])  # Только первая карта дилера видна

    # Корректируем тузы для игрока
    if player_score > 21:
        for i, (card, suit) in enumerate(player_cards):
            if card == 'A' and player_score > 21:
                player_score -= 10

    # Сохраняем состояние игры
    game_state = {
        'player_cards': player_cards,
        'dealer_cards': dealer_cards,
        'bet_amount': bet_amount,
        'current_balance': new_balance,
        'game_active': True
    }
    context.user_data['blackjack_game'] = game_state

    # Форматируем карты
    player_cards_text = ' '.join(f"<b>{format_card(card, suit)}</b>" for card, suit in player_cards)
    dealer_cards_text = f"<b>{format_card(dealer_cards[0][0], dealer_cards[0][1])}</b> <b>[XX]</b>"

    # Определяем правильное склонение "очков"
    def get_points_text(score):
        if score % 10 == 1 and score != 11:
            return f"{score} очко"
        elif score % 10 in [2, 3, 4] and score not in [12, 13, 14]:
            return f"{score} очка"
        else:
            return f"{score} очков"

    nickname = user[2]
    user_id_val = user[0]
    profile_link = f'<a href="tg://user?id={user_id_val}"><b>{nickname}</b></a>'

    message_text = f"""🃏 <b>блэкджек</b>

рука дилера ({get_points_text(dealer_visible_score)})
{dealer_cards_text}

рука {profile_link} ({get_points_text(player_score)})
{player_cards_text}

текущая ставка - <b>{format_money(bet_amount)}</b>
баланс - <b>{format_money(new_balance)}</b>"""

    inline_keyboard = [
        [InlineKeyboardButton("удвоить", callback_data="blackjack_double")],
        [InlineKeyboardButton("взять еще", callback_data="blackjack_hit")],
        [InlineKeyboardButton("пас", callback_data="blackjack_stand")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    message = await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    # Сохраняем ID сообщения для проверки кнопок
    context.user_data['current_blackjack_message_id'] = message.message_id



# Показать подтверждение ставки
async def show_bet_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_amount: int):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        return

    # Проверяем баланс
    if bet_amount > user[5]:
        message_text = f"❌ недостаточно средств! доступно: <b>{format_money(user[5])}</b>"
        if hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text=message_text,
                    parse_mode='HTML'
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=message_text,
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text(message_text, parse_mode='HTML')
        return

    game_type = context.user_data.get('waiting_for_bet', 'slot')
    game_name = {
        'slot': '🎰 автомат',
        'blackjack': '🃏 блэкджек'
    }.get(game_type, 'игра')

    message_text = f"""💰 <b>подтверждение ставки</b>

игра: {game_name}
ставка: <b>{format_money(bet_amount)}</b>

выбери действие:"""

    # Получаем баланс пользователя для кнопки "все"
    user_balance = user[5] if user else 0

    inline_keyboard = [
        [InlineKeyboardButton("х0.5", callback_data=f"bet_half_{bet_amount}"),
         InlineKeyboardButton("поставить", callback_data=f"bet_place_{bet_amount}"),
         InlineKeyboardButton("удвоить", callback_data=f"bet_double_{bet_amount}")],
        [InlineKeyboardButton("все", callback_data=f"bet_all_{user_balance}")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard)

    # Сохраняем ставку для подтверждения
    context.user_data['pending_bet'] = bet_amount

    # Если это callback query, редактируем сообщение
    if hasattr(update, 'callback_query') and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            context.user_data['current_bet_message_id'] = update.callback_query.message.message_id
            context.user_data['current_bet_chat_id'] = update.callback_query.message.chat_id
        except Exception:
            # Если не удалось отредактировать, отправляем новое сообщение
            sent = await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            context.user_data['current_bet_message_id'] = sent.message_id
            context.user_data['current_bet_chat_id'] = sent.chat_id
    else:
        # Для обычных сообщений отправляем новое
        sent = await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        context.user_data['current_bet_message_id'] = sent.message_id
        context.user_data['current_bet_chat_id'] = sent.chat_id

# Обработка ставок
async def handle_casino_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or 'waiting_for_bet' not in context.user_data:
        return

    text = update.message.text.strip()

    # Список команд, которые можно выполнять во время ожидания ставки
    cancel_commands = ['отмена', 'cancel', 'back']
    menu_commands = ['работа', 'работа ✅', 'назад', 'казино', 'казино ✅', 'магазин', 'дом', 'бизнес', 'донат', 'донат ✅', 'карта', 'помощь', 'помощь ✅', 'статистика', 'основные', '⬅️ назад', '⚙️', '🔄', '🔄 ✅']
    work_commands = ['начать чистку говна', 'начать доение', 'обновить время', 'отменить чистку', 'отменить доение']
    all_commands = cancel_commands + menu_commands + work_commands

    if text in all_commands:
        del context.user_data['waiting_for_bet']

        # Обрабатываем команду
        if text in cancel_commands:
            await show_casino_menu(update, context)
        elif text in ['работа', 'работа ✅']:
            await show_work_menu(update, context)
        elif text == 'назад':
            await show_main_menu(update, context)
        elif text in ['казино', 'казино ✅']:
            await show_casino_menu(update, context)
        elif text == 'магазин':
            await update.message.reply_text("🛍️ магазин в разработке")
        elif text == 'дом':
            await update.message.reply_text("🏠 дом в разработке")
        elif text == 'бизнес':
            await update.message.reply_text("💼 бизнес в разработке")
        elif text in ['донат', 'донат ✅']:
            from donations import show_donation_menu
            await show_donation_menu(update, context)
        elif text == 'карта':
            await update.message.reply_text("🗺️ карта в разработке")
        elif text in ['помощь', 'помощь ✅']:
            help_text = """🤖 <b>помощь по боту гангстер</b>

<b>основные команды:</b>
/start - начать работу с ботом
/me - открыть главное меню
/help - показать эту справку

<b>экономика:</b>
/pay @username сумма - перевести деньги другому игроку

💡 <b>совет:</b> используй кнопки в меню для удобной навигации!"""
            await update.message.reply_text(help_text, parse_mode='HTML')
        elif text == '⚙️':
            await show_settings(update, context)
        elif text == 'основные':
            await show_main_settings(update, context)
        elif text == '⬅️ назад':
            await show_main_menu(update, context)
        elif text == 'начать чистку говна':
            await start_shit_cleaning(update, context)
        elif text == 'статистика':
            await show_stats(update, context)
        elif text == 'начать доение':
            await start_milking(update, context)
        elif text == 'обновить время':
            # В зависимости от состояния, но для простоты пропускаем
            pass
        elif text == 'отменить чистку':
            await cancel_cleaning(update, context)
        elif text == 'отменить доение':
            await cancel_milking(update, context)
        return

    current_balance = user[5]

    # Парсим сумму ставки
    bet_amount = parse_bet_amount(update.message.text, current_balance)

    if bet_amount <= 0:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="❌ неверная сумма ставки!"
        )
        return

    if bet_amount > current_balance:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"❌ недостаточно средств! доступно: <b>{format_money(current_balance)}</b>"
        )
        return

    # Показываем подтверждение ставки
    await show_bet_confirmation(update, context, bet_amount)

# Возврат в меню казино
async def casino_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Очищаем состояние ожидания ставки и сообщений казино
    if 'waiting_for_bet' in context.user_data:
        del context.user_data['waiting_for_bet']
    
    # Удаляем кнопки из сообщений выбора режима казино
    if 'casino_games_message_id' in context.user_data and 'casino_games_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['casino_games_chat_id'],
                message_id=context.user_data['casino_games_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
    
    # Удаляем сообщения слот-машины и блэкджека если они есть
    if 'slot_machine_message_id' in context.user_data:
        del context.user_data['slot_machine_message_id']
    if 'slot_machine_chat_id' in context.user_data:
        del context.user_data['slot_machine_chat_id']
    if 'blackjack_message_id' in context.user_data:
        del context.user_data['blackjack_message_id']
    if 'blackjack_chat_id' in context.user_data:
        del context.user_data['blackjack_chat_id']
    
    # Показываем казино меню как новое сообщение
    await show_casino_menu_from_callback(query, context)

async def show_casino_menu_from_callback(query, context):
    """Показывает меню казино из callback с новым сообщением"""
    user_id = query.from_user.id
    user = get_user(user_id)

    if not user:
        return

    nickname = user[2]
    user_id_val = user[0]

    profile_link = f'<a href="tg://user?id={user_id_val}"><b>{nickname}</b></a>'

    message_text = f"""🎰 <b>казино дырявые трусы</b> 🎰

привет, {profile_link}! добро пожаловать в самое рискованное казино города!

выбери игру:"""

    inline_keyboard = [
        [InlineKeyboardButton("🎰 автомат", callback_data="casino_slot")],
        [InlineKeyboardButton("🃏 блэкджек", callback_data="casino_blackjack")]
    ]
    inline_reply_markup = InlineKeyboardMarkup(inline_keyboard)

    # Отправляем новое сообщение с выбором игр
    message = await query.message.reply_text(
        message_text,
        reply_markup=inline_reply_markup,
        parse_mode='HTML'
    )
    
    # Сохраняем id сообщения выбора игр
    if message:
        context.user_data['casino_games_message_id'] = message.message_id
        context.user_data['casino_games_chat_id'] = message.chat_id