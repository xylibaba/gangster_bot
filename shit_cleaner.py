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
import time
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, get_user_stats, update_user_stats
from utils import safe_delete_message

USE_PHOTOS = True

# кэш для проверки существования фото файлов
photo_cache = {}

def cached_photo_exists(filename):
    """Кэшированная проверка существования файла"""
    if filename not in photo_cache:
        photo_cache[filename] = os.path.exists(filename)
    return photo_cache[filename]

# Функция для форматирования денег
def format_money(amount: int) -> str:
    # защита от None
    if amount is None:
        return "0$"
    
    # преобразуем в целое число если нужно
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "0$"
    
    if amount < 1000:
        return f"{amount}$"
    elif amount < 1000000:
        return f"{amount:,}$".replace(",", ".")
    else:
        return f"{amount:,}$".replace(",", ".")

# Безопасная отправка сообщений с фото
async def safe_send_message(update: Update, text: str, photo_file: str = None, reply_markup=None, parse_mode='HTML'):
    """Безопасная отправка сообщения с фото или без"""
    try:
        if USE_PHOTOS and photo_file and cached_photo_exists(photo_file):
            # Проверяем размер файла
            file_size = os.path.getsize(photo_file)
            if file_size < 10 * 1024 * 1024:  # меньше 10MB
                with open(photo_file, 'rb') as photo:
                    return await update.message.reply_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        read_timeout=20,
                        write_timeout=20
                    )
        
        # Если фото недоступно - отправляем только текст
        return await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")
        # Фолбэк на простой текст
        return await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

# Функция для показа прогресса чистки
async def show_cleaning_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_cleaning'):
        await update.message.reply_text("❌ ты сейчас не чистишь говно!")
        return
    
    # Получаем текущее время и вычисляем оставшееся
    start_time = context.user_data.get('cleaning_start_time', 0)
    duration = context.user_data.get('cleaning_duration', 0)
    current_time = time.time()
    elapsed = current_time - start_time
    remaining = max(0, duration - elapsed)
    
    # Форматируем время
    time_text = format_time(int(remaining))
    salary = calculate_cleaning_salary(duration)
    
    # Текст для сообщения
    message_text = f"🧹 ты чистишь говно!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить чистку")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение
    await safe_send_message(
        update=update,
        text=message_text,
        photo_file='cleaning_in_progress.jpg',
        reply_markup=reply_markup
    )

# Меню работы говночиста
async def show_shit_cleaner_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        await update.message.reply_text("сначала нужно зарегистрироваться! напиши /start")
        return

    # Инвалидируем предыдущие сообщения меню работы
    if 'work_header_message_id' in context.user_data and 'work_header_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['work_header_chat_id'],
                message_id=context.user_data['work_header_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['work_header_message_id']
        del context.user_data['work_header_chat_id']
    if 'work_menu_message_id' in context.user_data and 'work_menu_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['work_menu_chat_id'],
                message_id=context.user_data['work_menu_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['work_menu_message_id']
        del context.user_data['work_menu_chat_id']
    
    nickname = user[2]
    user_id_val = user[0]
    
    # Создаем ссылку на профиль пользователя
    profile_link = f'<a href="tg://user?id={user_id_val}">{nickname}</a>'

    message_text = f"💩 <b>{profile_link}</b> — король луж. собирай редкости в навозе и делай район чище. готов к экшну?"
    
    # Клавиатура для меню работы говночиста
    keyboard = [
        [KeyboardButton("начать чистку говна")],
        [KeyboardButton("назад"), KeyboardButton("статистика")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение
    message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/shit_work.jpg',
        reply_markup=reply_markup
    )

    # Сохраняем id сообщения говночиста
    if message:
        context.user_data['shit_cleaner_message_id'] = message.message_id
        context.user_data['shit_cleaner_chat_id'] = message.chat_id

# Начать чистку говна
async def start_shit_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:
        return
    
    # Генерируем случайное время от 30 секунд до 3 минут
    cleaning_time = random.randint(30, 180)
    context.user_data['cleaning_start_time'] = time.time()
    context.user_data['cleaning_duration'] = cleaning_time
    context.user_data['cleaning_remaining'] = cleaning_time
    context.user_data['is_cleaning'] = True
    context.user_data['cleaning_finished'] = False
    
    # Форматируем время и зарплату
    time_text = format_time(cleaning_time)
    salary = calculate_cleaning_salary(cleaning_time)
    
    message_text = f"🧹 ты начал чистить говно!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>\n\nиспользуй кнопки ниже для управления"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить чистку")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение о начале работы
    message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/cleaning_in_progress.jpg',
        reply_markup=reply_markup
    )
    
    # Сохраняем ID сообщения для обновления
    if message:
        context.user_data['cleaning_message_id'] = message.message_id
        context.user_data['cleaning_chat_id'] = message.chat_id
    
    # Запускаем асинхронную задачу для завершения работы
    asyncio.create_task(finish_cleaning_after_delay(update, context, cleaning_time))

# Асинхронная задача для завершения чистки
async def finish_cleaning_after_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, delay: int):
    await asyncio.sleep(delay)
    
    # Проверяем, что чистка еще активна
    if context.user_data.get('is_cleaning') and not context.user_data.get('cleaning_finished'):
        await finish_shit_cleaning(update, context)

# Обновить время по запросу пользователя
async def update_cleaning_time_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_cleaning'):
        await update.message.reply_text("❌ ты сейчас не чистишь говно!")
        return
    
    # Получаем текущее время и вычисляем оставшееся
    start_time = context.user_data.get('cleaning_start_time', 0)
    duration = context.user_data.get('cleaning_duration', 0)
    current_time = time.time()
    elapsed = current_time - start_time
    remaining = max(0, duration - elapsed)
    
    # Обновляем оставшееся время в контексте
    context.user_data['cleaning_remaining'] = remaining
    
    # Форматируем время и зарплату
    time_text = format_time(int(remaining))
    salary = calculate_cleaning_salary(duration)
    
    message_text = f"🧹 ты чистишь говно!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить чистку")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем новое сообщение с обновленным временем
    new_message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/cleaning_in_progress.jpg',
        reply_markup=reply_markup
    )
    
    # Сохраняем ID нового сообщения
    if new_message:
        context.user_data['cleaning_message_id'] = new_message.message_id
        context.user_data['cleaning_chat_id'] = new_message.chat_id

