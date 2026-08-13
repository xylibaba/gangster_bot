import logging
import sys
import sqlite3
import asyncio
import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
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
    update_user_disable_referral_notifications, is_referral_notifications_disabled,
    get_news_subscribed_user_ids,
    get_user_activity_logs, log_financial_transaction, is_admin, DB_PATH
)
from utils import safe_delete_message, format_money, parse_amount, set_global_bot

from main_menu import show_main_menu, show_work_menu, show_user_profile, refresh_main_menu, create_profile_text, create_admin_keyboard, show_settings, show_main_settings, show_color_selection, show_gender_selection, show_notifications_settings, show_top_balance
from shit_cleaner import show_shit_cleaner_menu, start_shit_cleaning, update_cleaning_time_manual, cancel_cleaning, show_cleaning_progress, is_cleaning_in_progress
from milker import show_milker_menu, start_milking, cancel_milking, update_milking_time_manual, show_milking_progress
from scam import show_scam_menu, handle_referral_registration, add_referral_donation_earnings, add_referral_job_earnings, init_referral_stats, show_scam_instruction
from jobs import show_stats
from donations import (
    show_donation_menu, pre_checkout_handler,
    successful_payment_handler,
    handle_pack_navigation, handle_buy_pack_selection, start_pack_stars_payment, start_pack_crypto_payment,
    handle_back_to_packs, check_payment_command, check_all_pending_crypto_payments,
    prompt_promocode, activate_promocode, process_gangster_plus_weekly_payouts
)
from accessories import (init_accessories_and_backgrounds, show_wardrobe_menu, show_accessories_shop, show_backgrounds_shop,
                         show_shop_main, handle_shop_accessories_start, handle_shop_backgrounds_start, handle_shop_menu,
                         handle_shop_acc_nav, handle_shop_bg_nav, handle_shop_buy_accessory, handle_shop_buy_background, 
                         handle_shop_toggle_accessory, handle_shop_toggle_background, clear_character_cache,
                         get_accessory_id_by_name, is_accessory_equipped, equip_accessory, unequip_accessory,
                         show_tshirt_distribution_menu, claim_tshirt_distribution)
import homes
import business

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

<b>экономика:</b>
/pay @username сумма - перевести деньги другому игроку

🎧 <b>поддержка пользователей:</b>
если у тебя возник вопрос или проблема, напиши в бота поддержки: @gangstasupport_bot

💡 <b>совет:</b> используй кнопки в меню для удобной навигации!"""

    # создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton("🎧 связаться с поддержкой", url="https://t.me/gangstasupport_bot")],
        [
            InlineKeyboardButton("📜 оферта", url="https://telegra.ph/PUBLICHNAYA-OFERTA-POLZOVATELSKOE-SOGLASHENIE-08-11"),
            InlineKeyboardButton("🔒 приватность", url="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-11-81")
        ]
    ]
    
    # если пользователь админ, добавляем кнопку админ команд
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🔐 команды админов", callback_data="help_admin_commands")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

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

<b>основные команды:</b>
/start - перезапустить бота
/me - главное меню
/help - помощь для пользователей
/helpadm - эта справка"""

    await update.message.reply_text(helpadm_text, parse_mode='HTML')

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
    
    args = getattr(context, 'args', None) or []
    # если аргументов нет, показываем свой профиль
    if not args:
        await show_user_profile(update, context, current_user, is_admin_viewer=is_admin(user_id))
        return
    
    target_username = args[0].replace('@', '')
    
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
    
    is_viewer_admin = is_admin(user_id)
    
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
    
    # 🔒 Проверяем права: логи доступны ТОЛЬКО главному админу
    if not is_main_admin(user_id):
        await query.answer("❌ просмотр логов доступен только главному админу!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
    
    nickname = target_user[2] if len(target_user) > 2 else "неизвестно"
    
    # Получаем финансовые логи активности за 7 дней
    logs = get_user_activity_logs(target_user_id, limit=35)
    
    if not logs:
        message_text = f"📋 <b>логи активности {nickname} (за 7 дней)</b>\n\n🔍 нет записей о финансовых операциях за прошлую неделю"
    else:
        message_text = f"📋 <b>логи активности {nickname} (за 7 дней)</b>\n\n"
        for log in logs:
            action_type, amount, details, timestamp = log
            
            dt = datetime.datetime.fromtimestamp(timestamp)
            time_str = dt.strftime("%d.%m %H:%M")
            
            sign = "+" if amount > 0 else ""
            amt_str = f" <b>({sign}{format_money(amount)})</b>" if amount != 0 else ""
            
            icon = "📊"
            if "win" in action_type or "salary" in action_type or "earn" in action_type or "give" in action_type:
                icon = "💰"
            elif "loss" in action_type or "buy" in action_type:
                icon = "💸"
            elif "casino" in action_type:
                icon = "🎰"
            elif "transfer" in action_type:
                icon = "🔄"
            elif "donation" in action_type:
                icon = "💎"
                
            message_text += f"{icon} <code>[{time_str}]</code> {details}{amt_str}\n"
    
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
# выдача денег
async def admin_give_money_start(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем права - ТОЛЬКО ГЛАВНЫЙ АДМИН
    if not is_main_admin(user_id):
        await query.answer("❌ только главный админ может выдавать деньги!", show_alert=True)
        return
    
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
    
    nickname = target_user[2] if len(target_user) > 2 else "неизвестно"
    
    # Сохраняем ID целевого пользователя в контексте
    context.user_data['admin_giving_money_to'] = target_user_id
    context.user_data['admin_giving_money_from'] = user_id
    
    await query.answer()
    
    message_text = f"💰 <b>выдача денег</b>\n\nполучатель: <b>{nickname}</b>\n\nсколько денег выдать? (можно ввести: 1000, 1к, 1.5к, 1кк, 1ккк, 1кккк, 1ккккк)"
    
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
        
        # выдача денег
        elif data.startswith('admin_give_money_') or data.startswith('admin_give_coins_'):
            target_user_id = int(data.replace('admin_give_money_', '').replace('admin_give_coins_', ''))
            await admin_give_money_start(update, context, target_user_id)
        
        # переключение гангстер плюс
        elif data.startswith('admin_toggle_plus_'):
            target_user_id = int(data.replace('admin_toggle_plus_', ''))
            await toggle_gangster_plus(update, context, target_user_id)
        
        # перевести деньги пользователю
        elif data.startswith('pay_start_'):
            target_user_id = int(data.replace('pay_start_', ''))
            target_user = get_user(target_user_id)
            if target_user:
                nickname = target_user[2] if len(target_user) > 2 else "пользователю"
                username = target_user[1] if len(target_user) > 1 else None
                cmd_hint = f"/pay @{username} 1000" if username else f"/pay {target_user_id} 1000"
                msg_text = (
                    f"💸 <b>перевод средств пользователю {nickname}</b>\n\n"
                    f"чтобы перевести деньги, отправьте команду в чат:\n"
                    f"<code>{cmd_hint}</code>"
                )
                await query.answer()
                await context.bot.send_message(chat_id=query.message.chat_id, text=msg_text, parse_mode='HTML')
        
        else:
            await query.answer("❌ неизвестная команда!", show_alert=True)
            
    except ValueError as e:
        await query.answer("❌ ошибка в данных!", show_alert=True)
        print(f"❌ ошибка в handle_admin_actions: {e}")
    except Exception as e:
        await query.answer("❌ произошла ошибка!", show_alert=True)
        print(f"❌ непредвиденная ошибка в handle_admin_actions: {e}")

# функция для переключения подписки Гангстер Плюс главным админом
async def toggle_gangster_plus(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_main_admin(user_id):
        await query.answer("❌ только главный админ может изменять подписку!", show_alert=True)
        return
        
    target_user = get_user(target_user_id)
    if not target_user:
        await query.answer("❌ пользователь не найден!", show_alert=True)
        return
        
    current_plus = target_user[18] if len(target_user) > 18 else False
    new_plus = not current_plus
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_gangster_plus = ? WHERE user_id = ?', (new_plus, target_user_id))
    conn.commit()
    conn.close()
    
    clear_character_cache(target_user_id)
    
    status_text = "выдана 💎" if new_plus else "забрана ❌"
    await query.answer(f"✅ подписка Гангстер Плюс {status_text}!")
    
    updated_user = get_user(target_user_id)
    await show_user_profile(update, context, updated_user, is_admin_viewer=True)

# функция для немедленного выполнения перевода (без подтверждения)
async def confirm_transfer_immediate(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user, amount):
    user_id = update.effective_user.id
    conn = None  # инициализируем переменную

    # получаем актуальные данные отправителя
    from_user = get_user(user_id)
    if not from_user:
        await update.message.reply_text("❌ ошибка: пользователь не найден!")
        return

    # выполняем перевод в одной транзакции
    try:
        # создаем одно соединение для всей операции
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
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

        log_financial_transaction(user_id, "transfer_send", -amount, f"перевод пользователю {target_user[2]}")
        log_financial_transaction(target_user[0], "transfer_receive", amount, f"перевод от пользователя {from_user[2]}")

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

        # отправляем уведомление получателю (если не отключены уведомления о переводах)
        disable_transfer_notif = target_user[15] if len(target_user) > 15 else False
        if not disable_transfer_notif:
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
            if conn:
                conn.rollback()
        except Exception:
            pass
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

# функция для подтверждения перевода денег
async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    conn = None  # инициализируем переменную

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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
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

        # отправляем уведомление получателю (если не отключены уведомления о переводах)
        disable_transfer_notif = target_user[15] if len(target_user) > 15 else False
        if not disable_transfer_notif:
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
            if conn:
                conn.rollback()
        except Exception:
            pass
        del context.user_data['pending_transfer']
    except Exception as e:
        await query.answer("❌ ошибка при выполнении перевода!")
        print(f"ошибка перевода: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        del context.user_data['pending_transfer']
    finally:
        try:
            if conn:
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
    
    args = getattr(context, 'args', None) or []
    # проверяем аргументы
    if len(args) < 2:
        await update.message.reply_text("❌ использование: /pay @username сумма")
        return
    
    target_username = args[0].replace('@', '')
    
    amount = parse_amount(args[1], max_amount=from_user_balance)
    if amount <= 0:
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
    
    args = getattr(context, 'args', None) or []
    # проверяем аргументы
    if len(args) < 1:
        await update.message.reply_text("❌ использование: /ban @username [причина]")
        return
    
    target_username = args[0].replace('@', '')
    reason = " ".join(args[1:]) if len(args) > 1 else "причина не указана"
    
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
    
    args = getattr(context, 'args', None) or []
    # проверяем аргументы
    if not args:
        await update.message.reply_text("❌ использование: /unban @username")
        return
    
    target_username = args[0].replace('@', '')
    
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
    
    args = getattr(context, 'args', None) or []
    # проверяем аргументы
    if not args:
        await update.message.reply_text("❌ использование: /add_admin @username")
        return
    
    target_username = args[0].replace('@', '')
    
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    
    args = getattr(context, 'args', None) or []
    # проверяем аргументы
    if not args:
        await update.message.reply_text("❌ использование: /remove_admin @username")
        return
    
    target_username = args[0].replace('@', '')
    
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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

# команда выдачи доната (только для главного админа, для остальных — неизвестная команда)
async def donations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # проверяем бан - забаненные пользователи игнорируются полностью
    if is_user_banned(user_id):
        return
    
    # если не главный админ (обычный пользователь или обычный админ) — отвечаем "неизвестная команда"
    if not is_main_admin(user_id):
        await unknown_command(update, context)
        return
    
    # проверяем rate limit
    if not await rate_limit_check(update, context):
        return
    
    args = getattr(context, 'args', None) or []
    if len(args) < 2:
        await update.message.reply_text(
            "👑 <b>выдача доната (Главный Админ)</b>\n\n"
            "<b>использование:</b>\n"
            "<code>/donations @username <набор></code>\n"
            "<code>/donations ID <набор></code>\n\n"
            "<b>доступные наборы:</b>\n"
            "• <code>0</code> или <code>molodoy</code> — 📦 <b>молодой</b> (10кк, скин, х2 со всего заработка на 24 часа)\n"
            "• <code>1</code> или <code>gangster_plus</code> — 💎 <b>гангстер плюс</b> (х4 прибыль, 💎 около ника, 5кк каждую неделю)",
            parse_mode='HTML'
        )
        return
    
    target_username = args[0].replace('@', '').strip()
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
        
    target_user_id = target_user[0]
    target_nickname = target_user[2] if len(target_user) > 2 else f"ID {target_user_id}"
    
    pack_input = args[1].lower().strip()
    pack_index = None
    if pack_input in ['0', 'molodoy', 'молодой']:
        pack_index = 0
    elif pack_input in ['1', 'gangster_plus', 'плюс', 'гангстер']:
        pack_index = 1
    else:
        try:
            idx = int(pack_input)
            from donations import packs
            if 0 <= idx < len(packs):
                pack_index = idx
        except ValueError:
            pass
            
    if pack_index is None:
        await update.message.reply_text("❌ неверный набор! используйте 0 (молодой) или 1 (гангстер плюс).")
        return
        
    from donations import apply_pack_rewards, packs
    pack = packs[pack_index]
    
    success_msg = await apply_pack_rewards(target_user_id, pack_index)
    log_admin_action(user_id, "give_donation", target_user_id, f"выдан донат {pack['title']}")
    
    await update.message.reply_text(
        f"✅ <b>донат успешно выдан!</b>\n\n"
        f"👤 <b>получатель:</b> <b>{target_nickname}</b> (ID: <code>{target_user_id}</code>)\n"
        f"🎁 <b>пакет:</b> <b>{pack['title']}</b>",
        parse_mode='HTML'
    )
    
    # отправляем уведомление получателю
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎁 <b>Вам выдан донат от Главного Администратора!</b>\n\n{success_msg}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.warning(f"Could not send donation notification to user {target_user_id}: {e}")

# команда рассылки новостей для главного админа
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        return
        
    if not is_main_admin(user_id):
        await update.message.reply_text("❌ только главный админ может делать рассылку!")
        return
        
    from registration import get_news_subscribed_user_ids
    user_ids = get_news_subscribed_user_ids()
    
    if not user_ids:
        await update.message.reply_text("❌ нет пользователей для рассылки!")
        return
        
    msg = update.message
    reply_msg = msg.reply_to_message
    
    target_msg_id = None
    clean_caption = None
    import re
    
    if reply_msg:
        target_msg_id = reply_msg.message_id
        raw_text = msg.text or msg.caption or ""
        clean_text = re.sub(r'^/news(@\w+)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
        if clean_text:
            clean_caption = clean_text
    elif msg.photo or msg.video or msg.animation or msg.document or msg.audio or msg.voice:
        target_msg_id = msg.message_id
        raw_caption = msg.caption or ""
        clean_caption = re.sub(r'^/news(@\w+)?\s*', '', raw_caption, flags=re.IGNORECASE).strip()
    else:
        args = getattr(context, 'args', None) or []
        raw_text = msg.text or ""
        clean_text = raw_text.replace("/news", "").strip()
        
        if not clean_text and not args:
            await update.message.reply_text(
                "📢 <b>рассылка новостей (/news)</b>\n\n"
                "<b>способы использования:</b>\n"
                "• <code>/news Текст сообщения</code> — рассылка текста\n"
                "• Прикрепить фото/видео с подписью <code>/news Текст</code> — рассылка медиа с текстом\n"
                "• Ответить командой <code>/news</code> на любое сообщение, фото или видео",
                parse_mode='HTML'
            )
            return
        
        target_msg_id = None
        clean_caption = clean_text or " ".join(args)
        
    status_msg = await update.message.reply_text(f"⏳ запуск рассылки для {len(user_ids)} пользователей...")
    
    success_count = 0
    fail_count = 0
    
    for uid in user_ids:
        try:
            if target_msg_id:
                copy_kwargs = {
                    'chat_id': uid,
                    'from_chat_id': msg.chat_id,
                    'message_id': target_msg_id
                }
                if clean_caption is not None:
                    copy_kwargs['caption'] = clean_caption
                    copy_kwargs['parse_mode'] = 'HTML'
                await context.bot.copy_message(**copy_kwargs)
            else:
                await context.bot.send_message(chat_id=uid, text=clean_caption, parse_mode='HTML')
            
            success_count += 1
            await asyncio.sleep(0.04)
        except Exception as e:
            bot_logger.warning(f"Could not send news to user {uid}: {e}")
            fail_count += 1
            
    await status_msg.edit_text(
        f"✅ <b>рассылка завершена!</b>\n\n"
        f"📊 <b>статистика:</b>\n"
        f"• успешно доставлено: <b>{success_count}</b>\n"
        f"• ошибок/заблокировано: <b>{fail_count}</b>",
        parse_mode='HTML'
    )

# команда важной рассылки новостей для главного админа (доставляется ВСЕМ зарегистрированным пользователям)
async def onews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        return
        
    if not is_main_admin(user_id):
        await update.message.reply_text("❌ только главный админ может делать важную рассылку!")
        return
        
    from registration import get_all_user_ids
    user_ids = get_all_user_ids()
    
    if not user_ids:
        await update.message.reply_text("❌ нет зарегистрированных пользователей для рассылки!")
        return
        
    msg = update.message
    reply_msg = msg.reply_to_message
    
    target_msg_id = None
    clean_caption = None
    import re
    
    if reply_msg:
        target_msg_id = reply_msg.message_id
        raw_text = msg.text or msg.caption or ""
        clean_text = re.sub(r'^/onews(@\w+)?\s*', '', raw_text, flags=re.IGNORECASE).strip()
        if clean_text:
            clean_caption = clean_text
    elif msg.photo or msg.video or msg.animation or msg.document or msg.audio or msg.voice:
        target_msg_id = msg.message_id
        raw_caption = msg.caption or ""
        clean_caption = re.sub(r'^/onews(@\w+)?\s*', '', raw_caption, flags=re.IGNORECASE).strip()
    else:
        args = getattr(context, 'args', None) or []
        raw_text = msg.text or ""
        clean_text = raw_text.replace("/onews", "").strip()
        
        if not clean_text and not args:
            await update.message.reply_text(
                "🚨 <b>важная рассылка новостей (/onews)</b>\n\n"
                "<i>Эта рассылка доставляется ВСЕМ пользователям, независимо от их настроек уведомлений.</i>\n\n"
                "<b>способы использования:</b>\n"
                "• <code>/onews Текст сообщения</code> — важная рассылка текста\n"
                "• Прикрепить фото/видео с подписью <code>/onews Текст</code> — важная рассылка медиа с текстом\n"
                "• Ответить командой <code>/onews</code> на любое сообщение, фото или видео",
                parse_mode='HTML'
            )
            return
        
        target_msg_id = None
        clean_caption = clean_text or " ".join(args)
        
    status_msg = await update.message.reply_text(f"⏳ запуск важной рассылки для {len(user_ids)} пользователей...")
    
    success_count = 0
    fail_count = 0
    
    for uid in user_ids:
        try:
            if target_msg_id:
                copy_kwargs = {
                    'chat_id': uid,
                    'from_chat_id': msg.chat_id,
                    'message_id': target_msg_id
                }
                if clean_caption is not None:
                    copy_kwargs['caption'] = clean_caption
                    copy_kwargs['parse_mode'] = 'HTML'
                await context.bot.copy_message(**copy_kwargs)
            else:
                await context.bot.send_message(chat_id=uid, text=clean_caption, parse_mode='HTML')
            
            success_count += 1
            await asyncio.sleep(0.04)
        except Exception as e:
            bot_logger.warning(f"Could not send important news to user {uid}: {e}")
            fail_count += 1
            
    await status_msg.edit_text(
        f"✅ <b>важная рассылка завершена!</b>\n\n"
        f"📊 <b>статистика:</b>\n"
        f"• успешно доставлено: <b>{success_count}</b>\n"
        f"• ошибок/заблокировано: <b>{fail_count}</b>",
        parse_mode='HTML'
    )

# Команды управления промокодами (Главный Админ)
async def addpromo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает новый промокод (только для Главного Админа)"""
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        return
    if not is_main_admin(user_id):
        await update.message.reply_text("❌ только главный админ может создавать промокоды!")
        return
        
    args = getattr(context, 'args', None) or []
    if not args:
        from donations import render_promo_constructor_screen
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    code_input = args[0]
    rewards_str = args[1] if len(args) > 1 else ""
    max_uses_str = args[2] if len(args) > 2 else "1"
    target_user_str = args[3] if len(args) > 3 else "-"
    hours_str = args[4] if len(args) > 4 else "-"
    
    from donations import parse_promo_rewards, resolve_accessory_id_by_name_or_id, resolve_background_id_by_name_or_id, resolve_skin_id_by_name_or_id, create_promocode_entry
    parsed_rewards = parse_promo_rewards(rewards_str)
    
    reward_money = parsed_rewards['money']
    reward_acc_id = resolve_accessory_id_by_name_or_id(parsed_rewards['acc_name']) if parsed_rewards['acc_name'] else None
    reward_bg_id = resolve_background_id_by_name_or_id(parsed_rewards['bg_name']) if parsed_rewards['bg_name'] else None
    reward_skin_id = resolve_skin_id_by_name_or_id(parsed_rewards['skin_name']) if parsed_rewards['skin_name'] else None
    
    try:
        max_uses = int(max_uses_str) if max_uses_str != '-' else 1
    except ValueError:
        max_uses = 1
        
    target_user_id = None
    if target_user_str != '-':
        target_username = target_user_str.replace('@', '')
        t_user = get_user_by_username(target_username)
        if not t_user:
            try:
                t_user = get_user(int(target_username))
            except ValueError:
                pass
        if t_user:
            target_user_id = t_user[0]
        else:
            await update.message.reply_text(f"❌ Пользователь '{target_user_str}' не найден!")
            return

    try:
        expires_in_hours = float(hours_str) if hours_str != '-' else None
    except ValueError:
        expires_in_hours = None

    success, msg, created_code = create_promocode_entry(
        code=code_input,
        reward_money=reward_money,
        reward_accessory_id=reward_acc_id,
        reward_background_id=reward_bg_id,
        reward_skin_id=reward_skin_id,
        target_user_id=target_user_id,
        max_uses=max_uses,
        expires_in_hours=expires_in_hours,
        created_by=user_id
    )
    
    if success:
        from utils import format_money
        res_text = (
            f"✅ <b>Промокод <code>{created_code}</code> успешно создан!</b>\n\n"
            f"📋 <b>Содержимое:</b>\n"
        )
        if reward_money > 0:
            res_text += f"• 💰 Деньги: {format_money(reward_money)}\n"
        if reward_acc_id:
            res_text += f"• 👕 Аксессуар ID: {reward_acc_id}\n"
        if reward_bg_id:
            res_text += f"• 🎨 Фон ID: {reward_bg_id}\n"
        if reward_skin_id:
            res_text += f"• 👤 Скин ID: {reward_skin_id}\n"
        if parsed_rewards['is_plus']:
            res_text += "• ⭐️ Подписка Гангстер Плюс\n"
            
        res_text += f"\n👥 Макс. активаций: {max_uses if max_uses > 0 else 'Безлимит'}\n"
        if target_user_id:
            res_text += f"🎯 Только для ID: {target_user_id}\n"
        if expires_in_hours:
            res_text += f"⏳ Срок действия: {expires_in_hours} ч.\n"
            
        await update.message.reply_text(res_text, parse_mode='HTML')
    else:
        await update.message.reply_text(msg, parse_mode='HTML')

async def promos_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список существующих промокодов (для Главного Админа)"""
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        return
    if not is_main_admin(user_id):
        await update.message.reply_text("❌ только главный админ может просматривать промокоды!")
        return
        
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT code, reward_money, reward_accessory_id, reward_background_id, reward_skin_id,
               target_user_id, max_uses, uses_count, expires_at
        FROM promocodes
        ORDER BY rowid DESC
        LIMIT 30
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("🎟️ <b>Список промокодов пуст.</b>", parse_mode='HTML')
        return
        
    text = "🎟️ <b>Список промокодов:</b>\n\n"
    import time
    from utils import format_money
    now = time.time()
    for row in rows:
        code, money, acc_id, bg_id, skin_id, target_uid, max_u, uses, exp = row
        status = "✅"
        if exp and now > exp:
            status = "⏳ истёк"
        elif max_u > 0 and uses >= max_u:
            status = "❌ исчерпан"
            
        rewards = []
        if money: rewards.append(f"{format_money(money)}")
        if acc_id: rewards.append(f"акс#{acc_id}")
        if bg_id: rewards.append(f"фон#{bg_id}")
        if skin_id: rewards.append(f"скин#{skin_id}")
        rewards_str = ", ".join(rewards) if rewards else "бонус"
        
        text += f"{status} <code>{code}</code> — [{rewards_str}] ({uses}/{max_u if max_u > 0 else '∞'})\n"
        
    await update.message.reply_text(text, parse_mode='HTML')

async def delpromo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет промокод (для Главного Админа)"""
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        return
    if not is_main_admin(user_id):
        await update.message.reply_text("❌ только главный админ может удалять промокоды!")
        return
        
    args = getattr(context, 'args', None) or []
    if not args:
        await update.message.reply_text("❌ Использование: <code>/delpromo <code></code>", parse_mode='HTML')
        return
        
    code_del = args[0].strip().upper()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM promocodes WHERE UPPER(code) = ?", (code_del,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if deleted:
        await update.message.reply_text(f"✅ Промокод <code>{code_del}</code> удалён!", parse_mode='HTML')
    else:
        await update.message.reply_text(f"❌ Промокод <code>{code_del}</code> не найден!", parse_mode='HTML')

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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    
    # обработка выдачи денег
    if 'admin_giving_money_to' in context.user_data or 'admin_giving_coins_to' in context.user_data:
        target_user_id = context.user_data.get('admin_giving_money_to') or context.user_data.get('admin_giving_coins_to')
        
        amount = parse_amount(update.message.text)
        if amount <= 0:
            await update.message.reply_text("❌ неверный формат суммы! используйте: 1000, 1к, 1.5к, 1кк, 1ккк, 1кккк, 1ккккк")
            return
            
        if amount <= 0:
            await update.message.reply_text("❌ сумма денег должна быть больше нуля!")
            return
            
        new_balance = update_user_money(target_user_id, amount)
        
        target_user = get_user(target_user_id)
        nickname = target_user[2] if target_user and len(target_user) > 2 else "неизвестно"
        
        log_admin_action(user_id, "give_money", target_user_id, f"выдано {format_money(amount)} денег")
        log_financial_transaction(target_user_id, "admin_give", amount, f"начисление от админа")
        
        if 'admin_giving_money_to' in context.user_data:
            del context.user_data['admin_giving_money_to']
        if 'admin_giving_coins_to' in context.user_data:
            del context.user_data['admin_giving_coins_to']
        if 'admin_giving_coins_from' in context.user_data:
            del context.user_data['admin_giving_coins_from']
            
        admin_name = update.effective_user.username or "админ"
        await update.message.reply_text(f"✅ {nickname} получил {format_money(amount)}!", parse_mode='HTML')
        
        try:
            notification = f"💰 <b>вам выдали деньги!</b>\n\nполучено: <b>{format_money(amount)}</b>\n"
            if new_balance is not None:
                notification += f"новый баланс: <b>{format_money(new_balance)}</b>"
            notification += f"\n\nотправитель: <b>{admin_name}</b> (@{admin_name})"
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=notification,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"⚠️ не удалось отправить уведомление пользователю {target_user_id}: {e}")
            
        await show_main_menu(update, context)
        return
        
    if context.user_data.get('waiting_for_promocode'):
        del context.user_data['waiting_for_promocode']
        code_input = update.message.text.strip()
        if code_input.lower() in ['назад', 'отмена', 'cancel']:
            await show_donation_menu(update, context)
            return
        success, msg = activate_promocode(user_id, code_input)
        await update.message.reply_text(msg, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_promo_money'):
        del context.user_data['waiting_for_promo_money']
        val = parse_amount(update.message.text.strip())
        from donations import get_promo_builder_data, render_promo_constructor_screen
        bld = get_promo_builder_data(context)
        bld['money'] = val
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_promo_code'):
        del context.user_data['waiting_for_promo_code']
        code_str = update.message.text.strip().upper()
        from donations import get_promo_builder_data, render_promo_constructor_screen
        bld = get_promo_builder_data(context)
        bld['code'] = code_str
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_promo_uses'):
        del context.user_data['waiting_for_promo_uses']
        try:
            val = int(update.message.text.strip())
        except ValueError:
            val = 1
        from donations import get_promo_builder_data, render_promo_constructor_screen
        bld = get_promo_builder_data(context)
        bld['max_uses'] = val
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_promo_exp'):
        del context.user_data['waiting_for_promo_exp']
        try:
            val = float(update.message.text.strip())
        except ValueError:
            val = None
        from donations import get_promo_builder_data, render_promo_constructor_screen
        bld = get_promo_builder_data(context)
        bld['expires_hours'] = val if (val and val > 0) else None
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_promo_target'):
        del context.user_data['waiting_for_promo_target']
        input_str = update.message.text.strip().replace('@', '')
        t_user = get_user_by_username(input_str)
        if not t_user:
            try:
                t_user = get_user(int(input_str))
            except ValueError:
                pass
        from donations import get_promo_builder_data, render_promo_constructor_screen
        bld = get_promo_builder_data(context)
        if t_user:
            bld['target_user_id'] = t_user[0]
            await update.message.reply_text(f"✅ Установлен получатель: {t_user[2]} (ID: {t_user[0]})")
        else:
            await update.message.reply_text(f"❌ Пользователь '{input_str}' не найден!")
        text, reply_markup = render_promo_constructor_screen(context)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        return

    if context.user_data.get('waiting_for_roommate_invite'):
        await homes.finish_invite_roommate(update, context, update.message.text.strip())
        return
    
    text = update.message.text.strip().lower()
    first_word = text.split()[0] if text.split() else text

    handled = False

    # обработка кнопок главного меню
    if text in ["работа", "работа ✅"]:
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
        
        is_viewer_admin = is_admin(user_id)
        
        # логируем действие админа если это админ
        if is_viewer_admin and target_user[0] != user_id:
            log_admin_action(user_id, "profile_view", target_user[0], f"просмотр профиля {target_user[2]}")
        
        # показываем профиль пользователя
        await show_user_profile(update, context, target_user, is_admin_viewer=is_viewer_admin)
        return
    elif text == "назад":
        handled = True
        
        # если пользователь в разделе доната - вернуться в главное меню
        if context.user_data.get('in_donation_menu'):
            del context.user_data['in_donation_menu']
            await show_main_menu(update, context)
            return

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
    elif text in ["🔄", "🔄 ✅"]:  # обработка кнопки обновления
        handled = True
        await refresh_main_menu(update, context)
        return
    elif text in ["казино", "казино ✅"]:
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
        context.user_data['current_background_index'] = 0
        context.user_data['in_backgrounds_shop'] = True
        from accessories import _show_background_carousel
        await _show_background_carousel(update, context)
        return
    elif text == "назад" and (context.user_data.get('in_accessories_shop') or context.user_data.get('in_backgrounds_shop')):
        handled = True
        context.user_data['in_accessories_shop'] = False
        context.user_data['in_backgrounds_shop'] = False
        await show_shop_main(update, context)
        return
    elif text in ["дом", "🏠 дом", "дом ✅"]:
        handled = True
        await homes.show_home_menu(update, context)
        return
    elif text in ["👕 шкаф", "шкаф"]:
        handled = True
        await homes.show_wardrobe_page(update, context, page=0)
        return
    elif text in ["👥 подселение", "подселение"]:
        handled = True
        await homes.start_invite_roommate(update, context)
        return
    elif text in ["⚙️ настройки дома", "настройки дома"]:
        handled = True
        await homes.show_home_settings(update, context)
        return
    elif text in ["бизнес", "бизнесы"]:
        handled = True
        await update.message.reply_text("⚠️ <b>раздел бизнесы временно недоступен!</b>", parse_mode='HTML')
        return
    elif text in ["донат", "донат ✅"]:
        handled = True
        await show_donation_menu(update, context)
        return
    elif text in ["🎁 промокод", "промокод"] or first_word in ["промокоды", "промокод", "промо"]:
        handled = True
        parts = update.message.text.split(maxsplit=1)
        if len(parts) > 1:
            code_input = parts[1].strip()
            from donations import activate_promocode
            success, msg = activate_promocode(user_id, code_input)
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await prompt_promocode(update, context)
        return
    elif text in ["раздача 🎁", "🎁 раздача", "раздача"]:
        handled = True
        await show_tshirt_distribution_menu(update, context)
        return
    elif text in ["карта", "🗺️ карта"]:
        handled = True
        await update.message.reply_text("⚠️ <b>раздел карта временно недоступен!</b>", parse_mode='HTML')
        return
    elif text in ["помощь", "помощь ✅"]:  # обработка текстовой команды помощи
        handled = True
        await help_command(update, context)
        return
    elif text in ["топ", "🏆 топ", "топ 🏆", "🏆 топ ✅"]:
        handled = True
        await show_top_balance(update, context)
        return
    elif text in ["⚙️", "⚙️ ✅", "настройки"]:
        handled = True
        await show_settings(update, context)
        return

    # обработка кнопок меню настроек
    elif text == "основные" and context.user_data.get('in_settings'):
        handled = True
        await show_main_settings(update, context)
        return
    elif text == "уведомления" and context.user_data.get('in_settings'):
        handled = True
        await show_notifications_settings(update, context)
        return
    elif text == "⬅️ назад" and (context.user_data.get('in_main_settings') or context.user_data.get('in_notifications_settings')):
        handled = True
        if 'in_main_settings' in context.user_data:
            del context.user_data['in_main_settings']
        if 'in_notifications_settings' in context.user_data:
            del context.user_data['in_notifications_settings']
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
        
        if data.startswith("pb_"):
            from donations import handle_promo_builder_callback
            await handle_promo_builder_callback(update, context)
            return
        
        # обработка команд помощи
        if data == "help_admin_commands":
            # редактируем сообщение с админскими командами
            helpadm_text = """🔐 <b>админские команды</b>

<b>управление пользователями:</b>
/profile @username - посмотреть профиль пользователя
/ban @username [причина] - забанить пользователя
/unban @username - разбанить пользователя

<b>управление админами:</b>
/add_admin @username - добавить админа (только главный админ)
/remove_admin @username - снять админа (только главный админ)

<b>основные команды:</b>
/start - перезапустить бота
/me - главное меню
/help - помощь для пользователей
/helpadm - полная справка по админам

⚠️ <b>внимание:</b> будьте осторожны с баном пользователей!"""
            
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

<b>экономика:</b>
/pay @username сумма - перевести деньги другому игроку

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
            
            # получаем текущий пол и меняем на противоположный
            user_id = query.from_user.id
            user = get_user(user_id)
            current_gender = user[3] if len(user) > 3 else "male"
            new_gender = "female" if current_gender == "male" else "male"
            
            # меняем пол
            update_user_gender(user_id, new_gender)
            clear_character_cache(user_id)
            
            # отправляем уведомление
            gender_text = "мужской" if new_gender == "male" else "женский"
            await query.answer(f"✅ пол изменен на {gender_text}!")
            
            # обновляем настройки
            await show_main_settings(update, context)

        elif data == "settings_gender_male":
            user_id = query.from_user.id
            update_user_gender(user_id, "male")
            clear_character_cache(user_id)
            await query.answer("✅ пол изменен на мужской!")
            await show_main_settings(update, context)

        elif data == "settings_gender_female":
            user_id = query.from_user.id
            update_user_gender(user_id, "female")
            clear_character_cache(user_id)
            await query.answer("✅ пол изменен на женский!")
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
            user_id = query.from_user.id
            user = get_user(user_id)
            current_color = user[4] if len(user) > 4 else "black"
            new_color = "white" if current_color == "black" else "black"

            update_user_color(user_id, new_color)
            clear_character_cache(user_id)

            color_text = "черный" if new_color == "black" else "белый"
            await query.answer(f"✅ цвет кожи изменен на {color_text}!")
            await show_main_settings(update, context)

        elif data == "settings_color_black":
            user_id = query.from_user.id
            update_user_color(user_id, "black")
            clear_character_cache(user_id)
            await query.answer("✅ цвет изменен на черный!")
            await show_main_settings(update, context)

        elif data == "settings_color_white":
            user_id = query.from_user.id
            update_user_color(user_id, "white")
            clear_character_cache(user_id)
            await query.answer("✅ цвет изменен на белый!")
            await show_main_settings(update, context)

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
                        try:
                            await query.edit_message_text(
                                text=warning_text,
                                reply_markup=reply_markup,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            logger.error(f"Ошибка при редактировании предупреждения перевода: {e}")

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
            elif data in ["shop_acc_status", "shop_bg_disabled"]:
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
            elif data == "wardrobe_page_prev":
                page = context.user_data.get('wardrobe_page', 0) - 1
                await homes.show_wardrobe_page(update, context, page=page)
            elif data == "wardrobe_page_next":
                page = context.user_data.get('wardrobe_page', 0) + 1
                await homes.show_wardrobe_page(update, context, page=page)
            elif data == "wardrobe_refresh":
                await homes.show_wardrobe_page(update, context)
            elif data.startswith("wardrobe_slot_"):
                slot_num = int(data.replace("wardrobe_slot_", ""))
                await homes.handle_slot_click(update, context, slot_num)
            elif data.startswith("wardrobe_deposit_"):
                parts = data.split("_")
                slot_num = int(parts[2])
                acc_id = int(parts[3])
                await homes.deposit_accessory_to_slot(update, context, slot_num, acc_id)
            elif data.startswith("wardrobe_withdraw_"):
                slot_num = int(data.replace("wardrobe_withdraw_", ""))
                await homes.withdraw_accessory_from_slot(update, context, slot_num)
            elif data.startswith("wardrobe_toggle_lock_"):
                slot_num = int(data.replace("wardrobe_toggle_lock_", ""))
                await homes.toggle_slot_lock(update, context, slot_num)

        # обработка выбора типа аксессуара
        elif data.startswith("acc_type_"):
            from accessories import handle_acc_type_selection
            await handle_acc_type_selection(update, context)
        
        # обработка просмотра аксессуара и его действий
        elif data.startswith("acc_"):
            from accessories import handle_acc_view_details, handle_acc_buy, handle_acc_equip
            if data.startswith("acc_view_"):
                await handle_acc_view_details(update, context)
            elif data.startswith("acc_buy_"):
                await handle_acc_buy(update, context)
            elif data.startswith("acc_equip_"):
                await handle_acc_equip(update, context)
        
        # обработка просмотра фонов
        elif data.startswith("bg_"):
            from accessories import handle_bg_view_selection, handle_bg_buy, handle_bg_toggle
            if data.startswith("bg_view_"):
                await handle_bg_view_selection(update, context)
            elif data.startswith("bg_buy_"):
                await handle_bg_buy(update, context)
            elif data.startswith("bg_toggle_"):
                await handle_bg_toggle(update, context)
        
        # обработка домов
        elif data.startswith("homes_"):
            if data == "homes_next":
                await homes.handle_homes_navigation(update, context, "next")
            elif data == "homes_prev":
                await homes.handle_homes_navigation(update, context, "prev")
            elif data.startswith("homes_buy_"):
                try:
                    home_index = int(data.split("_")[2])
                    await homes.buy_home(update, context, home_index)
                except (ValueError, IndexError):
                    await query.answer("❌ ошибка при покупке дома", show_alert=True)
            elif data == "homes_no_money":
                await query.answer("❌ у вас недостаточно денег для этого", show_alert=True)

        elif data.startswith("home_"):
            if data == "home_menu_return":
                await homes.show_home_menu(update, context)
            elif data == "home_toggle_bg":
                await homes.toggle_home_background(update, context)
            elif data == "home_sell_confirm":
                await homes.sell_home(update, context)
            elif data == "home_settings":
                await homes.show_home_settings(update, context)
            elif data == "home_roommates_manage":
                await homes.manage_roommates(update, context)
            elif data.startswith("home_evict_"):
                roommate_id = int(data.replace("home_evict_", ""))
                await homes.evict_roommate(update, context, roommate_id)

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

        elif data == "settings_toggle_gun":
            user_id = query.from_user.id
            gun_id = get_accessory_id_by_name("пистолет")
            if gun_id:
                equipped = is_accessory_equipped(user_id, gun_id)
                if equipped:
                    unequip_accessory(user_id, "hand")
                    await query.answer("🔫 пистолет снят!", show_alert=True)
                else:
                    equip_accessory(user_id, gun_id)
                    await query.answer("🔫 пистолет надет!", show_alert=True)
                clear_character_cache(user_id)
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

        elif data == "notifications_toggle_referral":
            user_id = query.from_user.id
            current = is_referral_notifications_disabled(user_id)
            new_value = not current
            update_user_disable_referral_notifications(user_id, new_value)
            status = "отключены" if new_value else "включены"
            await query.answer(f"✅ уведомления о мамонтах {status}!")
            await show_notifications_settings(update, context)

        elif data == "settings_back":
            await show_main_menu(update, context)

        elif data == "refresh_top_balance" or data == "top_balance":
            await show_top_balance(update, context)

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
            elif data in ["shop_acc_status", "shop_bg_disabled"]:
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
        
        # обработка выбора типа аксессуара
        elif data.startswith("acc_type_"):
            from accessories import handle_acc_type_selection
            await handle_acc_type_selection(update, context)
        
        # обработка просмотра аксессуара и его действий
        elif data.startswith("acc_"):
            from accessories import handle_acc_view_details, handle_acc_buy, handle_acc_equip
            if data.startswith("acc_view_"):
                await handle_acc_view_details(update, context)
            elif data.startswith("acc_buy_"):
                await handle_acc_buy(update, context)
            elif data.startswith("acc_equip_"):
                await handle_acc_equip(update, context)
        
        # обработка раздачи футболки
        elif data in ["claim_tshirt_distribution", "refresh_tshirt_distribution", "already_claimed_tshirt", "back_to_main_menu"]:
            if data == "claim_tshirt_distribution":
                await claim_tshirt_distribution(update, context)
            elif data == "refresh_tshirt_distribution":
                await show_tshirt_distribution_menu(update, context)
            elif data == "already_claimed_tshirt":
                await query.answer("ты уже забрал эту футболку!", show_alert=True)
            elif data == "back_to_main_menu":
                from main_menu import show_main_menu
                await show_main_menu(update, context)

        # обработка просмотров фонов
        elif data.startswith("bg_"):
            from accessories import handle_bg_view_selection, handle_bg_buy, handle_bg_toggle
            if data.startswith("bg_view_"):
                await handle_bg_view_selection(update, context)
            elif data.startswith("bg_buy_"):
                await handle_bg_buy(update, context)
            elif data.startswith("bg_toggle_"):
                await handle_bg_toggle(update, context)
        

        
        # обработка домов и шкафа
        elif data.startswith("homes_"):
            if data == "homes_next":
                await homes.handle_homes_navigation(update, context, "next")
            elif data == "homes_prev":
                await homes.handle_homes_navigation(update, context, "prev")
            elif data.startswith("homes_buy_"):
                try:
                    home_index = int(data.split("_")[2])
                    await homes.buy_home(update, context, home_index)
                except (ValueError, IndexError):
                    await query.answer("❌ ошибка при покупке дома", show_alert=True)
            elif data == "homes_no_money":
                await query.answer("❌ у вас недостаточно денег для этого", show_alert=True)

        elif data.startswith("home_"):
            if data == "home_menu_return":
                await homes.show_home_menu(update, context)
            elif data == "home_toggle_bg":
                await homes.toggle_home_background(update, context)
            elif data == "home_sell_confirm":
                await homes.sell_home(update, context)
            elif data == "home_settings":
                await homes.show_home_settings(update, context)
            elif data == "home_roommates_manage":
                await homes.manage_roommates(update, context)
            elif data.startswith("home_evict_"):
                roommate_id = int(data.replace("home_evict_", ""))
                await homes.evict_roommate(update, context, roommate_id)

        elif data.startswith("wardrobe_"):
            if data == "wardrobe_menu":
                await show_wardrobe_menu(update, context)
            elif data == "wardrobe_accessories":
                await show_accessories_shop(update, context)
            elif data == "wardrobe_backgrounds":
                await show_backgrounds_shop(update, context)
            elif data == "wardrobe_page_prev":
                page = context.user_data.get('wardrobe_page', 0) - 1
                await homes.show_wardrobe_page(update, context, page=page)
            elif data == "wardrobe_page_next":
                page = context.user_data.get('wardrobe_page', 0) + 1
                await homes.show_wardrobe_page(update, context, page=page)
            elif data == "wardrobe_refresh":
                await homes.show_wardrobe_page(update, context)
            elif data.startswith("wardrobe_slot_"):
                slot_num = int(data.replace("wardrobe_slot_", ""))
                await homes.handle_slot_click(update, context, slot_num)
            elif data.startswith("wardrobe_deposit_"):
                parts = data.split("_")
                slot_num = int(parts[2])
                acc_id = int(parts[3])
                await homes.deposit_accessory_to_slot(update, context, slot_num, acc_id)
            elif data.startswith("wardrobe_withdraw_"):
                slot_num = int(data.replace("wardrobe_withdraw_", ""))
                await homes.withdraw_accessory_from_slot(update, context, slot_num)
            elif data.startswith("wardrobe_toggle_lock_"):
                slot_num = int(data.replace("wardrobe_toggle_lock_", ""))
                await homes.toggle_slot_lock(update, context, slot_num)
        
        # обработка бизнеса (временно закрыт)
        elif data.startswith("business_"):
            await query.answer("⚠️ раздел бизнесы временно недоступен!", show_alert=True)
        
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    
    print("👑 проверка главного админа...")
    # создаем главного админа при первом запуске
    user = get_user(MAIN_ADMIN_ID)
    if not user:
        print("👑 создание главного админа...")
        user_data = (
            MAIN_ADMIN_ID,
            "xylibaba",  # временный username
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
    set_global_bot(application.bot)

    print("📋 регистрация обработчиков...")
    # обработчики
    application.add_handler(CommandHandler("start", start_wrapper))
    application.add_handler(CommandHandler("me", me_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("helpadm", helpadm_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("pay", transfer_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("donations", donations_command))
    application.add_handler(CommandHandler("news", news_command, filters=filters.ALL))
    application.add_handler(CommandHandler("onews", onews_command, filters=filters.ALL))
    application.add_handler(CommandHandler("top", show_top_balance))
    application.add_handler(CommandHandler(["addpromo", "createpromo"], addpromo_command))
    application.add_handler(CommandHandler(["promos", "promolist"], promos_list_command))
    application.add_handler(CommandHandler("delpromo", delpromo_command))
    
    # обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    
    # обработчик неизвестных команд должен быть последним
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text_messages_wrapper))
    
    application.add_error_handler(error_handler)
    
    # Регистрируем фоновую задачу для проверки крипто-платежей каждые 30 секунд
    job_queue = application.job_queue
    job_queue.run_repeating(check_all_pending_crypto_payments, interval=30, first=5)
    job_queue.run_repeating(process_gangster_plus_weekly_payouts, interval=3600, first=10)
    
    print("✅ бот запущен и готов к работе!")
    print("📱 теперь иди в telegram и напиши /start боту")
    
    # запускаем бота без лишних логов
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
