import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import sqlite3
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, DB_PATH
from utils import format_money, get_global_bot, maybe_send_channel_reminder

# Показать меню скама со статистикой реферала
async def show_scam_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await maybe_send_channel_reminder(update, context)
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:
        return
    
    # Инвалидируем предыдущие сообщения меню работы - заголовок
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
    
    # Инвалидируем меню работы - удаляем кнопки из сообщения с доступными работами
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
    
    # Инвалидируем предыдущие сообщения работы
    if 'shit_cleaner_message_id' in context.user_data and 'shit_cleaner_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['shit_cleaner_chat_id'],
                message_id=context.user_data['shit_cleaner_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['shit_cleaner_message_id']
        del context.user_data['shit_cleaner_chat_id']
    
    if 'milker_message_id' in context.user_data and 'milker_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['milker_chat_id'],
                message_id=context.user_data['milker_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['milker_message_id']
        del context.user_data['milker_chat_id']
    
    nickname = user[2]
    username = user[1]
    
    # Получаем статистику реферала
    referral_stats = get_referral_stats(user_id)
    referrals_count = referral_stats['referrals_count']
    referral_earnings = referral_stats['earnings']
    
    # Создаем реф ссылку
    ref_link = f"https://t.me/gangster77_bot?start={user_id}"
    
    message_text = f"""ты находишься в скам меню

🦣 <b>сколько заскамлено мамонтов:</b> {referrals_count}
💰 <b>заработано:</b> {format_money(referral_earnings)}

🔗 <b>ссылка:</b>
<code>{ref_link}</code>"""
    
    # Reply-клавиатура с кнопками "инструкция" и "назад"
    keyboard = [
        [KeyboardButton("инструкция"), KeyboardButton("назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Отправляем сообщение с фото если оно существует
    photo_file = 'images/scam_work.jpg'
    if os.path.exists(photo_file):
        try:
            with open(photo_file, 'rb') as photo:
                message = await update.message.reply_photo(
                    photo=photo,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        except Exception:
            # Если ошибка при отправке фото - отправляем только текст
            message = await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        # Если фото не найдено - отправляем только текст
        message = await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    
    # Сохраняем id сообщения
    if message:
        context.user_data['scam_message_id'] = message.message_id
        context.user_data['scam_chat_id'] = message.chat_id

# Получить статистику реферала
def get_referral_stats(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT referrals_count, total_referral_earnings FROM referral_stats WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            return {
                'referrals_count': result[0],
                'earnings': result[1]
            }
        else:
            return {
                'referrals_count': 0,
                'earnings': 0
            }
    except Exception as e:
        return {
            'referrals_count': 0,
            'earnings': 0
        }
    finally:
        conn.close()

# Инициализировать статистику реферала для нового пользователя
def init_referral_stats(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT OR IGNORE INTO referral_stats (user_id, referrals_count, total_referral_earnings) VALUES (?, 0, 0)', (user_id,))
        conn.commit()
    except Exception as e: pass
    finally:
        conn.close()

def safe_trigger_async(coro):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass

async def notify_referral_registered(referrer_id, new_user_id, bot=None):
    """Отправить уведомление рефэру о том, что мамонт зарегистрировался по его ссылке"""
    try:
        from registration import is_referral_notifications_disabled, get_user
        if is_referral_notifications_disabled(referrer_id):
            return
        
        bot_inst = bot or get_global_bot()
        if not bot_inst:
            return
            
        new_user = get_user(new_user_id)
        if not new_user:
            return
            
        nickname = new_user[2] if len(new_user) > 2 else "игрок"
        profile_link = f'<a href="tg://user?id={new_user_id}"><b>{nickname}</b></a>'
        
        text = (
            f"🦣 <b>новый мамонт зарегистрировался по твоей реферальной ссылке!</b>\n\n"
            f"игрок {profile_link} теперь твой мамонт.\n"
            f"ты будешь получать <b>50%</b> от его заработка на работах и донатах!"
        )
        
        await bot_inst.send_message(chat_id=referrer_id, text=text, parse_mode='HTML')
    except Exception as e:
        print(f"⚠️ не удалось отправить уведомление о реферале {referrer_id}: {e}")

async def notify_referral_earnings(referrer_id, referral_user_id, referral_amount, source="работа", bot=None):
    """Отправить уведомление рефэру о заработке с мамонта"""
    try:
        from registration import is_referral_notifications_disabled, get_user
        if is_referral_notifications_disabled(referrer_id):
            return
            
        bot_inst = bot or get_global_bot()
        if not bot_inst:
            return
            
        referral_user = get_user(referral_user_id)
        if not referral_user:
            return
            
        nickname = referral_user[2] if len(referral_user) > 2 else "игрок"
        profile_link = f'<a href="tg://user?id={referral_user_id}"><b>{nickname}</b></a>'
        
        text = (
            f"💰 <b>доход от мамонта!</b>\n\n"
            f"твой мамонт {profile_link} принес тебе доход ({source})!\n"
            f"твой доход: <b>+{format_money(referral_amount)}</b>"
        )
        
        await bot_inst.send_message(chat_id=referrer_id, text=text, parse_mode='HTML')
    except Exception as e:
        print(f"⚠️ не удалось отправить уведомление о доходе {referrer_id}: {e}")

# Обработать регистрацию рефлинка (увеличить счетчик рефералов)
def handle_referral_registration(referrer_id, new_user_id):
    """Обработать регистрацию нового реферала"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Сохраняем referrer_id для нового пользователя
        cursor.execute('UPDATE users SET referrer_id = ? WHERE user_id = ?', (referrer_id, new_user_id))
        
        # Инициализируем статистику реферала для нового пользователя
        cursor.execute('INSERT OR IGNORE INTO referral_stats (user_id, referrals_count, total_referral_earnings) VALUES (?, 0, 0)', (new_user_id,))
        
        # Инициализируем статистику реферала для реффера, если её нет
        cursor.execute('INSERT OR IGNORE INTO referral_stats (user_id, referrals_count, total_referral_earnings) VALUES (?, 0, 0)', (referrer_id,))
        
        # Увеличиваем счетчик рефералов
        cursor.execute('''
            UPDATE referral_stats 
            SET referrals_count = referrals_count + 1 
            WHERE user_id = ?
        ''', (referrer_id,))
        
        conn.commit()
        safe_trigger_async(notify_referral_registered(referrer_id, new_user_id))
    except Exception as e: pass
    finally:
        conn.close()

# Добавить заработок от доната рефэру
async def add_referral_donation_earnings(donor_user_id, donation_amount):
    """Добавить 50% от доната рефэру донатера"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Получаем referrer_id донатера
        cursor.execute('SELECT referrer_id FROM users WHERE user_id = ?', (donor_user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:  # Если есть реферер
            referrer_id = result[0]
            referral_amount = int(donation_amount * 0.5)  # 50% от доната
            
            # Добавляем деньги рефэру
            update_user_money(referrer_id, referral_amount)
            
            # Добавляем к его заработкам от рефералов
            cursor.execute('''
                UPDATE referral_stats 
                SET total_referral_earnings = total_referral_earnings + ? 
                WHERE user_id = ?
            ''', (referral_amount, referrer_id))
            
            conn.commit()
            from registration import log_financial_transaction
            log_financial_transaction(referrer_id, "referral_earn", referral_amount, "доход от доната мамонта")
            print(f"✅ рефэру {referrer_id} добавлено {format_money(referral_amount)} от доната {donor_user_id}")
            safe_trigger_async(notify_referral_earnings(referrer_id, donor_user_id, referral_amount, source="донат"))
            return True
    except Exception as e:
        print(f"⚠️ Ошибка добавления заработка от доната: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    return False

# Добавить заработок от работы рефэру
def add_referral_job_earnings(employee_user_id, job_earnings):
    """Добавить 50% от заработка на работе рефэру сотрудника"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Получаем referrer_id сотрудника
        cursor.execute('SELECT referrer_id FROM users WHERE user_id = ?', (employee_user_id,))
        result = cursor.fetchone()
        
        if result and result[0]:  # Если есть реферер
            referrer_id = result[0]
            referral_amount = int(job_earnings * 0.5)  # 50% от заработка
            
            # Добавляем деньги рефэру
            update_user_money(referrer_id, referral_amount)
            
            # Добавляем к его заработкам от рефералов
            cursor.execute('''
                UPDATE referral_stats 
                SET total_referral_earnings = total_referral_earnings + ? 
                WHERE user_id = ?
            ''', (referral_amount, referrer_id))
            
            conn.commit()
            from registration import log_financial_transaction
            log_financial_transaction(referrer_id, "referral_earn", referral_amount, "доход от работы мамонта")
            print(f"✅ рефэру {referrer_id} добавлено {format_money(referral_amount)} от заработка {employee_user_id}")
            safe_trigger_async(notify_referral_earnings(referrer_id, employee_user_id, referral_amount, source="работа"))
            return True
    except Exception as e:
        print(f"⚠️ Ошибка добавления заработка от работы: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    return False

# Показать инструкцию для скама
async def show_scam_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instruction_text = """🎓 <b>инструкция по скаму</b>

<b>как маскировать ссылку в телеграме:</b>

1️⃣ <b>использование форматирования:</b>
   используй <code>[текст](ссылка)</code> чтобы замаскировать ссылку
   пример: <code>[нажми для приза](твоя_ссылка)</code>

2️⃣ <b>html теги:</b>
   ты можешь использовать HTML теги в сообщениях
   пример: <code>&lt;a href="твоя_ссылка"&gt;нажми здесь&lt;/a&gt;</code>

3️⃣ <b>короткие ссылки:</b>
   используй сервисы сокращения ссылок (bit.ly, tinyurl)
   это делает ссылку менее подозрительной

4️⃣ <b>контекст:</b>
   преподноси ссылку в интересном контексте
   например: "выиграй деньги", "получи бонус", "проверь свой рейтинг"

5️⃣ <b>социальная инженерия:</b>
   создавай срочность: "предложение действительно только 24 часа!"
   используй фото и видео для убедительности
   ссылайся на известные бренды или участников

⚠️ <b>важно:</b>
   помни, что скам - это всегда риск для репутации
   телеграм активно борется с мошенничеством
   используй это знание ответственно!"""
    
    keyboard = [
        [KeyboardButton("назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    message = await update.message.reply_text(
        instruction_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # сохраняем id сообщения инструкции
    if message:
        context.user_data['scam_instruction_message_id'] = message.message_id
        context.user_data['scam_instruction_chat_id'] = message.chat_id