# Завершение чистки говна
async def finish_shit_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    # Проверяем, что чистка активна и не завершена
    if not context.user_data.get('is_cleaning') or context.user_data.get('cleaning_finished'):
        return
    
    # Помечаем чистку как завершенную
    context.user_data['cleaning_finished'] = True
    
    # Вычисляем зарплату
    duration = context.user_data.get('cleaning_duration', 0)
    salary = calculate_cleaning_salary(duration)
    
    # Применяем общий множитель заработка (Гангстер Плюс x4, Буст x2)
    from registration import get_user_earnings_multiplier
    multiplier = get_user_earnings_multiplier(user_id)
    salary = int(salary * multiplier)
    
    # Обновляем статистику
    update_user_stats(user_id, shit_cleaned=1, money_earned=salary)
    from registration import log_financial_transaction
    log_financial_transaction(user_id, "job_salary", salary, "зарплата: очистка говна")
    
    nickname = user[2]
    user_id_val = user[0]
    
    # Создаем ссылку на профиль
    profile_link = f'<a href="tg://user?id={user_id_val}">{nickname}</a>'
    
    # Форматируем время работы
    time_worked = format_time(duration)
    
    bonus_text = f" (бонус х{int(multiplier)})" if multiplier > 1.0 else ""
    
    message_text = f"✅ <b>{profile_link}</b>, ты успешно почистил говно!\n\n💰 заработано: <b>{format_money(salary)}</b>{bonus_text}\n⏰ время работы: <b>{time_worked}</b>\n💩 почищено говна: +1"
    
    # Клавиатура после завершения работы
    keyboard = [
        [KeyboardButton("начать чистку говна")],
        [KeyboardButton("назад"), KeyboardButton("статистика")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Удаляем предыдущее сообщение с прогрессом
    old_message_id = context.user_data.get('cleaning_message_id')
    old_chat_id = context.user_data.get('cleaning_chat_id')
    
    if old_message_id and old_chat_id:
        await safe_delete_message(context, old_chat_id, old_message_id)
    
    # Отправляем сообщение о завершении
    await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/shit_work.jpg',
        reply_markup=reply_markup
    )
    
    # Очищаем данные о чистке
    clear_cleaning_data(context.user_data)

# Отменить чистку
async def cancel_cleaning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_cleaning'):
        await update.message.reply_text("❌ ты сейчас не чистишь говно!")
        return
    
    # Удаляем предыдущее сообщение
    old_message_id = context.user_data.get('cleaning_message_id')
    old_chat_id = context.user_data.get('cleaning_chat_id')
    
    if old_message_id and old_chat_id:
        await safe_delete_message(context, old_chat_id, old_message_id)
    
    # Очищаем данные
    clear_cleaning_data(context.user_data)
    
    # Отправляем сообщение об отмене
    await update.message.reply_text("❌ чистка говна отменена!")
    
    # Показываем меню работы
    await show_shit_cleaner_menu(update, context)

# Функция для очистки данных о чистке
def clear_cleaning_data(user_data: dict):
    keys_to_remove = [
        'cleaning_start_time', 
        'cleaning_duration', 
        'cleaning_remaining',
        'cleaning_message_id',
        'cleaning_chat_id',
        'is_cleaning',
        'cleaning_finished'
    ]
    
    for key in keys_to_remove:
        if key in user_data:
            del user_data[key]

# Вспомогательные функции
def format_time(seconds: int) -> str:
    minutes = seconds // 60
    seconds_remaining = seconds % 60
    
    if minutes > 0:
        return f"{minutes} мин {seconds_remaining} сек"
    else:
        return f"{seconds_remaining} сек"

def calculate_cleaning_salary(duration: int) -> int:
    # Линейно от 7500 до 15000 в зависимости от времени (30-300 секунд)
    return min(7500 + (duration - 30) * 31, 15000)

# Функция для проверки находится ли пользователь в процессе чистки
def is_cleaning_in_progress(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    user_data = context.user_data
    return user_data.get('is_cleaning', False)