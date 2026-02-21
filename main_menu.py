import os
import random
import datetime
import sqlite3
import asyncio
import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from registration import get_user, get_user_stats
from utils import format_money, safe_delete_message
from accessories import get_user_skin, get_user_skin_name, get_user_equipped_names, get_user_background_name, create_character_with_accessories

logger = logging.getLogger(__name__)

# используем локальные файлы или вообще убираем фото
USE_PHOTOS = True

# кэш для проверки существования фото файлов
photo_cache = {}

# кэш для отрисованных персонажей (user_id -> последний файл)
character_cache = {}

def cached_photo_exists(filename):
    """Кэшированная проверка существования файла"""
    if filename not in photo_cache:
        photo_cache[filename] = os.path.exists(filename)
    return photo_cache[filename]

# функция для получения приветствия по времени
def get_time_greeting():
    current_hour = datetime.datetime.now().hour
    
    if 5 <= current_hour < 12:
        greetings = [
            "доброе утро",
            "утречка",
            "с добрым утром",
            "привет с утра"
        ]
    elif 12 <= current_hour < 18:
        greetings = [
            "добрый день", 
            "день добрый",
            "приветствую в это время дня"
        ]
    elif 18 <= current_hour < 23:
        greetings = [
            "добрый вечер",
            "вечер в хату",
            "вечер добрый"
        ]
    else:  # 23-5 ночь
        greetings = [
            "доброй ночи",
            "ночь на дворе",
            "привет ночной сове",
            "о, ночной гуль"
        ]
    
    return random.choice(greetings)

# функция для получения случайного общего приветствия
def get_random_general_greeting():
    greetings = [
        "привет",
        "хай",
        "здарова", 
        "салют",
        "приветик",
        "здорово",
        "добро пожаловать",
        "рад тебя видеть",
        "как дела?",
        "чего как?",
        "че каво?",
        "как жизнь?",
        "чем занят?",
        "как сам?",
        "че по чем?",
        "здаровча",
        "приветствую",
        "здрасте",
        "хелло",
        "хаюшки",
        "здаровеньки булы"
    ]
    return random.choice(greetings)

