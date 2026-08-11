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

# Меню работы дояра
async def show_milker_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    message_text = f"🐄 <b>{profile_link}</b> — топ дояр. дои коров, собирай бонусы и прокачивай репу. поехали?"
    
    # Клавиатура для меню работы дояра
    keyboard = [
        [KeyboardButton("начать доение")],
        [KeyboardButton("назад"), KeyboardButton("статистика")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение
    message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/milker_work.jpg',
        reply_markup=reply_markup
    )

    # Сохраняем id сообщения дояра
    if message:
        context.user_data['milker_message_id'] = message.message_id
        context.user_data['milker_chat_id'] = message.chat_id

# Начать доение
async def start_milking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:
        return
    
    # Генерируем случайное время от 45 секунд до 4 минут
    milking_time = random.randint(45, 240)
    context.user_data['milking_start_time'] = time.time()
    context.user_data['milking_duration'] = milking_time
    context.user_data['milking_remaining'] = milking_time
    context.user_data['is_milking'] = True
    context.user_data['milking_finished'] = False
    
    # Форматируем время и зарплату
    time_text = format_time(milking_time)
    salary = calculate_milking_salary(milking_time)
    
    message_text = f"🐄 ты начал доить коров!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>\n\nиспользуй кнопки ниже для управления"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить доение")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение о начале работы
    message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='milking_in_progress.jpg',
        reply_markup=reply_markup
    )
    
    # Сохраняем ID сообщения для обновления
    if message:
        context.user_data['milking_message_id'] = message.message_id
        context.user_data['milking_chat_id'] = message.chat_id
    
    # Запускаем асинхронную задачу для завершения работы
    asyncio.create_task(finish_milking_after_delay(update, context, milking_time))

# Асинхронная задача для завершения доения
async def finish_milking_after_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, delay: int):
    await asyncio.sleep(delay)
    
    # Проверяем, что доение еще активна
    if context.user_data.get('is_milking') and not context.user_data.get('milking_finished'):
        await finish_milking(update, context)

# Обновить время доения по запросу пользователя
async def update_milking_time_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_milking'):
        await update.message.reply_text("❌ ты сейчас не доишь коров!")
        return
    
    # Получаем текущее время и вычисляем оставшееся
    start_time = context.user_data.get('milking_start_time', 0)
    duration = context.user_data.get('milking_duration', 0)
    current_time = time.time()
    elapsed = current_time - start_time
    remaining = max(0, duration - elapsed)
    
    # Обновляем оставшееся время в контексте
    context.user_data['milking_remaining'] = remaining
    
    # Форматируем время и зарплату
    time_text = format_time(int(remaining))
    salary = calculate_milking_salary(duration)
    
    message_text = f"🐄 ты доишь коров!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить доение")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем новое сообщение с обновленным временем
    new_message = await safe_send_message(
        update=update,
        text=message_text,
        photo_file='images/milking_in_progress.jpg',
        reply_markup=reply_markup
    )
    
    # Сохраняем ID нового сообщения
    if new_message:
        context.user_data['milking_message_id'] = new_message.message_id
        context.user_data['milking_chat_id'] = new_message.chat_id

# Завершение доения
async def finish_milking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    # Проверяем, что доение активна и не завершена
    if not context.user_data.get('is_milking') or context.user_data.get('milking_finished'):
        return
    
    # Помечаем доение как завершенную
    context.user_data['milking_finished'] = True
    
    # Вычисляем зарплату
    duration = context.user_data.get('milking_duration', 0)
    salary = calculate_milking_salary(duration)
    
    # Применяем общий множитель заработка (Гангстер Плюс x4, Буст x2)
    from registration import get_user_earnings_multiplier
    multiplier = get_user_earnings_multiplier(user_id)
    salary = int(salary * multiplier)
    
    # Обновляем статистику
    update_user_stats(user_id, milk_collected=1, money_earned=salary)
    from registration import log_financial_transaction
    log_financial_transaction(user_id, "job_salary", salary, "зарплата: доение коров")
    
    nickname = user[2]
    user_id_val = user[0]
    
    # Создаем ссылку на профиль
    profile_link = f'<a href="tg://user?id={user_id_val}">{nickname}</a>'
    
    # Форматируем время работы
    time_worked = format_time(duration)
    
    bonus_text = f" (бонус х{int(multiplier)})" if multiplier > 1.0 else ""
    
    message_text = f"✅ <b>{profile_link}</b>, ты успешно подоил коров!\n\n💰 заработано: <b>{format_money(salary)}</b>{bonus_text}\n⏰ время работы: <b>{time_worked}</b>\n🥛 надоено молока: +1"
    
    # Клавиатура после завершения работы
    keyboard = [
        [KeyboardButton("начать доение")],
        [KeyboardButton("назад"), KeyboardButton("статистика")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Удаляем предыдущее сообщение с прогрессом
    old_message_id = context.user_data.get('milking_message_id')
    old_chat_id = context.user_data.get('milking_chat_id')
    
    if old_message_id and old_chat_id:
        await safe_delete_message(context, old_chat_id, old_message_id)
    
    # Отправляем сообщение о завершении
    await safe_send_message(
        update=update,
        text=message_text,
        photo_file='milker_work.jpg',
        reply_markup=reply_markup
    )
    
    # Очищаем данные о доении
    clear_milking_data(context.user_data)

# Отменить доение
async def cancel_milking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_milking'):
        await update.message.reply_text("❌ ты сейчас не доишь коров!")
        return
    
    # Удаляем предыдущее сообщение
    old_message_id = context.user_data.get('milking_message_id')
    old_chat_id = context.user_data.get('milking_chat_id')
    
    if old_message_id and old_chat_id:
        await safe_delete_message(context, old_chat_id, old_message_id)
    
    # Очищаем данные
    clear_milking_data(context.user_data)
    
    # Отправляем сообщение об отмене
    await update.message.reply_text("❌ доение отменено!")
    
    # Показываем меню работы
    await show_milker_menu(update, context)

# Функция для очистки данных о доении
def clear_milking_data(user_data: dict):
    keys_to_remove = [
        'milking_start_time', 
        'milking_duration', 
        'milking_remaining',
        'milking_message_id',
        'milking_chat_id',
        'is_milking',
        'milking_finished'
    ]
    
    for key in keys_to_remove:
        if key in user_data:
            del user_data[key]

# Функция для расчета зарплаты дояра
def calculate_milking_salary(duration: int) -> int:
    # Линейно от 9000 до 18000 в зависимости от времени (60-300 секунд)
    return min(9000 + (duration - 60) * 38, 18000)

# Показать прогресс доения
async def show_milking_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('is_milking'):
        await update.message.reply_text("❌ ты сейчас не доишь коров!")
        return
    
    # Получаем текущее время и вычисляем оставшееся
    start_time = context.user_data.get('milking_start_time', 0)
    duration = context.user_data.get('milking_duration', 0)
    current_time = time.time()
    elapsed = current_time - start_time
    remaining = max(0, duration - elapsed)
    
    # Форматируем время
    time_text = format_time(int(remaining))
    salary = calculate_milking_salary(duration)
    
    # Текст для сообщения
    message_text = f"🐄 ты доишь коров!\n\n⏰ осталось времени: <b>{time_text}</b>\n💰 заработаешь: <b>{format_money(salary)}</b>"
    
    keyboard = [
        [KeyboardButton("обновить время"), KeyboardButton("отменить доение")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем новое сообщение с прогрессом
    await safe_send_message(
        update=update,
        text=message_text,
        photo_file='milking_in_progress.jpg',
        reply_markup=reply_markup
    )

# Вспомогательные функции
def format_time(seconds: int) -> str:
    minutes = seconds // 60
    seconds_remaining = seconds % 60
    
    if minutes > 0:
        return f"{minutes} мин {seconds_remaining} сек"
    else:
        return f"{seconds_remaining} сек"