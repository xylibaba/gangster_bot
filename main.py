import logging
import sys
import sqlite3
import asyncio
import time
import random
import os
from dotenv import load_dotenv
from casino import show_casino_menu, handle_casino_bet, show_slot_machine, show_blackjack, casino_back, show_bet_confirmation, play_slot_machine, play_blackjack, blackjack_hit, blackjack_stand, blackjack_double
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler

# загружаем переменные окружения из .env файла
load_dotenv()

# ПОЛНЫЕ ИСПРАВЛЕННЫЕ ИМПОРТЫ
from registration import (
    start, choose_gender, choose_color, choose_name, finish_registration,
    init_db, get_user, save_user, handle_all_text_messages, update_user_money,
    ban_user, unban_user, is_user_banned,
    get_user_by_username, get_user_by_name, temp_ban_user, get_ban_remaining_time,
    format_ban_time, is_main_admin, can_ban_user, log_admin_action, get_user_stats,
    update_user_stats, update_user_name, update_user_color, update_user_gender, is_nickname_valid,
    update_user_disable_transfer_confirmation, update_user_disable_transfer_notifications,
    update_user_disable_news_notifications, update_user_disable_system_notifications,
    get_user_activity_logs, is_admin
)
from utils import safe_delete_message
from utils import format_money

from main_menu import show_main_menu, show_work_menu, show_user_profile, refresh_main_menu, create_profile_text, create_admin_keyboard, show_settings, show_main_settings, show_color_selection, show_gender_selection, show_notifications_settings
from shit_cleaner import show_shit_cleaner_menu, start_shit_cleaning, update_cleaning_time_manual, cancel_cleaning, show_cleaning_progress, is_cleaning_in_progress
from milker import show_milker_menu, start_milking, cancel_milking, update_milking_time_manual, show_milking_progress
from scam import show_scam_menu, handle_referral_registration, add_referral_donation_earnings, add_referral_job_earnings, init_referral_stats, show_scam_instruction
from jobs import show_stats
from donations import (
    show_donation_menu, pre_checkout_handler,
    successful_payment_handler,
    handle_pack_navigation, handle_buy_pack_selection, start_pack_stars_payment, start_pack_crypto_payment,
    handle_back_to_packs
)
from accessories import (init_accessories_and_backgrounds, show_wardrobe_menu, show_accessories_shop, show_backgrounds_shop,
                         show_shop_main, handle_shop_accessories_start, handle_shop_backgrounds_start, handle_shop_menu,
                         handle_shop_acc_nav, handle_shop_bg_nav, handle_shop_buy_accessory, handle_shop_buy_background, 
                         handle_shop_toggle_accessory, handle_shop_toggle_background, clear_character_cache)
from admin_shop import show_admin_shop, handle_admin_shop_callback

# настройка логирования - отключаем все лишние логи
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# настраиваем только наши логи
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)

# создаем кастомный логгер для нашего бота без лишней информации
bot_logger = logging.getLogger('gangster_bot')
bot_logger.setLevel(logging.INFO)

# 🔐 загружаем конфиденциальные данные из .env файла
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", "0"))
MAX_MONEY_TRANSFER = int(os.getenv("MAX_MONEY_TRANSFER", "100000000000"))
MAX_ADMIN_MONEY_GIVE = int(os.getenv("MAX_ADMIN_MONEY_GIVE", "0"))

# проверяем, что необходимые переменные загружены
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

print("🚀 запуск бота...")

# класс для создания искусственного update с message
class FakeUpdate:
    def __init__(self, original_update, message):
        self.effective_user = original_update.effective_user
        self.message = message
        self.callback_query = original_update.callback_query

# система rate limiting
user_requests = {}

async def rate_limit_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_time = time.time()
    
    if user_id not in user_requests:
        user_requests[user_id] = []
    
    # удаляем старые запросы (последние 60 секунд)
    user_requests[user_id] = [t for t in user_requests[user_id] if current_time - t < 30]
    
    if len(user_requests[user_id]) >= 30:  # максимум 30 запросов в 30 секунд
        # ДОБАВЛЯЕМ СЛУЧАЙНОСТЬ: 10% шанс показать сообщение, чтобы не спамить
        if random.random() < 0.1:  # только в 10% случаев показываем сообщение
            await update.message.reply_text("❌ слишком много запросов! подождите.")
        return False
    
    user_requests[user_id].append(current_time)
    return True

# команда /help для обычных пользователей
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    help_text = """🤖 <b>помощь по боту гангстер</b>

<b>основные команды:</b>
/start - начать работу с ботом
/me - открыть главное меню
/help - показать эту справку

<b>игровые команды:</b>
"работа" - выбрать работу
"казино" - играть в казино (в разработке)
"магазин" - покупки (в разработке)
"дом" - ваш дом (в разработке)
"бизнес" - бизнес (в разработке)
"донат" - поддержать бота (в разработке)
"карта" - карта города (в разработке)
"статистика" - ваша статистика

<b>экономика:</b>
/pay @username сумма - перевести деньги другому игроку
"🔄" - обновить главное меню

<b>доступные работы:</b>
• 💩 говночист — лови лужи и собирай редкости
• 🐄 дояр — дои коров, собирай бонусы

<b>управление:</b>
"назад" - вернуться назад
"помощь" - показать справку
"настройки" - изменить ник и цвет персонажа

💡 <b>совет:</b> используй кнопки в меню для удобной навигации!"""

    # создаем клавиатуру
    keyboard = []
    
    # если пользователь админ, добавляем кнопку админ команд
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🔐 команды админов", callback_data="help_admin_commands")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

# команда /helpadm для админов
async def helpadm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    # проверяем админку - если не админ, перекидываем в главное меню без предупреждения
    if not is_admin(user_id):
        await show_main_menu(update, context)
        return
    
    helpadm_text = """🔐 <b>админские команды</b>

<b>управление пользователями:</b>
/profile @username - посмотреть профиль пользователя
/ban @username [причина] - забанить пользователя
/unban @username - разбанить пользователя

<b>управление админами:</b>
/add_admin @username - добавить админа (только главный админ)
/remove_admin @username - снять админа (только главный админ)

<b>админ магазин:</b>
/adminshop - открыть магазин администратора

<b>основные команды:</b>
/start - перезапустить бота
/me - главное меню
/help - помощь для пользователей
/helpadm - эта справка

⚠️ <b>внимание:</b> используй /adminshop для работы с админ валютой!"""

    await update.message.reply_text(helpadm_text, parse_mode='HTML')

# команда для открытия магазина администратора
async def adminshop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем adminку
    if not is_admin(user_id):
        await show_main_menu(update, context)
        return
    
    await show_admin_shop(update, context)

# обработчик команды /me
async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
        
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем чистку - если идет чистку, показываем прогресс вместо главного меню
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    await show_main_menu(update, context)

# команда для просмотра профиля пользователя
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    current_user = get_user(user_id)
    
    # если аргументов нет, показываем свой профиль
    if not context.args:
        await show_user_profile(update, context, current_user, is_admin_viewer=is_admin(user_id))
        return
    
    target_username = context.args[0].replace('@', '')
    
    # ищем пользователя в базе
    target_user = get_user_by_username(target_username)
    
    # если не нашли по username, пробуем найти по user_id
    if not target_user:
        try:
            target_user_id = int(target_username)
            target_user = get_user(target_user_id)
        except ValueError:
            pass
    
    # если все еще не нашли, ищем по имени
    if not target_user:
        target_user = get_user_by_name(target_username)
    
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
    
    # 🔒 защита: проверяем, не является ли целевой пользователь главным админом
    # Но если сам смотрящий админ, то просмотр разрешен (но огранич)
    is_target_main_admin = target_user[7] if len(target_user) > 7 else False
    is_viewer_admin = is_admin(user_id)
    
    if is_target_main_admin and not is_viewer_admin:
        await update.message.reply_text("❌ профиль главного админа виден только для администраторов!")
        return
    
    # логируем действие админа если это админ
    if is_viewer_admin:
        log_admin_action(user_id, "profile_view", target_user[0], f"просмотр профиля @{target_username}")
    
    # показываем профиль пользователя
    await show_user_profile(update, context, target_user, is_admin_viewer=is_viewer_admin)

# команда для просмотра профиля пользователя (админ)
async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        target_user = get_user(target_user_id)
        
        if not target_user:
            await query.answer("❌ пользователь не найден!", show_alert=True)
            return
        
        # 🔒 проверка прав на бан
        can_ban, reason = can_ban_user(user_id, target_user_id)
        if not can_ban:
            await query.answer(f"❌ {reason}", show_alert=True)
            return
        
        # баним на 24 часа
        temp_ban_user(target_user_id, 24 * 3600, user_id, "быстрый бан через админ-панель")
        
        # логируем действие админа
        log_admin_action(user_id, "ban", target_user_id, "быстрый бан на 24 часа")
        
        await query.answer("✅ пользователь забанен на 24 часа!")
        
        # Даем время на обработку бана перед обновлением
        await asyncio.sleep(0.5)
        await admin_refresh_profile(update, context, target_user_id)
        
    except Exception as e:
        await query.answer("❌ ошибка при бане пользователя!", show_alert=True)
        print(f"❌ ошибка в admin_ban_user: {e}")

# быстрый разбан
async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        unban_user(target_user_id)
        
        # логируем действие админа
        log_admin_action(user_id, "unban", target_user_id, "быстрый разбан")
        
        await query.answer("✅ пользователь разбанен!")
        
        # Даем время на обработку разбана перед обновлением
        await asyncio.sleep(0.5)
        await admin_refresh_profile(update, context, target_user_id)
        
    except Exception as e:
        await query.answer("❌ ошибка при разбане пользователя!", show_alert=True)
        print(f"❌ ошибка в admin_unban_user: {e}")

# быстрая выдача денег
# обновление профиля - ИСПРАВЛЕННАЯ ВЕРСИЯ
async def admin_refresh_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    
    try:
        target_user = get_user(target_user_id)
        
        if not target_user:
            await query.answer("❌ пользователь не найден!", show_alert=True)
            return
        
        # 🔒 БЕЗОПАСНЫЙ ДОСТУП К ДАННЫМ ПОЛЬЗОВАТЕЛЯ
        user_id = target_user[0] if len(target_user) > 0 else 0
        
        # Создаем текст профиля
        message_text = create_profile_text(target_user, is_viewer_admin=True)
        reply_markup = create_admin_keyboard(target_user_id, target_user)
        
        # Проверяем, что текст не пустой
        if not message_text or not message_text.strip():
            await query.answer("❌ ошибка при получении данных профиля!", show_alert=True)
            return
        
        # Пытаемся сначала отредактировать как фото (caption)
        try:
            await query.edit_message_caption(
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception as caption_error:
            # Если это не сообщение с фото, редактируем как текст
            try:
                await query.edit_message_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            except Exception as text_error:
                # Если не удается отредактировать, отправляем новое сообщение
                await query.message.reply_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        
        await query.answer("✅ профиль обновлен!")
        
    except Exception as e:
        print(f"❌ ошибка при обновлении профиля: {e}")
        await query.answer("❌ ошибка при обновлении профиля!", show_alert=True)

# показать логи активности пользователя 
async def show_user_activity_logs(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем права
    if not is_admin(user_id):
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
    
    nickname = target_user[2] if len(target_user) > 2 else "неизвестно"
    
    # Получаем логи активности
    logs = get_user_activity_logs(target_user_id, limit=15)
    
    if not logs:
        message_text = f"📋 <b>логи активности {nickname}</b>\n\n🔍 нет записей о активности"
    else:
        message_text = f"📋 <b>логи активности {nickname}</b>\n\n"
        for log in logs:
            from_id, to_id, amount, transfer_date = log
            
            # Определяем направление
            if from_id == target_user_id:
                sender = f"вы отправили"
                receiver_user = get_user(to_id) if to_id else None
                receiver_name = receiver_user[2] if receiver_user and len(receiver_user) > 2 else f"id{to_id}"
                message_text += f"💸 {sender} {format_money(amount)} пользователю {receiver_name}\n"
            else:
                sender_user = get_user(from_id) if from_id else None
                sender_name = sender_user[2] if sender_user and len(sender_user) > 2 else f"id{from_id}"
                message_text += f"💰 получили {format_money(amount)} от {sender_name}\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ назад", callback_data=f"admin_refresh_{target_user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_caption(caption=message_text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# показать аксессуары пользователя
async def show_user_accessories(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем права
    if not is_admin(user_id):
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
    
    nickname = target_user[2] if len(target_user) > 2 else "неизвестно"
    
    try:
        from accessories import get_user_equipped_names, get_user_background_name
        
        equipped = get_user_equipped_names(target_user_id)
        bg = get_user_background_name(target_user_id)
        
        message_text = f"👕 <b>аксессуары {nickname}</b>\n\n"
        message_text += f"<b>надетые предметы:</b>\n"
        for slot, item in equipped.items():
            if item:
                message_text += f"  {slot}: {item}\n"
            else:
                message_text += f"  {slot}: не выбран\n"
        
        if bg:
            message_text += f"\n<b>фон:</b> {bg}"
        else:
            message_text += f"\n<b>фон:</b> стандартный"
        
    except Exception as e:
        message_text = f"👕 <b>аксессуары {nickname}</b>\n\n🔍 не удалось загрузить информацию об аксессуарах"
    
    keyboard = [[InlineKeyboardButton("⬅️ назад", callback_data=f"admin_refresh_{target_user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_caption(caption=message_text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# переключение админки (ставить/снимать)
async def toggle_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем, главный ли админ 
    viewer = get_user(user_id)
    if not viewer or not viewer[7]:  # is_main_admin
        await query.answer("❌ только главный админ может менять статус!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user or target_user[7]:  # is_main_admin
        await query.answer("❌ нельзя менять статус главного админа!", show_alert=True)
        return
    
    # Переключаем статус
    is_admin = target_user[6]
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    if is_admin:
        # Снимаем админку
        cursor.execute('UPDATE users SET is_admin = FALSE WHERE user_id = ?', (target_user_id,))
        action = "снята"
    else:
        # Даем админку БЕЗ изменения баланса
        cursor.execute('UPDATE users SET is_admin = TRUE WHERE user_id = ?', (target_user_id,))
        action = "поставлена"
    
    conn.commit()
    conn.close()
    
    # Логируем действие
    log_admin_action(user_id, "admin_toggle", target_user_id, f"админка {action}")
    
    await query.answer(f"✅ админка {action}!")
    
    # Обновляем профиль
    updated_user = get_user(target_user_id)
    await admin_refresh_profile(update, context, target_user_id)

# выдача админ коинов
async def admin_give_coins_start(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем права
    if not is_admin(user_id):
        await query.answer("❌ только для админов!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
    
    # Проверяем что целевой пользователь админ atau главный админ
    is_target_admin = target_user[6] if len(target_user) > 6 else False
    is_target_main = target_user[7] if len(target_user) > 7 else False
    
    if not is_target_admin and not is_target_main:
        await query.answer("❌ можно выдать коины только админам!", show_alert=True)
        return
    
    nickname = target_user[2] if len(target_user) > 2 else "неизвестно"
    
    # Сохраняем ID целевого пользователя в контексте
    context.user_data['admin_giving_coins_to'] = target_user_id
    context.user_data['admin_giving_coins_from'] = user_id
    
    await query.answer()
    
    message_text = f"💎 <b>выдача админ коинов</b>\n\nполучатель: <b>{nickname}</b>\n\nсколько коинов выдать? (введи число)"
    
    # Пытаемся отредактировать сообщение (может быть либо с фото, либо текстовое)
    try:
        await query.edit_message_caption(caption=message_text, parse_mode='HTML')
    except:
        try:
            await query.edit_message_text(text=message_text, parse_mode='HTML')
        except:
            pass

# обработчик админских инлайн кнопок
async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        # 🔒 проверка бана для ВСЕХ кнопок без исключений
        if is_user_banned(user_id):
            await query.answer("❌ вы забанены и не можете использовать бота!", show_alert=True)
            return
        
        # проверяем, что пользователь админ
        if not is_admin(user_id):
            await query.answer("❌ у вас нет прав админа!", show_alert=True)
            return
        
        await query.answer()
        
        data = query.data
        
        # обработка бана
        if data.startswith('admin_ban_'):
            target_user_id = int(data.replace('admin_ban_', ''))
            await admin_ban_user(update, context, target_user_id)
        
        # обработка разбана
        elif data.startswith('admin_unban_'):
            target_user_id = int(data.replace('admin_unban_', ''))
            await admin_unban_user(update, context, target_user_id)
        
        # просмотр логов активности
        elif data.startswith('admin_view_logs_'):
            target_user_id = int(data.replace('admin_view_logs_', ''))
            await show_user_activity_logs(update, context, target_user_id)
        
        # просмотр аксессуаров
        elif data.startswith('admin_view_accessories_'):
            target_user_id = int(data.replace('admin_view_accessories_', ''))
            await show_user_accessories(update, context, target_user_id)
        
        # переключение админки
        elif data.startswith('admin_toggle_admin_'):
            target_user_id = int(data.replace('admin_toggle_admin_', ''))
            await toggle_admin_status(update, context, target_user_id)
        
        # обновление профиля
        elif data.startswith('admin_refresh_'):
            target_user_id = int(data.replace('admin_refresh_', ''))
            await admin_refresh_profile(update, context, target_user_id)
        
        # выдача админ коинов
        elif data.startswith('admin_give_coins_'):
            target_user_id = int(data.replace('admin_give_coins_', ''))
            await admin_give_coins_start(update, context, target_user_id)
        
        else:
            await query.answer("❌ неизвестная команда!", show_alert=True)
            
    except ValueError as e:
        await query.answer("❌ ошибка в данных!", show_alert=True)
        print(f"❌ ошибка в handle_admin_actions: {e}")
    except Exception as e:
        await query.answer("❌ произошла ошибка!", show_alert=True)
        print(f"❌ непредвиденная ошибка в handle_admin_actions: {e}")

# функция для немедленного выполнения перевода (без подтверждения)
async def confirm_transfer_immediate(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user, amount):
    user_id = update.effective_user.id

    # получаем актуальные данные отправителя
    from_user = get_user(user_id)
    if not from_user:
        await update.message.reply_text("❌ ошибка: пользователь не найден!")
        return

    # выполняем перевод в одной транзакции
    try:
        # создаем одно соединение для всей операции
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()

        # начинаем транзакцию
        cursor.execute('BEGIN TRANSACTION')

        # 🔒 атомарно снимаем деньги у отправителя
        cursor.execute('UPDATE users SET money = money - ? WHERE user_id = ? AND money >= ?',
                      (amount, user_id, amount))

        if cursor.rowcount == 0:
            await update.message.reply_text("❌ недостаточно средств для перевода!")
            conn.rollback()
            return

        # атомарно добавляем деньги получателю
        cursor.execute('UPDATE users SET money = money + ? WHERE user_id = ?', (amount, target_user[0]))

        # логируем перевод
        cursor.execute('''
            INSERT INTO money_transfers (from_user_id, to_user_id, amount)
            VALUES (?, ?, ?)
        ''', (user_id, target_user[0], amount))

        # коммитим транзакцию
        conn.commit()

        # форматируем суммы
        formatted_amount = format_money(amount)

        # создаем скрытые ссылки на telegram профили
        from_user_link = f'<a href="https://t.me/{from_user[1]}"><b>{from_user[2]}</b></a>' if from_user[1] else f'<b>{from_user[2]}</b>'
        to_user_link = f'<a href="https://t.me/{target_user[1]}"><b>{target_user[2]}</b></a>' if target_user[1] else f'<b>{target_user[2]}</b>'

        # сообщение для отправителя
        sender_message = (
            f"✅ перевод выполнен!\n\n"
            f"💸 переведено: {formatted_amount}\n"
            f"👤 получатель: {to_user_link}"
        )

        # сообщение для получателя
        receiver_message = (
            f"💸 <b>поступление средств!</b>\n\n"
            f"💰 получено: {formatted_amount}\n"
            f"👤 отправитель: {from_user_link}"
        )

        # отправляем сообщение отправителю
        await update.message.reply_text(sender_message, parse_mode='HTML')

        # отправляем уведомление получателю
        try:
            await context.bot.send_message(
                chat_id=target_user[0],
                text=receiver_message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"❌ не удалось отправить уведомление получателю: {e}")

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await update.message.reply_text("❌ база данных временно заблокирована, попробуйте позже!")
        else:
            await update.message.reply_text("❌ ошибка при выполнении перевода!")
        print(f"ошибка базы данных при переводе: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
            pass
    finally:
        try:
            conn.close()
        except:
            pass

# функция для подтверждения перевода денег
async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if 'pending_transfer' not in context.user_data:
        await query.answer("❌ нет ожидающего перевода!")
        return

    transfer_data = context.user_data['pending_transfer']
    target_user = transfer_data['target_user']
    amount = transfer_data['amount']

    # получаем актуальные данные отправителя
    from_user = get_user(user_id)
    if not from_user:
        await query.answer("❌ ошибка: пользователь не найден!")
        del context.user_data['pending_transfer']
        return

    # выполняем перевод в одной транзакции
    try:
        # создаем одно соединение для всей операции
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False, timeout=30)
        cursor = conn.cursor()

        # начинаем транзакцию
        cursor.execute('BEGIN TRANSACTION')

        # 🔒 атомарно снимаем деньги у отправителя
        cursor.execute('UPDATE users SET money = money - ? WHERE user_id = ? AND money >= ?',
                      (amount, user_id, amount))

        if cursor.rowcount == 0:
            await query.answer("❌ недостаточно средств для перевода!")
            conn.rollback()
            del context.user_data['pending_transfer']
            return

        # атомарно добавляем деньги получателю
        cursor.execute('UPDATE users SET money = money + ? WHERE user_id = ?', (amount, target_user[0]))

        # логируем перевод
        cursor.execute('''
            INSERT INTO money_transfers (from_user_id, to_user_id, amount)
            VALUES (?, ?, ?)
        ''', (user_id, target_user[0], amount))

        # коммитим транзакцию
        conn.commit()

        # форматируем суммы
        formatted_amount = format_money(amount)

        # создаем скрытые ссылки на telegram профили
        from_user_link = f'<a href="https://t.me/{from_user[1]}"><b>{from_user[2]}</b></a>' if from_user[1] else f'<b>{from_user[2]}</b>'
        to_user_link = f'<a href="https://t.me/{target_user[1]}"><b>{target_user[2]}</b></a>' if target_user[1] else f'<b>{target_user[2]}</b>'

        # сообщение для отправителя
        sender_message = (
            f"✅ перевод выполнен!\n\n"
            f"💸 переведено: {formatted_amount}\n"
            f"👤 получатель: {to_user_link}"
        )

        # сообщение для получателя
        receiver_message = (
            f"💸 <b>поступление средств!</b>\n\n"
            f"💰 получено: {formatted_amount}\n"
            f"👤 отправитель: {from_user_link}"
        )

        # отправляем сообщение отправителю
        await query.message.edit_text(sender_message, parse_mode='HTML')

        # отправляем уведомление получателю
        try:
            await context.bot.send_message(
                chat_id=target_user[0],
                text=receiver_message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"❌ не удалось отправить уведомление получателю: {e}")

        # очищаем данные перевода
        del context.user_data['pending_transfer']

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            await query.answer("❌ база данных временно заблокирована, попробуйте позже!")
        else:
            await query.answer("❌ ошибка при выполнении перевода!")
        print(f"ошибка базы данных при переводе: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        del context.user_data['pending_transfer']
    except Exception as e:
        await query.answer("❌ ошибка при выполнении перевода!")
        print(f"ошибка перевода: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        del context.user_data['pending_transfer']
    finally:
        try:
            conn.close()
        except Exception:
            pass
async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    # получаем данные отправителя до обработки суммы
    from_user = get_user(user_id)
    if not from_user:
        await update.message.reply_text("❌ вы не зарегистрированы!")
        return

    from_user_balance = from_user[5]
    
    # проверяем аргументы
    if len(context.args) < 2:
        await update.message.reply_text("❌ использование: /pay @username сумма")
        return
    
    target_username = context.args[0].replace('@', '')
    
    try:
        amount_str = context.args[1].lower().replace(',', '.').replace(' ', '')
        
          # если ввели "все" - переводим весь баланс
        if amount_str == 'все':
            amount = from_user_balance
        else:
            # обрабатываем сокращения
            if 'ккккк' in amount_str:
                amount = int(float(amount_str.replace('ккккк', '')) * 10000000000000)
            elif 'кккк' in amount_str:
                amount = int(float(amount_str.replace('кккк', '')) * 1000000000000)
            elif 'ккк' in amount_str:
                amount = int(float(amount_str.replace('ккк', '')) * 1000000000)
            elif 'кк' in amount_str:
                amount = int(float(amount_str.replace('кк', '')) * 1000000)
            elif 'к' in amount_str:
                amount = int(float(amount_str.replace('к', '')) * 1000)
            else:
                amount = int(float(amount_str))
            
    except ValueError:
        await update.message.reply_text("❌ неверный формат суммы! используйте: 1000, 1к, 1.5к, 1кк, 1ккк, 1кккк, 1ккккк или 'все'")
        return
    
    if amount <= 0:
        await update.message.reply_text("❌ сумма перевода должна быть больше нуля!")
        return
    
    # ищем получателя
    target_user = None
    
    # ищем по username
    target_user = get_user_by_username(target_username)
    
    # если не нашли по username, пробуем найти по user_id
    if not target_user:
        try:
            target_user_id = int(target_username)
            target_user = get_user(target_user_id)
        except ValueError:
            pass
    
    # если все еще не нашли, ищем по имени
    if not target_user:
        target_user = get_user_by_name(target_username)
    
    if not target_user:
        await update.message.reply_text("❌ получатель не найден! проверьте username, id или имя.")
        return
    
    # проверяем, что не переводим самому себе
    if target_user[0] == user_id:
        await update.message.reply_text("❌ нельзя переводить деньги самому себе!")
        return

    # проверяем настройку отключения подтверждения
    disable_confirmation = from_user[14] if len(from_user) > 14 else False
    if disable_confirmation:
        # выполняем перевод сразу без подтверждения
        await confirm_transfer_immediate(update, context, target_user, amount)
        return

    # сохраняем данные для подтверждения
    context.user_data['pending_transfer'] = {
        'target_user': target_user,
        'amount': amount,
        'formatted_amount': format_money(amount)
    }

    # создаем скрытые ссылки на telegram профили
    from_user_link = f'<a href="https://t.me/{from_user[1]}"><b>{from_user[2]}</b></a>' if from_user[1] else f'<b>{from_user[2]}</b>'
    to_user_link = f'<a href="https://t.me/{target_user[1]}"><b>{target_user[2]}</b></a>' if target_user[1] else f'<b>{target_user[2]}</b>'

    # сообщение подтверждения
    confirm_message = (
        f"💸 <b>подтверждение перевода</b>\n\n"
        f"👤 получатель: {to_user_link}\n"
        f"💰 сумма: {format_money(amount)}\n"
        f"💳 ваш баланс после: {format_money(from_user_balance - amount)}\n\n"
        f"подтвердить перевод?"
    )

    # клавиатура подтверждения
    keyboard = [
        [InlineKeyboardButton("✅ подтвердить", callback_data="transfer_confirm")],
        [InlineKeyboardButton("❌ отменить", callback_data="transfer_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(confirm_message, reply_markup=reply_markup, parse_mode='HTML')

# команда для бана пользователя с причиной (админ)
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    # проверяем админку
    if not is_admin(user_id):
        await show_main_menu(update, context)
        return
    
    # проверяем аргументы
    if len(context.args) < 1:
        await update.message.reply_text("❌ использование: /ban @username [причина]")
        return
    
    target_username = context.args[0].replace('@', '')
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "причина не указана"
    
    # ищем пользователя в базе
    target_user = get_user_by_username(target_username)
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
    
    # 🔒 проверка прав на бан
    can_ban, ban_reason = can_ban_user(user_id, target_user[0])
    if not can_ban:
        await update.message.reply_text(f"❌ {ban_reason}")
        return
    
    # баним пользователя
    ban_user(target_user[0])
    
    # логируем действие админа
    log_admin_action(user_id, "ban", target_user[0], f"причина: {reason}")
    
    # отправляем уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=target_user[0],
            text=f"🚫 <b>вы были забанены!</b>\n\n📝 <b>причина:</b> {reason}",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ не удалось отправить уведомление пользователю: {e}")
    
    await update.message.reply_text(f"✅ пользователь @{target_username} забанен!\n📝 причина: {reason}")

# команда для разбана пользователя (админ)
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    # проверяем админку
    if not is_admin(user_id):
        await show_main_menu(update, context)
        return
    
    # проверяем аргументы
    if not context.args:
        await update.message.reply_text("❌ использование: /unban @username")
        return
    
    target_username = context.args[0].replace('@', '')
    
    # ищем пользователя в базе
    target_user = get_user_by_username(target_username)
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
    
    # разбаниваем пользователя
    unban_user(target_user[0])
    
    # логируем действие админа
    log_admin_action(user_id, "unban", target_user[0])
    
    # отправляем уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=target_user[0],
            text="✅ <b>вас разбанили!</b>\n\nтеперь вы снова можете использовать бота.",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ не удалось отправить уведомление пользователю: {e}")
    
    await update.message.reply_text(f"✅ пользователь @{target_username} разбанен!")

# команда для добавления админа (только главный админ)
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    user = get_user(user_id)
    
    # если пользователь не главный админ
    if not user or not user[7]:  # is_main_admin
        if is_admin(user_id):  # если обычный админ
            await update.message.reply_text("❌ эта команда недоступна!")
        # для всех остальных - просто перебрасываем в главное меню
        await show_main_menu(update, context)
        return
    
    # проверяем аргументы
    if not context.args:
        await update.message.reply_text("❌ использование: /add_admin @username")
        return
    
    target_username = context.args[0].replace('@', '')
    
    # ищем пользователя в базе
    target_user = get_user_by_username(target_username)
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
    
    # проверяем, не является ли пользователь уже админом
    if target_user[6]:  # is_admin
        await update.message.reply_text(f"❌ пользователь @{target_username} уже является админом!")
        return
    
    # делаем пользователя админом
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = TRUE WHERE user_id = ?', (target_user[0],))
    conn.commit()
    conn.close()
    
    # логируем действие админа
    log_admin_action(user_id, "add_admin", target_user[0])
    
    # отправляем уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=target_user[0],
            text="🔺 <b>вам выдали админку!</b>\n\nтеперь у вас есть доступ к админским командам.",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ не удалось отправить уведомление пользователю: {e}")
    
    await update.message.reply_text(f"✅ пользователь @{target_username} теперь админ!")

# команда для снятия админки (только главный админ)
async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    user = get_user(user_id)
    
    # если пользователь не главный админ
    if not user or not user[7]:  # is_main_admin
        if is_admin(user_id):  # если обычный админ
            await update.message.reply_text("❌ эта команда недоступна!")
        # для всех остальных - просто перебрасываем в главное меню
        await show_main_menu(update, context)
        return
    
    # проверяем аргументы
    if not context.args:
        await update.message.reply_text("❌ использование: /remove_admin @username")
        return
    
    target_username = context.args[0].replace('@', '')
    
    # ищем пользователя в базе
    target_user = get_user_by_username(target_username)
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
    
    # проверяем, является ли пользователь админом
    if not target_user[6]:  # is_admin
        await update.message.reply_text(f"❌ пользователь @{target_username} не является админом!")
        return
    
    # проверяем, что не снимаем админку с главного админа
    if target_user[7]:  # is_main_admin
        await update.message.reply_text("❌ нельзя снять админку с главного админа!")
        return
    
    # снимаем админку
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_admin = FALSE WHERE user_id = ?', (target_user[0],))
    conn.commit()
    conn.close()
    
    # логируем действие админа
    log_admin_action(user_id, "remove_admin", target_user[0])
    
    # отправляем уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=target_user[0],
            text="🔻 <b>с вас сняли админку!</b>\n\nтеперь вы обычный пользователь.",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"❌ не удалось отправить уведомление пользователю: {e}")
    
    await update.message.reply_text(f"✅ у пользователя @{target_username} снята админка!")

# обработчик неизвестных команд
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await show_cleaning_progress(update, context)
        return
    
    # отправляем сообщение с неизвестной командой и сразу показываем главное меню
    await update.message.reply_text("❌ неизвестная команда!")
    await show_main_menu(update, context)

# обработчик всех текстовых сообщений
async def invalidate_user_inline_buttons(context, user_id):
    """Удаляет inline-кнопки у сохранённых пользователем сообщений и помечает их как неактивные.
    Возвращает количество обработанных сообщений.
    """
    keys_pairs = [
        ('casino_header_message_id', 'casino_header_chat_id'),
        ('casino_games_message_id', 'casino_games_chat_id'),
        ('work_header_message_id', 'work_header_chat_id'),
        ('work_menu_message_id', 'work_menu_chat_id'),
        ('shit_cleaner_message_id', 'shit_cleaner_chat_id'),
        ('milker_message_id', 'milker_chat_id'),
        ('stats_message_id', 'stats_chat_id')
    ]

    invalidated = 0
    for msg_key, chat_key in keys_pairs:
        # если пользователь уже выбрал работу - не инвалидируем сообщения меню работы
        if msg_key in ('work_header_message_id', 'work_menu_message_id') and context.user_data.get('selected_job'):
            continue

        if msg_key in context.user_data and chat_key in context.user_data:
            try:
                chat_id = context.user_data[chat_key]
                message_id = context.user_data[msg_key]
                # Попытка убрать inline-кнопки, но не удалять само сообщение
                try:
                    await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                except Exception:
                    pass

                # помечаем сообщение как неактивное (нужно для обработки callback-ов из кэша клиента)
                inactive_list = context.user_data.get('inactive_messages', [])
                if not isinstance(inactive_list, list):
                    inactive_list = []
                if message_id not in inactive_list:
                    inactive_list.append(message_id)
                context.user_data['inactive_messages'] = inactive_list

                # УДАЛЯЕМ СТАРЫЕ КЛЮЧИ ИЗ КОНТЕКСТА, ЧТО БЫ ОНИ НЕ СЧИТАЛИСЬ АКТИВНЫМИ
                if msg_key in context.user_data:
                    del context.user_data[msg_key]
                if chat_key in context.user_data:
                    del context.user_data[chat_key]

                invalidated += 1
            except Exception:
                pass

    return invalidated

# обработчик всех текстовых сообщений
async def handle_all_text_messages_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    # ПРОВЕРКА СТАВОК КАЗИНО ПЕРВОЙ (если ожидается ставка)
    if 'waiting_for_bet' in context.user_data:
        await handle_casino_bet(update, context)
        return
    
    # проверяем чистку - если идет чистка, показываем прогресс
    if is_cleaning_in_progress(context, user_id):
        # если это кнопки управления чисткой - обрабатываем их
        text = update.message.text.strip().lower()
        
        if text == "обновить время":
            await update_cleaning_time_manual(update, context)
            return
        elif text == "отменить чистку":
            await cancel_cleaning(update, context)
            return
        else:
            # для всех остальных команд показываем прогресс чистки
            await show_cleaning_progress(update, context)
            return
    
    # проверяем доение - если идет доение, показываем прогресс
    if context.user_data.get('is_milking'):
        text = update.message.text.strip()
        
        if text == "обновить время":
            await update_milking_time_manual(update, context)
            return
        elif text == "отменить доение":
            await cancel_milking(update, context)
            return
        else:
            # для всех остальных команд показываем прогресс доения
            await show_milking_progress(update, context)
            return
    
    # обработка смены ника админом
    if 'admin_changing_name_for' in context.user_data:
        target_user_id = context.user_data['admin_changing_name_for']
        new_name = update.message.text.strip()

        # валидация имени
        is_valid, error_message = is_nickname_valid(new_name)

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}")
            return

        # обновляем имя в базе
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET name = ? WHERE user_id = ?', (new_name, target_user_id))
        conn.commit()
        conn.close()

        # очищаем контекст
        del context.user_data['admin_changing_name_for']

        # удаляем сообщение с запросом имени
        try:
            await update.message.delete()
        except:
            pass

        await update.message.reply_text(f"✅ ник успешно изменен на: <b>{new_name}</b>", parse_mode='HTML')

        # показываем обновленный профиль
        target_user = get_user(target_user_id)
        if target_user:
            await show_user_profile(update, context, target_user)
        return

    # обработка смены ника пользователем
    if 'changing_name' in context.user_data:
        new_name = update.message.text.strip()

        # валидация имени
        is_valid, error_message = is_nickname_valid(new_name)

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}")
            return

        # обновляем имя
        update_user_name(user_id, new_name)

        # очищаем контекст
        del context.user_data['changing_name']

        # удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass

        await update.message.reply_text(f"✅ ваш ник успешно изменен на: <b>{new_name}</b>", parse_mode='HTML')

        # показываем настройки
        await show_settings(update, context)
        return
    
    # проверяем, находится ли пользователь в процессе регистрации (ввод имени)
    if 'gender' in context.user_data and 'color' in context.user_data:
        # если пользователь в процессе ввода имени - пропускаем обработку в main.py
        # и передаем управление в registration.py
        from registration import handle_all_text_messages
        await handle_all_text_messages(update, context, MAIN_ADMIN_ID)
        return
    
    # проверяем регистрацию пользователя
    user = get_user(user_id)
    if not user or not user[8]:  # если не зарегистрирован - отправляем на регистрацию
        await start(update, context, MAIN_ADMIN_ID)
        return
    
    # обработка выдачи админ коинов
    if 'admin_giving_coins_to' in context.user_data:
        target_user_id = context.user_data['admin_giving_coins_to']
        
        try:
            amount = int(update.message.text.strip())
            
            if amount <= 0:
                await update.message.reply_text("❌ количество коинов должно быть больше нуля!")
                return
            
            # Даём коины
            from registration import update_admin_currency
            new_balance = update_admin_currency(target_user_id, amount)
            
            if new_balance is None:
                await update.message.reply_text(f"❌ ошибка при выдаче коинов! проверьте логи.")
                return
            
            target_user = get_user(target_user_id)
            nickname = target_user[2] if target_user and len(target_user) > 2 else "неизвестно"
            
            # Логируем действие
            log_admin_action(user_id, "give_coins", target_user_id, f"выдано {amount} админ коинов")
            
            # Удаляем из контекста
            del context.user_data['admin_giving_coins_to']
            if 'admin_giving_coins_from' in context.user_data:
                del context.user_data['admin_giving_coins_from']
            
            # Отправляем сообщение об успехе админу
            admin_name = update.effective_user.username or "админ"
            await update.message.reply_text(f"✅ {nickname} получил {amount} админ коинов!", parse_mode='HTML')
            
            # Отправляем уведомление целевому пользователю
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                
                notification = f"💎 <b>вы получили админ коины!</b>\n\nполучено: <b>{amount}</b> коинов\n"
                if new_balance is not None:
                    notification += f"новый баланс: <b>{new_balance}</b> коинов"
                notification += f"\n\nотправитель: <b>{admin_name}</b> (@{admin_name})"
                
                keyboard = [
                    [InlineKeyboardButton("🛍️ перейти в магазин", callback_data="admin_shop")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=notification,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"⚠️ не удалось отправить уведомление пользователю {target_user_id}: {e}")
            
            # Возвращаемся в главное меню
            await show_main_menu(update, context)
            return
        except ValueError:
            await update.message.reply_text("❌ введите корректное число!")
            return
    
    text = update.message.text.strip().lower()
    first_word = text.split()[0] if text.split() else text

    handled = False

    # обработка кнопок главного меню
    if text == "работа":
        handled = True
        await show_work_menu(update, context)
        return
    # обработка текстовых команд профиля
    elif first_word in ["профиль", "посмотреть", "глянуть"]:
        # получаем юзера (если есть аргумент после команды)
        message_parts = update.message.text.split(maxsplit=1)
        if len(message_parts) > 1:
            # есть аргумент - парсим его
            target_username = message_parts[1].replace('@', '')
            target_user = get_user_by_username(target_username)
            
            if not target_user:
                try:
                    target_user_id = int(target_username)
                    target_user = get_user(target_user_id)
                except ValueError:
                    target_user = get_user_by_name(target_username)
            
            if not target_user:
                await update.message.reply_text("❌ пользователь не найден!")
                return
        else:
            # нет аргумента - показываем свой профиль
            target_user = get_user(user_id)
        
        # 🔒 защита: проверяем, не является ли целевой пользователь главным админом
        is_target_main_admin = target_user[7] if len(target_user) > 7 else False
        is_viewer_admin = is_admin(user_id)
        
        if is_target_main_admin and not is_viewer_admin:
            await update.message.reply_text("❌ профиль главного админа виден только для администраторов!")
            return
        
        # логируем действие админа если это админ
        if is_viewer_admin and target_user[0] != user_id:
            log_admin_action(user_id, "profile_view", target_user[0], f"просмотр профиля {target_user[2]}")
        
        # показываем профиль пользователя
        await show_user_profile(update, context, target_user, is_admin_viewer=is_viewer_admin)
        return
    elif text == "назад":
        handled = True
        
        # если пользователь в магазине аксессуаров - вернуться в меню магазина
        if context.user_data.get('in_accessories_shop'):
            context.user_data['in_accessories_shop'] = False
            await show_shop_main(update, context)
            return
        
        # проверяем, если пользователь был на инструкции скама - вернуться в скам меню
        if 'scam_instruction_message_id' in context.user_data:
            if 'scam_instruction_message_id' in context.user_data:
                del context.user_data['scam_instruction_message_id']
            if 'scam_instruction_chat_id' in context.user_data:
                del context.user_data['scam_instruction_chat_id']
            
            # возвращаемся в меню скама
            from scam import show_scam_menu
            fake_update = FakeUpdate(update, update.message)
            await show_scam_menu(fake_update, context)
            return
        
        # если пользователь выбрал одну из работ (говночист, дояр, скам) - вернуться в меню работ
        if context.user_data.get('selected_job'):
            del context.user_data['selected_job']
            await show_work_menu(update, context)
            return
        
        # очищаем список неактивных сообщений при возврате в главное меню
        if 'inactive_messages' in context.user_data:
            del context.user_data['inactive_messages']
        await show_main_menu(update, context)
        return
    elif text == "🔄":  # обработка кнопки обновления
        handled = True
        await refresh_main_menu(update, context)
        return
    elif text == "казино":
        handled = True
        await show_casino_menu(update, context)
        return
    elif text == "магазин":
        handled = True
        await show_shop_main(update, context)
        return
    elif text == "👕 магазин аксессуаров":
        handled = True
        context.user_data['current_accessory_index'] = 0
        context.user_data['in_accessories_shop'] = True
        from accessories import _show_accessory_carousel
        await _show_accessory_carousel(update, context)
        return
    elif text == "🎨 магазин фонов":
        handled = True
        await update.message.reply_text("😔 фоны временно недоступны")
        await show_shop_main(update, context)
        return
    elif text == "💎 админ магазин":
        handled = True
        # Проверяем что пользователь админ
        if is_admin(user_id):
            from admin_shop import show_admin_shop
            await show_admin_shop(update, context)
        else:
            await update.message.reply_text("❌ это только для администраторов!")
            await show_shop_main(update, context)
        return
    elif text == "назад" and context.user_data.get('in_accessories_shop'):
        handled = True
        context.user_data['in_accessories_shop'] = False
        await show_shop_main(update, context)
        return
    elif text == "дом":
        handled = True
        await update.message.reply_text("🏠 дом в разработке")
        return
    elif text == "бизнес":
        handled = True
        await update.message.reply_text("💼 бизнес в разработке")
        return
    elif text == "донат":
        handled = True
        await show_donation_menu(update, context)
        return
    elif text == "карта":
        handled = True
        await update.message.reply_text("🗺️ карта в разработке")
        return
    elif text == "помощь":  # обработка текстовой команды помощи
        handled = True
        await help_command(update, context)
        return
    elif text == "⚙️":
        handled = True
        await show_settings(update, context)
        return
    elif text == "настройки":
        handled = True
        await show_settings(update, context)
        return

    # обработка кнопок меню настроек
    elif text == "основные" and context.user_data.get('in_settings'):
        handled = True
        await show_main_settings(update, context)
        return
    elif text == "⬅️ назад" and context.user_data.get('in_main_settings'):
        handled = True
        # очищаем состояние основных настроек
        if 'in_main_settings' in context.user_data:
            del context.user_data['in_main_settings']
        await show_settings(update, context)
        return
    elif text == "⬅️ назад" and context.user_data.get('in_settings'):
        handled = True
        # очищаем состояние настроек
        if 'in_settings' in context.user_data:
            del context.user_data['in_settings']
        await show_main_menu(update, context)
        return

    # обработка кнопок меню говночиста (без эмодзи)
    elif text == "начать чистку говна":
        handled = True
        await start_shit_cleaning(update, context)
        return
    elif text == "статистика":
        handled = True
        await show_stats(update, context)
        return
    elif text.lower() == "я":
        handled = True
        await show_main_menu(update, context)
        return

    # обработка кнопок меню дояра (без эмодзи)
    elif text == "начать доение":
        handled = True
        await start_milking(update, context)
        return

    # обработка кнопок меню скама (без эмодзи)
    elif text == "инструкция":
        handled = True
        await show_scam_instruction(update, context)
        return

    # обработка кнопок управления чисткой (без эмодзи)
    elif text == "обновить время":
        handled = True
        await update_cleaning_time_manual(update, context)
        return
    elif text == "отменить чистку":
        handled = True
        await cancel_cleaning(update, context)
        return

    # обработка кнопок управления доением (без эмодзи)
    elif text == "отменить доение":
        handled = True
        await cancel_milking(update, context)
        return

    # если сообщение не обработано, показываем неизвестную команду
    if not handled:
        # если были активные сообщения с inline-кнопками (например, меню работы),
        # делаем их кнопки неактивными и уведомляем пользователя
        try:
            invalidated = await invalidate_user_inline_buttons(context, user_id)
        except Exception:
            invalidated = 0

        if invalidated > 0:
            await update.message.reply_text("⚠️ кнопки в предыдущих сообщениях теперь неактивны.")
            await show_main_menu(update, context)
            return

        await update.message.reply_text("❌ неизвестная команда! напишите /help для списка команд")
        await show_main_menu(update, context)

# обработка нажатий кнопок регистрации, работы и админских действий
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # ===== ПРОВЕРКА НЕАКТИВНОСТИ В САМОМ НАЧАЛЕ =====
    try:
        inactive_list = context.user_data.get('inactive_messages', [])
        msg = query.message
        
        if msg is not None and isinstance(inactive_list, list):
            # Если сообщение помечено неактивным — ОТКЛОНЯЕМ И ВЫХОДИМ
            if msg.message_id in inactive_list:
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
    except Exception:
        pass
    
    # ===== ДАЛЬШЕ ИДЕТ ОСНОВНАЯ ОБРАБОТКА =====
    try:
        # 🔒 проверка бана первым делом для ВСЕХ кнопок
        if is_user_banned(user_id):
            await query.answer("❌ вы забанены и не можете использовать бота!", show_alert=True)
            return
        
        await query.answer()
        
        # проверяем чистку - если идет чистка, показываем прогресс
        if is_cleaning_in_progress(context, user_id):
            await show_cleaning_progress(update, context)
            return
        
        data = query.data
        
        # обработка команд помощи
        if data == "help_admin_commands":
            # редактируем сообщение с админскими командами
            helpadm_text = """🔐 <b>админские команды</b>

<b>управление пользователями:</b>
/profile @username - посмотреть профиль пользователя
/ban @username [причина] - забанить пользователя
/unban @username - разбанить пользователя

<b>управление экономикой:</b>
/money @username сумма - выдать/снять деньги
• поддерживаются сокращения: к, кк, ккк, кккк, ккккк
• примеры: 1000, 1к, 1.5к, 1кк, 1ккк

<b>управление админами:</b>
/add_admin @username - добавить админа (только главный админ)
/remove_admin @username - снять админа (только главный админ)

<b>основные команды:</b>
/start - перезапустить бота
/me - главное меню
/help - помощь для пользователей
/helpadm - полная справка по админам

⚠️ <b>внимание:</b> будьте осторожны с выдачей денег и баном пользователей!"""
            
            keyboard = [
                [InlineKeyboardButton("⬅️ назад", callback_data="help_back_to_user")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                try:
                    await query.edit_message_caption(
                        caption=helpadm_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except:
                    await query.edit_message_text(
                        text=helpadm_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                print(f"❌ ошибка при редактировании сообщения: {e}")
            return
        
        elif data == "help_back_to_user":
            # редактируем сообщение обратно на обычную помощь
            help_text = """🤖 <b>помощь по боту гангстер</b>

<b>основные команды:</b>
/start - начать работу с ботом
/me - открыть главное меню
/help - показать эту справку

<b>игровые команды:</b>
"работа" - выбрать работу
"казино" - играть в казино (в разработке)
"магазин" - покупки (в разработке)
"дом" - ваш дом (в разработке)
"бизнес" - бизнес (в разработке)
"донат" - поддержать бота (в разработке)
"карта" - карта города (в разработке)
"статистика" - ваша статистика

<b>экономика:</b>
/pay @username сумма - перевести деньги другому игроку
"🔄" - обновить главное меню

<b>доступные работы:</b>
• 💩 говночист — лови лужи и собирай редкости
• 🐄 дояр — дои коров, собирай бонусы

<b>управление:</b>
"назад" - вернуться назад
"помощь" - показать справку
"настройки" - изменить ник и цвет персонажа

💡 <b>совет:</b> используй кнопки в меню для удобной навигации!"""
            
            keyboard = []
            if is_admin(user_id):
                keyboard.append([InlineKeyboardButton("🔐 команды админов", callback_data="help_admin_commands")])
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            try:
                try:
                    await query.edit_message_caption(
                        caption=help_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except:
                    await query.edit_message_text(
                        text=help_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                print(f"❌ ошибка при редактировании сообщения: {e}")
            return
        
        # обработка донатов
        if data == "donate_menu":
            await show_donation_menu(update, context)
            return
        elif data in ["pack_prev", "pack_next"]:
            await handle_pack_navigation(update, context)
            return
        elif data == "pack_back":
            await handle_back_to_packs(update, context)
            return
        elif data.startswith("pack_buy_"):
            await handle_buy_pack_selection(update, context)
            return
        elif data.startswith("pay_stars_"):
            await start_pack_stars_payment(update, context)
            return
        elif data.startswith("pay_crypto_"):
            await start_pack_crypto_payment(update, context)
            return
        elif data == "main_menu":
            await show_main_menu(update, context)
            return
        
        # обработка кнопки обновления времени бана
        if data.startswith('refresh_ban_'):
            target_user_id = int(data.replace('refresh_ban_', ''))
            
            # проверяем, что кнопку нажал забаненный пользователь
            if user_id != target_user_id:
                await query.answer("❌ эта кнопка не для вас!", show_alert=True)
                return
            
            # проверяем, все еще ли пользователь забанен
            if not is_user_banned(user_id):
                await query.answer("✅ вас уже разбанили!", show_alert=True)
                # удаляем сообщение о бане
                try:
                    await query.message.delete()
                except:
                    pass
                return
            
            remaining = get_ban_remaining_time(user_id)
            
            if remaining is None:
                await query.answer("❌ ошибка при получении информации о бане!", show_alert=True)
                return
            
            if remaining == -1:  # перманентный бан
                new_text = "🚫 <b>вы забанены навсегда!</b>\n\n<i>обновление времени недоступно для перманентного бана</i>"
                await query.answer("❌ вы забанены навсегда!", show_alert=True)
            elif remaining == 0:  # бан закончился
                unban_user(user_id)
                await query.answer("✅ бан закончился! вы свободны!", show_alert=True)
                new_text = "✅ <b>вас разбанили!</b>\n\nбан закончился, теперь вы снова можете использовать бота."
            else:
                formatted_time = format_ban_time(remaining)
                await query.answer(f"⏰ осталось: {formatted_time}")
                new_text = f"🚫 <b>вы забанены!</b>\n\n⏰ <b>осталось:</b> {formatted_time}\n\n<i>нажмите кнопку ниже чтобы обновить оставшееся время</i>"
            
            # обновляем сообщение
            if remaining > 0:  # если бан еще не закончился, показываем кнопку обновления
                keyboard = [
                    [InlineKeyboardButton("🔄 обновить время", callback_data=f"refresh_ban_{user_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            else:
                reply_markup = None
            
            try:
                await query.edit_message_text(
                    text=new_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"❌ ошибка при обновлении сообщения о бане: {e}")
                try:
                    await query.message.reply_text(
                        text=new_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception:
                    await query.bot.send_message(
                        chat_id=query.from_user.id,
                        text=new_text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            return
        
        # обработка админских инлайн кнопок
        elif data.startswith('admin_'):
            await handle_admin_actions(update, context)
            return
        
        # обработка кнопок регистрации
        elif data == "register":
            await choose_gender(update, context)
        
        elif data.startswith("gender_"):  # обработка выбора пола
            await choose_color(update, context)
        
        elif data == "color_black" or data == "color_white":
            await choose_name(update, context, data.replace("color_", ""))
        
        elif data == "cancel_registration":
            # очищаем данные о сообщениях выбора имени при отмене
            if 'name_selection_message_id' in context.user_data:
                del context.user_data['name_selection_message_id']
            if 'name_selection_chat_id' in context.user_data:
                del context.user_data['name_selection_chat_id']
            await start(update, context, MAIN_ADMIN_ID)
        
        elif data == "confirm_registration":
            await finish_registration(update, context, MAIN_ADMIN_ID)
        
        # обработка кнопок выбора работы
        elif data == "work_shit_cleaner":
            # ПРОВЕРКА: это должно быть сообщение текущего меню работы
            if query.message.message_id != context.user_data.get('work_menu_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await query.answer()
            # помечаем, что пользователь выбрал работу — не удаляем сообщения и кнопки
            context.user_data['selected_job'] = 'shit_cleaner'
            fake_update = FakeUpdate(update, query.message)
            await show_shit_cleaner_menu(fake_update, context)
            
        elif data == "work_milker":
            # ПРОВЕРКА: это должно быть сообщение текущего меню работы
            if query.message.message_id != context.user_data.get('work_menu_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await query.answer()
            # помечаем, что пользователь выбрал работу — не удаляем сообщения и кнопки
            context.user_data['selected_job'] = 'milker'
            fake_update = FakeUpdate(update, query.message)
            await show_milker_menu(fake_update, context)
        
        elif data == "work_scam":
            # ПРОВЕРКА: это должно быть сообщение текущего меню работы
            if query.message.message_id != context.user_data.get('work_menu_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await query.answer()
            # помечаем, что пользователь выбрал работу — не удаляем сообщения и кнопки
            context.user_data['selected_job'] = 'scam'
            fake_update = FakeUpdate(update, query.message)
            await show_scam_menu(fake_update, context)
         # обработка кнопок казино
        elif data == "casino_slot":
            if query.message.message_id != context.user_data.get('casino_games_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await query.answer()
            
            # Удаляем кнопки из сообщения выбора режима казино
            if 'casino_games_message_id' in context.user_data and 'casino_games_chat_id' in context.user_data:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=context.user_data['casino_games_chat_id'],
                        message_id=context.user_data['casino_games_message_id'],
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            # Отправляем меню слот-машины как новое сообщение
            await show_slot_machine(update, context)

        elif data == "casino_blackjack":
            if query.message.message_id != context.user_data.get('casino_games_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await query.answer()
            
            # Удаляем кнопки из сообщения выбора режима казино
            if 'casino_games_message_id' in context.user_data and 'casino_games_chat_id' in context.user_data:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=context.user_data['casino_games_chat_id'],
                        message_id=context.user_data['casino_games_message_id'],
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            # Отправляем меню блэкджека как новое сообщение
            await show_blackjack(update, context)

        elif data == "casino_back":
            await casino_back(update, context)

        # обработка кнопок настроек
        elif data == "settings_change_gender":
            if query.message.message_id != context.user_data.get('main_settings_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await show_gender_selection(update, context)

        elif data == "settings_gender_male":
            user_id = query.from_user.id
            update_user_gender(user_id, "male")
            clear_character_cache(user_id)
            await query.answer("✅ пол изменен на парень!")
            await show_main_settings(update, context)

        elif data == "settings_gender_female":
            user_id = query.from_user.id
            update_user_gender(user_id, "female")
            clear_character_cache(user_id)
            await query.answer("✅ пол изменен на девушка!")
            await show_main_settings(update, context)

        elif data == "settings_change_name":
            if query.message.message_id != context.user_data.get('main_settings_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            context.user_data['changing_name'] = True
            await context.bot.send_message(chat_id=user_id, text="✏️ введите новый ник для вашего персонажа:")

        elif data == "settings_change_color":
            if query.message.message_id != context.user_data.get('main_settings_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await show_color_selection(update, context)

        elif data == "settings_color_black":
            user_id = query.from_user.id
            update_user_color(user_id, "black")
            clear_character_cache(user_id)
            await query.answer("✅ цвет изменен на черный!")
            await show_settings(update, context)

        elif data == "settings_color_white":
            user_id = query.from_user.id
            update_user_color(user_id, "white")
            clear_character_cache(user_id)
            await query.answer("✅ цвет изменен на белый!")
            await show_settings(update, context)

        elif data == "settings_main":
            if query.message.message_id != context.user_data.get('settings_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            await show_main_settings(update, context)

        elif data == "settings_toggle_transfer_confirmation":
            if query.message.message_id != context.user_data.get('main_settings_message_id'):
                await query.answer("❌ кнопка неактивна!", show_alert=True)
                return
            user_id = query.from_user.id
            user = get_user(user_id)
            if user:
                current = user[14] if len(user) > 14 else False
                if current:
                    # Если сейчас отключено, включаем без предупреждения
                    update_user_disable_transfer_confirmation(user_id, False)
                    await query.answer("✅ подтверждение переводов включено!")
                    await show_main_settings(update, context)
                else:
                    # Если сейчас включено, показываем предупреждение перед отключением
                    context.user_data['confirm_disable_transfer'] = True
                    warning_text = """⚠️ <b>внимание!</b>

отключение подтверждения переводов <b>не рекомендуется</b>, так как повышает риск случайных переводов денег.

вы уверены, что хотите отключить подтверждение?"""

                    keyboard = [
                        [InlineKeyboardButton("✅ да, отключить", callback_data="confirm_disable_transfer")],
                        [InlineKeyboardButton("❌ нет, оставить", callback_data="cancel_disable_transfer")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    try:
                        await query.edit_message_caption(
                            caption=warning_text,
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                    except Exception:
                        await query.message.reply_text(
                            warning_text,
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )

        elif data == "confirm_disable_transfer":
            if 'confirm_disable_transfer' in context.user_data:
                del context.user_data['confirm_disable_transfer']
                user_id = query.from_user.id
                update_user_disable_transfer_confirmation(user_id, True)
                await query.answer("✅ подтверждение переводов отключено!")
                await show_main_settings(update, context)

        elif data == "cancel_disable_transfer":
            if 'confirm_disable_transfer' in context.user_data:
                del context.user_data['confirm_disable_transfer']
            await query.answer("❌ отмена")
            await show_main_settings(update, context)

        elif data == "transfer_confirm":
            await confirm_transfer(update, context)

        elif data == "transfer_cancel":
            if 'pending_transfer' in context.user_data:
                del context.user_data['pending_transfer']
            await query.answer("❌ перевод отменен!")
            await show_main_menu(update, context)

        elif data == "settings_notifications":
            await show_notifications_settings(update, context)

        elif data == "notifications_toggle_transfer":
            user_id = query.from_user.id
            user = get_user(user_id)
            if user:
                current = user[15] if len(user) > 15 else False
                new_value = not current
                update_user_disable_transfer_notifications(user_id, new_value)
                status = "отключены" if new_value else "включены"
                await query.answer(f"✅ уведомления о переводах {status}!")
                await show_notifications_settings(update, context)

        elif data == "notifications_toggle_news":
            user_id = query.from_user.id
            user = get_user(user_id)
            if user:
                current = user[16] if len(user) > 16 else False
                new_value = not current
                update_user_disable_news_notifications(user_id, new_value)
                status = "отключены" if new_value else "включены"
                await query.answer(f"✅ новостные уведомления {status}!")
                await show_notifications_settings(update, context)

        elif data == "notifications_toggle_system":
            user_id = query.from_user.id
            user = get_user(user_id)
            if user:
                current = user[17] if len(user) > 17 else False
                new_value = not current
                update_user_disable_system_notifications(user_id, new_value)
                status = "отключены" if new_value else "включены"
                await query.answer(f"✅ системные уведомления {status}!")
                await show_notifications_settings(update, context)

        elif data == "settings_back":
            await show_main_menu(update, context)

        # обработка кнопок блэкджека
        elif data == "blackjack_hit":
            await blackjack_hit(update, context)

        elif data == "blackjack_stand":
            await blackjack_stand(update, context)

        elif data == "blackjack_double":
            await blackjack_double(update, context)

        elif data == "blackjack_play_again":
            await query.answer()
            # Очищаем сохраненную ставку чтобы показать меню ввода новой ставки
            if 'last_blackjack_bet' in context.user_data:
                del context.user_data['last_blackjack_bet']
            # Показываем меню ввода ставки для блэкджека
            context.user_data['waiting_for_bet'] = 'blackjack'
            await show_blackjack(update, context)

        elif data == "slot_play_again":
            await query.answer()
            # Очищаем сохраненную ставку чтобы показать меню ввода новой ставки
            if 'last_slot_bet' in context.user_data:
                del context.user_data['last_slot_bet']
            # Показываем меню ввода ставки для слот-машины
            context.user_data['waiting_for_bet'] = 'slot'
            await show_slot_machine(update, context)

        # обработка кнопок подтверждения ставки
        elif data.startswith("bet_double_"):
            if query.message.message_id != context.user_data.get('current_bet_message_id'):
                await query.answer("❌ кнопка недействительна!", show_alert=True)
                return
            bet_amount = int(data.replace("bet_double_", ""))
            if bet_amount <= 0:
                await query.answer("❌ неверная сумма ставки!", show_alert=True)
                return
            new_bet = bet_amount * 2
            user = get_user(update.effective_user.id)
            if not user or new_bet > user[5]:
                await query.answer("❌ недостаточно средств для удвоения!")
                return
            await show_bet_confirmation(update, context, new_bet)

        elif data.startswith("bet_half_"):
            if query.message.message_id != context.user_data.get('current_bet_message_id'):
                await query.answer("❌ кнопка недействительна!", show_alert=True)
                return
            bet_amount = int(data.replace("bet_half_", ""))
            if bet_amount <= 0:
                await query.answer("❌ неверная сумма ставки!", show_alert=True)
                return
            new_bet = bet_amount // 2
            if new_bet < 1:
                new_bet = 1
            await show_bet_confirmation(update, context, new_bet)

        elif data.startswith("bet_all_"):
            if query.message.message_id != context.user_data.get('current_bet_message_id'):
                await query.answer("❌ кнопка недействительна!", show_alert=True)
                return
            user_balance = int(data.replace("bet_all_", ""))
            if user_balance <= 0:
                await query.answer("❌ недостаточно средств!", show_alert=True)
                return
            await show_bet_confirmation(update, context, user_balance)

        elif data.startswith("bet_place_"):
            if query.message.message_id != context.user_data.get('current_bet_message_id'):
                await query.answer("❌ кнопка недействительна!", show_alert=True)
                return
            await query.answer()
            
            # Удаляем кнопки из сообщения подтверждения ставки
            if 'current_bet_message_id' in context.user_data and 'current_bet_chat_id' in context.user_data:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=context.user_data['current_bet_chat_id'],
                        message_id=context.user_data['current_bet_message_id'],
                        reply_markup=None
                    )
                except Exception:
                    pass
            
            bet_amount = int(data.replace("bet_place_", ""))
            if bet_amount <= 0:
                await query.answer("❌ неверная сумма ставки!", show_alert=True)
                return
            user = get_user(update.effective_user.id)
            if not user or bet_amount > user[5]:
                await query.answer("❌ недостаточно средств!")
                return
            game_type = context.user_data.get('waiting_for_bet', 'slot')

            # Запускаем игру
            if game_type == 'slot':
                await play_slot_machine(update, context, bet_amount)
            elif game_type == 'blackjack':
                await play_blackjack(update, context, bet_amount)

            # Очищаем данные ставки
            if 'pending_bet' in context.user_data:
                del context.user_data['pending_bet']
            if 'waiting_for_bet' in context.user_data:
                del context.user_data['waiting_for_bet']

        # обработка неизвестных кнопок
        elif data.startswith("shop_"):
            if data == "shop_menu":
                await handle_shop_menu(update, context)
            elif data == "shop_accessories_start":
                await handle_shop_accessories_start(update, context)
            elif data == "shop_backgrounds_start":
                await handle_shop_backgrounds_start(update, context)
            elif data == "shop_acc_disabled":
                await update.callback_query.answer()
            elif data == "shop_acc_prev":
                await handle_shop_acc_nav(update, context, "prev")
            elif data == "shop_acc_next":
                await handle_shop_acc_nav(update, context, "next")
            elif data == "shop_acc_status":
                await update.callback_query.answer()
            elif data == "shop_bg_prev":
                await handle_shop_bg_nav(update, context, "prev")
            elif data == "shop_bg_next":
                await handle_shop_bg_nav(update, context, "next")
            elif data.startswith("shop_acc_buy_"):
                await handle_shop_buy_accessory(update, context)
            elif data.startswith("shop_acc_toggle_"):
                await handle_shop_toggle_accessory(update, context)
            elif data.startswith("shop_bg_buy_"):
                await handle_shop_buy_background(update, context)
            elif data.startswith("shop_bg_toggle_"):
                await handle_shop_toggle_background(update, context)
        
        elif data.startswith("wardrobe_"):
            if data == "wardrobe_menu":
                await show_wardrobe_menu(update, context)
            elif data == "wardrobe_accessories":
                await show_accessories_shop(update, context)
            elif data == "wardrobe_backgrounds":
                await show_backgrounds_shop(update, context)
        
        # обработка магазина админ валюты
        elif data.startswith("admin_shop") or data.startswith("admin_exchange") or data.startswith("admin_buy"):
            if data == "admin_shop":
                await show_admin_shop(update, context)
            else:
                await handle_admin_shop_callback(update, context, data)
        
        else:
            print(f"⚠️ неизвестная callback data: {data}")
            try:
                await query.message.edit_text("❌ неизвестная команда!")
            except:
                pass
                
    except Exception as e:
        print(f"❌ ошибка в button_handler: {e}")
        await query.answer("❌ произошла ошибка!", show_alert=True)

# старт команды (обертка)
async def start_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context, MAIN_ADMIN_ID)

# обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_logger.error(f"exception while handling an update: {context.error}")

# функция для обновления username главного админа
def update_main_admin_username(user_id, username):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    conn.commit()
    conn.close()

def main():
    print("🔧 инициализация базы данных...")
    # инициализация бд
    init_db()
    
    print("🎨 инициализация аксессуаров и фонов...")
    # инициализация аксессуаров и фонов
    init_accessories_and_backgrounds()
    
    print("�👑 проверка главного админа...")
    # создаем главного админа при первом запуске
    user = get_user(MAIN_ADMIN_ID)
    if not user:
        print("👑 создание главного админа...")
        user_data = (
            MAIN_ADMIN_ID,
            "triplesirota",  # временный username
            "мембер",
            "male",  # пол по умолчанию
            "black",
            999999,
            True,
            True,
            True,
            False,  # banned
            0,      # ban_duration
            0,      # ban_start_time
            None,   # banned_by
            ""      # ban_reason
        )
        save_user(user_data)
        print("✅ главный админ создан")
    else:
        print("✅ главный админ уже существует")
    
    print("🤖 создание приложения...")
    # создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    print("📋 регистрация обработчиков...")
    # обработчики
    application.add_handler(CommandHandler("start", start_wrapper))
    application.add_handler(CommandHandler("me", me_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("helpadm", helpadm_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("adminshop", adminshop_command))
    application.add_handler(CommandHandler("pay", transfer_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    
    # обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # обработчик неизвестных команд должен быть последним
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text_messages_wrapper))
    
    application.add_error_handler(error_handler)
    
    print("✅ бот запущен и готов к работе!")
    print("📱 теперь иди в telegram и напиши /start боту")
    
    # запускаем бота без лишних логов
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