# функция для создания текста главного меню
def create_main_menu_text(nickname: str, money: int, user_id: int, username: str = None, is_gangster_plus: bool = False):
    # случайно выбираем тип приветствия
    use_time_greeting = random.choice([True, False])
    
    if use_time_greeting:
        greeting = get_time_greeting()
    else:
        greeting = get_random_general_greeting()
    
    formatted_money = format_money(money)
    
    # Добавляем алмаз если есть подписка
    display_nickname = f"{nickname} 💎" if is_gangster_plus else nickname
    
    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{display_nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{display_nickname}</b></a>'
    
    message_text = f"""{greeting}, {profile_link}

сейчас ты находишься в <b>"город"</b>.

на счету у тя <b>{formatted_money}</b>"""
    
    return message_text

# главное меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, unknown_command=False):
    user_id = update.effective_user.id
    user = get_user(user_id)

    # определяем chat_id
    chat_id = None
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat_id
    else:
        chat_id = update.effective_chat.id if update.effective_chat else user_id

    if not user or not user[8]:
        await context.bot.send_message(chat_id=chat_id, text="сначала нужно зарегистрироваться! напиши /start")
        return

    # инвалидируем предыдущее сообщение настроек
    if 'settings_message_id' in context.user_data and 'settings_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['settings_chat_id'],
                message_id=context.user_data['settings_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['settings_message_id']
        del context.user_data['settings_chat_id']
    
    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    username = user[1] if len(user) > 1 else None
    color = user[4] if len(user) > 4 else "black"
    money = user[5] if len(user) > 5 else 0
    is_gangster_plus = user[18] if len(user) > 18 else False
    
    # определяем фото персонажа
    photo_file = 'images/character_black.jpg'
    if color == "white" and cached_photo_exists('images/character_white.jpg'):
        photo_file = 'images/character_white.jpg'
    
    # ОТОБРАЖАЕМ ПЕРСОНАЖА С АКСЕССУАРАМИ (с кэшированием)
    try:
        from accessories import create_character_with_accessories
        # Используем кэшированный персонаж если он есть
        if user_id not in character_cache:
            custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_main_menu.png')
            if custom_photo:
                character_cache[user_id] = custom_photo
                photo_file = custom_photo
        else:
            # Проверяем существует ли кэшированный файл
            if os.path.exists(character_cache[user_id]):
                photo_file = character_cache[user_id]
            else:
                # Пересоздаем если файл был удален
                custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_main_menu.png')
                if custom_photo:
                    character_cache[user_id] = custom_photo
                    photo_file = custom_photo
    except Exception as e:
        pass  # тихо используем дефолтный персонаж
    
    # передаем username в функцию создания текста
    message_text = create_main_menu_text(nickname, money, user_id, username, is_gangster_plus)
    
    # если была неизвестная команда, добавляем сообщение сверху
    if unknown_command:
        message_text = f"❌ неизвестная команда!\n\n{message_text}"
    
    # клавиатура главного меню
    keyboard = [
        [KeyboardButton("работа"), KeyboardButton("казино"), KeyboardButton("магазин")],
        [KeyboardButton("дом"), KeyboardButton("бизнес"), KeyboardButton("донат"), KeyboardButton("карта")],
        [KeyboardButton("🔄"), KeyboardButton("помощь"), KeyboardButton("⚙️")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # ОТПРАВКА С ФОТО - СУПЕРНАДЕЖНАЯ ВЕРСИЯ
    message = None
    max_attempts = 2
    
    if USE_PHOTOS and os.path.exists(photo_file):
        for attempt in range(max_attempts):
            try:
                # Простая отправка без сложных таймаутов
                with open(photo_file, 'rb') as photo:
                    message = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                break

            except Exception as e:
                if attempt == max_attempts - 1:
                    # Последняя попытка - отправляем только текст
                    message = await context.bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    # Ждем перед следующей попыткой
                    await asyncio.sleep(1)
    else:
        # Отправляем только текст если фото отключено или не найдено
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    # сохраняем id сообщения главного меню
    if message:
        context.user_data['main_menu_message_id'] = message.message_id
        context.user_data['main_menu_chat_id'] = message.chat_id

# функция для обновления главного меню
async def refresh_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Просто показываем новое главное меню
    await show_main_menu(update, context)

# функция для создания текста профиля - ИСПРАВЛЕННАЯ ВЕРСИЯ
def create_profile_text(user_data, is_viewer_admin=False):
    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    user_id = user_data[0] if len(user_data) > 0 else 0
    nickname = user_data[2] if len(user_data) > 2 else "неизвестно"
    username = user_data[1] if len(user_data) > 1 else None
    money = user_data[5] if len(user_data) > 5 else 0
    is_gangster_plus = user_data[18] if len(user_data) > 18 else False
    
    display_nickname = f"{nickname} 💎" if is_gangster_plus else nickname
    
    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{display_nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{display_nickname}</b></a>'
    
    # Для админов показываем баланс
    if is_viewer_admin:
        formatted_money = format_money(money)
        message_text = f"""вот так выглядит {profile_link}

баланс: {formatted_money}"""
    else:
        # Для обычных юзеров только ник
        message_text = f"""вот так выглядит {profile_link}"""

    return message_text

# функция для создания админской клавиатуры - ИСПРАВЛЕННАЯ ВЕРСИЯ
def create_admin_keyboard(target_user_id, target_user_data):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    is_banned = target_user_data[9] if len(target_user_data) > 9 else False
    is_target_admin = target_user_data[6] if len(target_user_data) > 6 else False
    is_target_main_admin = target_user_data[7] if len(target_user_data) > 7 else False
    
    keyboard = []
    
    if not is_target_main_admin:
        # Кнопка поставить/снять админку
        if is_target_admin:
            keyboard.append([InlineKeyboardButton("✅ снять", callback_data=f"admin_toggle_admin_{target_user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("✅ поставить", callback_data=f"admin_toggle_admin_{target_user_id}")])
        
        # Кнопки забана/разбана
        if is_banned:
            keyboard.append([InlineKeyboardButton("🚫 разбанить", callback_data=f"admin_unban_{target_user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("⛔ забанить", callback_data=f"admin_ban_{target_user_id}")])
        
        # Кнопка выдачи админ коинов (если админ)
        if is_target_admin:
            keyboard.append([InlineKeyboardButton("💎 выдать коины", callback_data=f"admin_give_coins_{target_user_id}")])
        
        # Кнопки логов и аксессуаров
        keyboard.append([
            InlineKeyboardButton("👕 аксессуары", callback_data=f"admin_view_accessories_{target_user_id}"),
            InlineKeyboardButton("📋 логи", callback_data=f"admin_view_logs_{target_user_id}")
        ])
    else:
        # Для главного админа - только кнопка выдачи коинов и логов
        keyboard.append([InlineKeyboardButton("💎 выдать коины", callback_data=f"admin_give_coins_{target_user_id}")])
        keyboard.append([InlineKeyboardButton("📋 логи", callback_data=f"admin_view_logs_{target_user_id}")])
    
    return InlineKeyboardMarkup(keyboard)

# показать профиль пользователя - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def show_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data, is_admin_viewer=False):
    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    user_id = user_data[0] if len(user_data) > 0 else 0
    is_main_admin_user = user_data[7] if len(user_data) > 7 else False
    is_target_admin = user_data[6] if len(user_data) > 6 else False
    nickname = user_data[2] if len(user_data) > 2 else "неизвестно"
    username = user_data[1] if len(user_data) > 1 else None
    color = user_data[4] if len(user_data) > 4 else "black"
    
    # Обработка профиля главного админа
    if is_main_admin_user:
        if not is_admin_viewer:
            message_text = """🔒 <b>профиль главного админа</b>

👤 <b>информация скрыта для безопасности</b>
💼 <b>статус:</b> главный админ

🔐 <b>доступ к полным данным ограничен</b>"""
            await update.message.reply_text(message_text, parse_mode='HTML')
            return
        else:
            # Админ может видеть профиль главного админа с персонажем
            display_nickname = f"{nickname} 💎"
            if username:
                profile_link = f'<a href="https://t.me/{username}"><b>{display_nickname}</b></a>'
            else:
                profile_link = f'<a href="tg://user?id={user_id}"><b>{display_nickname}</b></a>'
            
            message_text = f"вот так выглядит {profile_link}\n\nроль: главный админ"
            
            # Показываем с персонажем
            photo_file = None
            try:
                from accessories import create_character_with_accessories
                profile_cache_key = f"profile_{user_id}"
                if profile_cache_key not in character_cache:
                    custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_profile.png')
                    if custom_photo:
                        character_cache[profile_cache_key] = custom_photo
                        photo_file = custom_photo
                else:
                    if os.path.exists(character_cache[profile_cache_key]):
                        photo_file = character_cache[profile_cache_key]
                    else:
                        custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_profile.png')
                        if custom_photo:
                            character_cache[profile_cache_key] = custom_photo
                            photo_file = custom_photo
            except Exception as e:
                pass
            
            if not photo_file:
                if color == "white":
                    photo_file = 'images/character_white.jpg' if cached_photo_exists('images/character_white.jpg') else 'images/registration.jpg'
                else:
                    photo_file = 'images/character_black.jpg' if cached_photo_exists('images/character_black.jpg') else 'images/registration.jpg'
            
            # Клавиатура для админа, смотрящего главного админа
            keyboard = [
                [InlineKeyboardButton("💎 выдать коины", callback_data=f"admin_give_coins_{user_id}"),
                 InlineKeyboardButton("📋 логи", callback_data=f"admin_view_logs_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if USE_PHOTOS:
                try:
                    await update.message.reply_photo(
                        photo=open(photo_file, 'rb') if cached_photo_exists(photo_file) else None,
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception:
                    await update.message.reply_text(
                        message_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(
                    message_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            return
    
    # получаем статистику
    stats = get_user_stats(user_id)
    
    # создаем текст профиля
    message_text = create_profile_text(user_data, is_admin_viewer)
    
    # создаем инлайн клавиатуру 
    reply_markup = None
    if is_admin_viewer:
        # Клавиатура для админа, смотрящего профиль другого
        viewer_id = context.user_data.get('viewer_id')  # Это должна быть переменная, которую нам нужно пока добавить
        # На данный момент используем create_admin_keyboard для совместимости
        reply_markup = create_admin_keyboard(user_id, user_data)
    
    # ОТОБРАЖАЕМ ПЕРСОНАЖА С АКСЕССУАРАМИ (с кэшированием)
    photo_file = None
    
    # ОТОБРАЖАЕМ ПЕРСОНАЖА С АКСЕССУАРАМИ (с кэшированием)
    photo_file = None
    try:
        from accessories import create_character_with_accessories
        # Используем кэшированный персонаж если он есть
        profile_cache_key = f"profile_{user_id}"
        if profile_cache_key not in character_cache:
            custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_profile.png')
            if custom_photo:
                character_cache[profile_cache_key] = custom_photo
                photo_file = custom_photo
        else:
            # Проверяем существует ли кэшированный файл
            if os.path.exists(character_cache[profile_cache_key]):
                photo_file = character_cache[profile_cache_key]
            else:
                # Пересоздаем если файл был удален
                custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_profile.png')
                if custom_photo:
                    character_cache[profile_cache_key] = custom_photo
                    photo_file = custom_photo
    except Exception as e:
        pass  # тихо используем дефолтный персонаж
    
    # Если не удалось создать с аксессуарами, используем базовое изображение
    if not photo_file:
        if color == "white":
            photo_file = 'images/character_white.jpg' if cached_photo_exists('images/character_white.jpg') else 'images/registration.jpg'
        else:  # black
            photo_file = 'images/character_black.jpg' if cached_photo_exists('images/character_black.jpg') else 'images/registration.jpg'
    
    # отправляем фото с текстом профиля и кнопками
    if USE_PHOTOS:
        try:
            await update.message.reply_photo(
                photo=open(photo_file, 'rb') if cached_photo_exists(photo_file) else None,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

# меню выбора работы
async def show_work_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:
        chat_id = update.message.chat_id if update.message else update.effective_user.id
        await context.bot.send_message(chat_id=chat_id, text="сначала нужно зарегистрироваться! напиши /start")
        return
    
    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    user_id_val = user[0] if len(user) > 0 else user_id
    
    # создаем ссылку на профиль пользователя с жирным шрифтом
    profile_link = f'<a href="tg://user?id={user_id_val}">{nickname}</a>'
    
    # ==== ИНВАЛИДИРУЕМ ВСЕ СТАРЫЕ СООБЩЕНИЯ ПЕРЕД СОЗДАНИЕМ НОВЫХ ====
    keys_to_invalidate = [
        ('casino_header_message_id', 'casino_header_chat_id'),
        ('casino_games_message_id', 'casino_games_chat_id'),
        ('main_menu_message_id', 'main_menu_chat_id'),
        ('shit_cleaner_message_id', 'shit_cleaner_chat_id'),
        ('milker_message_id', 'milker_chat_id'),
        ('stats_message_id', 'stats_chat_id')
    ]
    
    for msg_key, chat_key in keys_to_invalidate:
        if msg_key in context.user_data and chat_key in context.user_data:
            try:
                chat_id = context.user_data[chat_key]
                message_id = context.user_data[msg_key]
                # Убираем кнопки
                try:
                    await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                except Exception:
                    pass
                
                # Добавляем в inactive_messages
                inactive_list = context.user_data.get('inactive_messages', [])
                if not isinstance(inactive_list, list):
                    inactive_list = []
                if message_id not in inactive_list:
                    inactive_list.append(message_id)
                context.user_data['inactive_messages'] = inactive_list
                
                # Удаляем ключи
                del context.user_data[msg_key]
                del context.user_data[chat_key]
            except Exception:
                pass

    # первое сообщение: заголовок с кнопкой "назад"
    header_text = f"<b>{profile_link}</b>, выбери работу, на которой хочешь сейчас работать:"

    # reply-клавиатура с кнопкой "назад"
    reply_keyboard = [
        [KeyboardButton("назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    # отправляем первое сообщение с заголовком и кнопкой "назад"
    header_message = await update.message.reply_text(
        header_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # второе сообщение: доступные работы с инлайн кнопками
    work_text = """<b>доступные тебе работы:</b>"""
    
    # инлайн клавиатура выбора работы - кнопки в двух рядах
    inline_keyboard = [
        [InlineKeyboardButton("💩 говночист", callback_data="work_shit_cleaner"), 
         InlineKeyboardButton("🐄 дояр", callback_data="work_milker")],
        [InlineKeyboardButton("💻 скам", callback_data="work_scam")]
    ]
    inline_reply_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # отправляем второе сообщение с инлайн кнопками
    work_message = await update.message.reply_text(
        work_text,
        reply_markup=inline_reply_markup,
        parse_mode='HTML'
    )
    
    # сохраняем id сообщений для возможного удаления
    context.user_data['work_header_message_id'] = header_message.message_id
    context.user_data['work_header_chat_id'] = header_message.chat_id
    context.user_data['work_menu_message_id'] = work_message.message_id
    context.user_data['work_menu_chat_id'] = work_message.chat_id

# функция для проверки является ли пользователь главным админом
def is_main_admin(user_id):
    user = get_user(user_id)
    return user and len(user) > 7 and user[7]

# функция для назначения админа
def make_admin(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = TRUE WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# меню настроек
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await update.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    username = user[1] if len(user) > 1 else None
    gender = user[3] if len(user) > 3 else "male"
    color = user[4] if len(user) > 4 else "black"
    disable_transfer_confirmation = user[14] if len(user) > 14 else False

    # определяем фото персонажа
    photo_file = 'images/character_black.jpg'
    if color == "white" and cached_photo_exists('images/character_white.jpg'):
        photo_file = 'images/character_white.jpg'

    gender_text = "👨" if gender == "male" else "👩"
    color_text = "⚫ черный" if color == "black" else "⚪ белый"

    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{nickname}</b></a>'

    message_text = f"""выбери что хочешь изменить:"""

    # клавиатура настроек - reply кнопки
    keyboard = [
        [KeyboardButton("основные")],
        [KeyboardButton("⬅️ назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # инвалидируем предыдущее сообщение главного меню
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

    # инвалидируем предыдущее сообщение основных настроек
    if 'main_settings_message_id' in context.user_data and 'main_settings_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['main_settings_chat_id'],
                message_id=context.user_data['main_settings_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['main_settings_message_id']
        del context.user_data['main_settings_chat_id']

    # сохраняем состояние - пользователь в меню настроек
    context.user_data['in_settings'] = True

    # отправляем фото с текстом настроек
    settings_photo = 'images/settings_menu.jpg'
    if USE_PHOTOS and cached_photo_exists(settings_photo):
        try:
            message = await context.bot.send_photo(
                chat_id=user_id,
                photo=open(settings_photo, 'rb'),
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            message = await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        message = await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    # сохраняем id сообщения настроек для инвалидации
    if message:
        context.user_data['settings_message_id'] = message.message_id
        context.user_data['settings_chat_id'] = message.chat_id

# меню основных настроек
async def show_main_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await update.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    if not user or not user[8]:
        await update.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    username = user[1] if len(user) > 1 else None
    gender = user[3] if len(user) > 3 else "male"
    color = user[4] if len(user) > 4 else "black"

    gender_text = "👨" if gender == "male" else "👩"
    color_text = "⚫ черный" if color == "black" else "⚪ белый"

    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{nickname}</b></a>'

    transfer_confirmation_text = "отключено" if (user[14] if len(user) > 14 else False) else "включено"
    skin_name = get_user_skin_name(user_id)
    equipped_names = get_user_equipped_names(user_id)
    background_name = get_user_background_name(user_id)
    
    # Формируем текст о аксессуарах (в форме списка)
    accessories_text = ""
    if equipped_names['head'] or equipped_names['hand'] or equipped_names['body'] or equipped_names['feet']:
        accessories_list = []
        if equipped_names['head']:
            accessories_list.append(f"голова: {equipped_names['head']}")
        if equipped_names['hand']:
            accessories_list.append(f"рука: {equipped_names['hand']}")
        if equipped_names['body']:
            accessories_list.append(f"тело: {equipped_names['body']}")
        if equipped_names['feet']:
            accessories_list.append(f"ноги: {equipped_names['feet']}")
        accessories_text = "\n🎭 аксессуары:\n" + "\n".join(accessories_list)
    else:
        accessories_text = "\n🎭 аксессуары: нет"

    message_text = f"""⚙️ <b>основные настройки</b>

{profile_link} {gender_text}
цвет кожи: {color_text}
👕 скин: {skin_name}
🖼️ фон: {background_name}{accessories_text}
💸 подтверждение переводов: {transfer_confirmation_text}

выбери что хочешь изменить:"""

    # клавиатура основных настроек
    keyboard = [
        [InlineKeyboardButton("👨👩 сменить пол", callback_data="settings_change_gender")],
        [InlineKeyboardButton("🎨 сменить цвет кожи", callback_data="settings_change_color")],
        [InlineKeyboardButton("✏️ сменить ник", callback_data="settings_change_name")],
        [InlineKeyboardButton("💸 подтверждение переводов", callback_data="settings_toggle_transfer_confirmation")],
        [InlineKeyboardButton("🔔 уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton("⬅️ назад", callback_data="settings_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # сохраняем состояние - пользователь в основных настройках
    context.user_data['in_main_settings'] = True

    # СОЗДАЕМ КАРТИНКУ ПЕРСОНАЖА С АКСЕССУАРАМИ
    photo_file = 'images/character_black.jpg'
    try:
        custom_photo = create_character_with_accessories(user_id, output_file='temp/temp_settings.png')
        if custom_photo:
            photo_file = custom_photo
    except Exception as e:
        pass  # тихо используем дефолтную картинку

    # отправляем фото с текстом основных настроек
    message = None
    if USE_PHOTOS and os.path.exists(photo_file):
        try:
            message = await context.bot.send_photo(
                chat_id=user_id,
                photo=open(photo_file, 'rb'),
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            message = await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        message = await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    # сохраняем id сообщения основных настроек для инвалидации кнопок
    if message:
        context.user_data['main_settings_message_id'] = message.message_id
        context.user_data['main_settings_chat_id'] = message.chat_id

# меню настроек уведомлений
async def show_notifications_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await update.callback_query.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    disable_transfer_notifications = user[15] if len(user) > 15 else False
    disable_news_notifications = user[16] if len(user) > 16 else False
    disable_system_notifications = user[17] if len(user) > 17 else False

    transfer_notifications_text = "отключены" if disable_transfer_notifications else "включены"
    news_notifications_text = "отключены" if disable_news_notifications else "включены"
    system_notifications_text = "отключены" if disable_system_notifications else "включены"

    message_text = f"""🔔 <b>настройки уведомлений</b>

💰 уведомления о получении денег: {transfer_notifications_text}
📢 новостная рассылка: {news_notifications_text}
⚙️ системные уведомления: {system_notifications_text}

выбери какие уведомления хочешь включить/отключить:"""

    # клавиатура настроек уведомлений
    keyboard = [
        [InlineKeyboardButton("💰 переводы", callback_data="notifications_toggle_transfer")],
        [InlineKeyboardButton("📢 новости", callback_data="notifications_toggle_news")],
        [InlineKeyboardButton("⚙️ системные", callback_data="notifications_toggle_system")],
        [InlineKeyboardButton("⬅️ назад", callback_data="settings_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # сохраняем состояние - пользователь в настройках уведомлений
    context.user_data['in_notifications_settings'] = True

    # отправляем фото с текстом настроек уведомлений
    notifications_photo = 'images/notifications_settings.jpg'
    if USE_PHOTOS and cached_photo_exists(notifications_photo):
        try:
            message = await update.callback_query.message.reply_photo(
                photo=open(notifications_photo, 'rb'),
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            message = await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        message = await update.callback_query.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    # сохраняем id сообщения настроек уведомлений для инвалидации
    if message:
        context.user_data['notifications_settings_message_id'] = message.message_id
        context.user_data['notifications_settings_chat_id'] = message.chat_id

# функция для выбора нового цвета
async def show_color_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await context.bot.send_message(chat_id=user_id, text="сначала нужно зарегистрироваться! напиши /start")
        return

    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    username = user[1] if len(user) > 1 else None

    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{nickname}</b></a>'

    message_text = f"""{profile_link}, выбери новый цвет кожи для своего персонажа:"""

    keyboard = [
        [InlineKeyboardButton("⚫ черный", callback_data="settings_color_black")],
        [InlineKeyboardButton("⚪ белый", callback_data="settings_color_white")],
        [InlineKeyboardButton("⬅️ назад", callback_data="settings_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.callback_query.edit_message_caption(
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception:
        try:
            await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            await update.callback_query.bot.send_message(
                chat_id=update.callback_query.from_user.id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

# функция для выбора нового пола
async def show_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await context.bot.send_message(chat_id=user_id, text="сначала нужно зарегистрироваться! напиши /start")
        return

    # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ
    nickname = user[2] if len(user) > 2 else "игрок"
    username = user[1] if len(user) > 1 else None

    # создаем кликабельную ссылку на профиль
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{nickname}</b></a>'

    message_text = f"""{profile_link}, выбери новый пол для своего персонажа:"""

    keyboard = [
        [InlineKeyboardButton("👨 парень", callback_data="settings_gender_male")],
        [InlineKeyboardButton("👩 девушка", callback_data="settings_gender_female")],
        [InlineKeyboardButton("⬅️ назад", callback_data="settings_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.callback_query.edit_message_caption(
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception:
        try:
            await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception:
            await update.callback_query.bot.send_message(
                chat_id=update.callback_query.from_user.id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )