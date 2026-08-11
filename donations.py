import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import logging
import sqlite3
import os
import time
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from registration import get_user, update_user_money
from utils import safe_delete_message, format_money, maybe_send_channel_reminder
from scam import add_referral_donation_earnings

# загружаем переменные окружения
load_dotenv()

# настройка логгера
logger = logging.getLogger(__name__)

# ==========================================
# Глобальное хранилище ожидающих крипто-платежей
# ==========================================
# Структура: {user_id: {pack_index: {invoice_id, created_at, message_id, chat_id}}}
pending_crypto_payments = {}

# ==========================================
# 🔑 настройки платежных систем
# ==========================================

# 1. crypto bot
# 🔐 загружаем из .env файла
crypto_bot_token = os.getenv("CRYPTO_BOT_TOKEN", "")

# 2. telegram payment provider (для Telegram Stars provider_token не требуется - передается пустая строка "")

# ==========================================

# конфигурация наборов
packs = [
    {
        "id": "molodoy",
        "title": "📦 молодой",
        "description": "• 👕 скин «молодой» (одевается сразу, снимается дома)\n• 💰 10.000.000$\n• ⚡️ х2 со всего заработка на 24 часа",
        "price_stars": 44,
        "price_crypto": 1.0,
        "reward_money": 10000000,
        "is_subscription": False,
        "photo": "images/donation_1.jpg"
    },
    {
        "id": "gangster_plus",
        "title": "💎 гангстер плюс",
        "description": "• 💬 VIP-чат с админами\n• ⚡️ х4 прибыль со всех работ\n• 💎 алмаз около ника\n• 💰 5.000.000$ каждую неделю (автоматически)\n\n💡 <i>наполнение подписки будет меняться в лучшую сторону!</i>\n✨ <i>все действует пока активна подписка (1 месяц)</i>",
        "price_stars": 65,
        "price_crypto": 1.5,
        "reward_money": 0,
        "is_subscription": True,
        "photo": "images/donation_2.jpg"
    }
]

def get_main_admin_chat_link():
    """Получает ссылку на чат с главным админом (@gangstermgr)"""
    return "https://t.me/gangstermgr"

# меню донатов (карусель)
async def show_donation_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await maybe_send_channel_reminder(update, context)
    user_id = update.effective_user.id
    
    # по умолчанию первый набор
    current_pack_index = 0
    context.user_data['current_pack_index'] = current_pack_index
    context.user_data['in_donation_menu'] = True
    
    # Reply клавиатура доната: кнопки "🎁 промокод" и "назад"
    reply_keyboard = [
        [KeyboardButton("🎁 промокод"), KeyboardButton("назад")]
    ]
    reply_markup_reply = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    chat_id = update.effective_chat.id if update and update.effective_chat else user_id
    if update.message:
        await update.message.reply_text(
            "💎 <b>раздел доната</b>",
            parse_mode='HTML',
            reply_markup=reply_markup_reply
        )
    elif update.callback_query:
        await context.bot.send_message(
            chat_id=chat_id,
            text="💎 <b>раздел доната</b>",
            parse_mode='HTML',
            reply_markup=reply_markup_reply
        )
    
    await show_pack(update, context, current_pack_index)

async def show_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int):
    user_id = update.effective_user.id
    pack = packs[index]
    
    has_plus = is_gangster_plus_active(user_id) if pack['is_subscription'] else False
    
    text = (
        f"<b>{pack['title']}</b>\n\n"
        f"{pack['description']}\n\n"
        f"💰 цена: <b>{pack['price_stars']} ⭐️</b> или <b>{pack['price_crypto']}$ (crypto)</b>"
    )
    if has_plus:
        text += "\n\n✅ <b>у вас активна эта подписка!</b>"

    buy_button_text = "уже куплено" if has_plus else "купить"

    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="pack_prev"),
            InlineKeyboardButton(buy_button_text, callback_data=f"pack_buy_{index}"),
            InlineKeyboardButton("➡️", callback_data="pack_next")
        ]
    ]
    if has_plus:
        keyboard.append([InlineKeyboardButton("💬 VIP-чат с админами", url=get_main_admin_chat_link())])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            # пытаемся обновить подпись, если это сообщение с фото
            await update.callback_query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode='html')
        except Exception:
            # если ошибка (например, сообщение без фото), удаляем и шлем новое
            await safe_delete_message(context, update.effective_chat.id, update.callback_query.message.message_id)
            try:
                with open(pack['photo'], 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
            except FileNotFoundError:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='html'
                )
    else:
        try:
            with open(pack['photo'], 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='html'
                )
        except FileNotFoundError:
            await update.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='html'
            )

# навигация по наборам
async def handle_pack_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    current_index = context.user_data.get('current_pack_index', 0)
    
    if data == "pack_prev":
        current_index = (current_index - 1) % len(packs)
    elif data == "pack_next":
        current_index = (current_index + 1) % len(packs)
        
    context.user_data['current_pack_index'] = current_index
    await show_pack(update, context, current_index)

# выбор способа оплаты
async def handle_buy_pack_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            logger.warning(f"Invalid pack_buy data format: {query.data}")
            return
        try:
            index = int(parts[-1])
        except ValueError:
            logger.warning(f"Could not parse pack index: {parts[-1]}")
            return
            
        if not (0 <= index < len(packs)):
            logger.warning(f"Invalid pack index: {index}")
            return
    except Exception as e:
        logger.warning(f"Error parsing pack_buy data: {e}")
        return
    
    pack = packs[index]
    
    # Проверяем, не куплен ли уже пакет подписки
    if pack['is_subscription'] and is_gangster_plus_active(user_id):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ <b>у вас уже активна эта подписка!</b>",
            parse_mode='html'
        )
        return
    
    text = (
        f"💳 <b>оплата: {pack['title']}</b>\n\n"
        f"выберите способ оплаты:"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"⭐️ telegram stars ({pack['price_stars']} зв.)", callback_data=f"pay_stars_{index}")],
        [InlineKeyboardButton(f"💎 crypto bot ({pack['price_crypto']}$)", callback_data=f"pay_crypto_{index}")],
        [InlineKeyboardButton("назад", callback_data="pack_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode='html')
    except Exception:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='html')

# возврат к выбору набора
async def handle_back_to_packs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_index = context.user_data.get('current_pack_index', 0)
    await show_pack(update, context, current_index)

# запуск оплаты stars
async def start_pack_stars_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            logger.warning(f"Invalid stars payment data format: {query.data}")
            return
        
        try:
            index = int(parts[-1])
        except ValueError:
            logger.warning(f"Could not parse pack index from: {parts[-1]}")
            return
        
        if not (0 <= index < len(packs)):
            logger.warning(f"Invalid pack index: {index}")
            return
        
        pack = packs[index]
        
        # Для Telegram Stars используем целые числа
        price = int(pack['price_stars']) if isinstance(pack['price_stars'], (int, float)) else 1
        prices = [LabeledPrice(pack['title'], price)]
        
        try:
            message = await context.bot.send_invoice(
                chat_id=update.effective_chat.id,
                title=pack['title'][:32],
                description=pack['description'][:255],
                payload=f"pack_{index}",
                provider_token="",
                currency="XTR",
                prices=prices
            )
            # Сохраняем ID сообщения со счётом
            context.user_data['stars_invoice_message_id'] = message.message_id
            context.user_data['pending_pack_index'] = index  # Сохраняем индекс пакета для обработки платежа
            logger.info(f"Stars invoice sent for user {user_id}, pack {index}")
            
            # Отправляем пользователю информационное сообщение
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⭐️ <b>счет отправлен</b>\n\n✅ нажмите на счет выше чтобы оплатить",
                parse_mode='html'
            )
        except Exception as e:
            logger.error(f"Error sending stars invoice for user {user_id}: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ <b>ошибка отправки счёта</b>\n\n{str(e)}",
                parse_mode='html'
            )
            return
    except Exception as e:
        logger.error(f"Error in start_pack_stars_payment for user {user_id}: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ <b>ошибка</b>\n\n{str(e)}",
                parse_mode='html'
            )
        except:
            logger.error(f"Could not send error message to user {user_id}")

# запуск оплаты crypto bot
async def start_pack_crypto_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            logger.warning(f"Invalid crypto payment data format: {query.data}")
            return
        
        try:
            index = int(parts[-1])
        except ValueError:
            logger.warning(f"Could not parse pack index from: {parts[-1]}")
            return
        
        if not (0 <= index < len(packs)):
            logger.warning(f"Invalid pack index: {index}")
            return
    except (ValueError, IndexError) as e:
        logger.warning(f"Error parsing crypto payment data: {e}")
        return
    
    pack = packs[index]
    
    if not crypto_bot_token or crypto_bot_token == "вставить_токен_сюда":
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ <b>криптобот не настроен</b>\n\nАдминистратор должен установить токен Crypto Bot",
            parse_mode='html'
        )
        return

    try:
        
        # Используем правильный URL для Crypto Bot API
        url = "https://pay.crypt.bot/api/createInvoice"
        headers = {"Crypto-Pay-API-Token": crypto_bot_token}
        payload_data = {
            "asset": "USDT",
            "amount": str(round(float(pack['price_crypto']), 2)),
            "description": pack['title'][:255]
        }
        
        logger.info(f"Sending crypto request to {url}: {payload_data}")
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers=headers, json=payload_data)
            logger.info(f"Crypto response status: {response.status_code}")
            logger.info(f"Crypto response: {response.text}")
            
            result = response.json()
            
            if result.get("ok") and result.get("result"):
                invoice_url = result["result"].get("bot_invoice_url")
                invoice_id = result["result"].get("invoice_id")
                
                if invoice_url:
                    # Сохраняем информацию о платеже для автоматической проверки в глобальное хранилище
                    if user_id not in pending_crypto_payments:
                        pending_crypto_payments[user_id] = {}
                    
                    pending_crypto_payments[user_id][index] = {
                        'invoice_id': invoice_id,
                        'pack_index': index,
                        'user_id': user_id,
                        'created_at': time.time(),
                        'check_count': 0
                    }
                    
                    # Отправляем просто со ссылкой (без кнопки проверки)
                    keyboard = [
                        [InlineKeyboardButton("💎 оплатить", url=invoice_url)]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    message = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"<b>счет для оплаты:</b>\n\n{invoice_url}\n\n💡 <i>статус будет обновлен автоматически после оплаты</i>",
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
                    # Сохраняем информацию о сообщении для обновления
                    pending_crypto_payments[user_id][index]['message_id'] = message.message_id
                    pending_crypto_payments[user_id][index]['chat_id'] = update.effective_chat.id
                    logger.info(f"Crypto invoice created for user {user_id}, invoice_id={invoice_id}, waiting for auto-check")
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ <b>ошибка</b>\n\nНет ссылки для оплаты в ответе",
                        parse_mode='html'
                    )
            else:
                error_msg = result.get('error', {}).get('name', 'Unknown error')
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ <b>ошибка криптобота</b>\n\n{error_msg}",
                    parse_mode='html'
                )
                logger.error(f"Crypto API error for user {user_id}: {result}")
    except Exception as e:
        logger.error(f"Crypto bot error for user {user_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ <b>ошибка соединения</b>\n\n{str(e)}",
            parse_mode='html'
        )

# pre-checkout handler
async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload
    
    logger.info(f"Pre-checkout query from {update.effective_user.id}: payload={payload}")
    
    if payload.startswith("pack_"):
        try:
            parts = payload.split("_")
            if len(parts) < 2:
                await query.answer(ok=False, error_message="Invalid payload")
                return
            index = int(parts[-1])
            if 0 <= index < len(packs):
                await query.answer(ok=True)
            else:
                await query.answer(ok=False, error_message="Invalid pack")
        except (ValueError, IndexError):
            await query.answer(ok=False, error_message="Invalid payload")
    else:
        await query.answer(ok=False, error_message="Unknown payload")

# обработка успешного платежа
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        payment = update.message.successful_payment
        user_id = update.effective_user.id
        payload = payment.invoice_payload
        
        logger.info(f"Payment received from {user_id}: payload={payload}, amount={payment.total_amount}, currency={payment.currency}")
        
        amount_paid = payment.total_amount
        currency = payment.currency
        
        # Удаляем старое сообщение со счётом/кнопкой
        try:
            if 'stars_invoice_message_id' in context.user_data:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['stars_invoice_message_id']
                )
                del context.user_data['stars_invoice_message_id']
        except Exception as e:
            logger.warning(f"Could not delete stars invoice message: {e}")
        
        # Также удаляем crypto сообщение если оно было
        try:
            if 'crypto_invoice_message_id' in context.user_data:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['crypto_invoice_message_id']
                )
                del context.user_data['crypto_invoice_message_id']
        except Exception as e:
            logger.warning(f"Could not delete crypto invoice message: {e}")
        
        if payload.startswith("pack_"):
            try:
                index = int(payload.split("_")[-1])
                if 0 <= index < len(packs):
                    pack = packs[index]
                    success_msg = await apply_pack_rewards(user_id, index)
                    await update.message.reply_text(success_msg, parse_mode='html')
                    
                    # Определяем payment_system
                    payment_system = "telegram_stars" if currency.upper() == "XTR" else "crypto_bot"
                    add_donation(user_id, amount_paid, currency, payment_system, "completed")
                    logger.info(f"Pack payment processed: user={user_id}, pack={index}, system={payment_system}")
                else:
                    logger.error(f"Invalid pack index: {index}")
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing pack payload: {e}")
        else:
            logger.warning(f"Unknown payload format: {payload}")
    except Exception as e:
        logger.error(f"Error processing payment: {e}", exc_info=True)
        await update.message.reply_text("⚠️ ошибка обработки платежа")

# ... (остальные функции)

# функция добавления записи о донате в бд
def add_donation(user_id, amount, currency, payment_system, status):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            insert into donations (user_id, amount, currency, payment_system, status)
            values (?, ?, ?, ?, ?)
        ''', (user_id, amount, currency, payment_system, status))
        
        conn.commit()
    except Exception as e:
        print(f"⚠️ Ошибка добавления доната: {e}")
        conn.rollback()
    finally:
        conn.close()

def activate_gangster_plus(user_id):
    try:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Проверяем что пользователь существует
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            logger.warning(f"User {user_id} not found for gangster_plus activation")
            conn.close()
            return False
        
        cursor.execute("UPDATE users SET is_gangster_plus = TRUE WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.info(f"Gangster plus activated for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error activating gangster plus for {user_id}: {e}")
        return False
    finally:
        conn.close()

def is_gangster_plus_active(user_id):
    """Проверяет, активна ли подписка гангстер плюс"""
    try:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT is_gangster_plus FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else False
    except Exception as e:
        logger.error(f"Error checking gangster plus status: {e}")
        return False

# проверка платежа Crypto Bot по invoice_id
async def check_crypto_payment_status(user_id: int, invoice_id: str, pack_index: int, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет статус платежа в Crypto Bot по invoice_id"""
    if not crypto_bot_token or crypto_bot_token == "вставить_токен_сюда":
        logger.error("Crypto bot token not configured")
        return False
    
    try:
        url = "https://pay.crypt.bot/api/getInvoices"
        headers = {"Crypto-Pay-API-Token": crypto_bot_token}
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            logger.debug(f"Crypto status check response: {response.status_code}")
            
            result = response.json()
            
            if result.get("ok") and result.get("result"):
                invoices = result["result"].get("items", [])
                
                # Ищем счет с нужным ID
                for invoice in invoices:
                    if invoice.get("invoice_id") == invoice_id and invoice.get("status") == "paid":
                        # Платеж найден и оплачен!
                        amount_paid = invoice.get("paid_amount", 0)
                        
                        # Получаем информацию для отправки уведомления
                        global pending_crypto_payments
                        bot = context.bot
                        chat_id = None
                        message_id = None
                        
                        if user_id in pending_crypto_payments and pack_index in pending_crypto_payments[user_id]:
                            payment_info = pending_crypto_payments[user_id][pack_index]
                            chat_id = payment_info.get('chat_id')
                            message_id = payment_info.get('message_id')
                        
                        # Обрабатываем платеж
                        return await process_payment(user_id, pack_index, amount_paid, "USDT", bot, chat_id, message_id)
        
        logger.debug(f"Invoice {invoice_id} not found or not paid")
        return False
    
    except Exception as e:
        logger.error(f"Error checking crypto payment: {e}", exc_info=True)
        return False

async def apply_pack_rewards(user_id: int, pack_index: int) -> str:
    """Выдает все награды за покупку пакета и возвращает текст успеха"""
    if not (0 <= pack_index < len(packs)):
        return "⚠️ Неизвестный пакет"
    
    pack = packs[pack_index]
    
    if pack['is_subscription']:
        activate_gangster_plus(user_id)
        now = time.time()
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT gangster_plus_until FROM users WHERE user_id = ?', (user_id,))
            res = cursor.fetchone()
            current_until = res[0] if res and res[0] else 0.0
            new_until = max(now, current_until) + (30 * 86400)
            
            # Выдаем 5кк бонус при покупке и обновляем таймеры
            update_user_money(user_id, 5000000)
            cursor.execute('UPDATE users SET gangster_plus_until = ?, last_plus_weekly_payout = ? WHERE user_id = ?', (new_until, now, user_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Error setting gangster_plus subscription time: {e}")
        finally:
            conn.close()

        return (
            f"✅ <b>покупка успешна!</b>\n\n"
            f"<b>{pack['title']}</b> подписка активирована на 30 дней!\n\n"
            f"вам доступно:\n"
            f"• 💬 VIP-чат с админами\n"
            f"• ⚡️ х4 прибыль на работах\n"
            f"• 💎 алмаз около ника\n"
            f"• 💰 5.000.000$ (первый еженедельный бонус начислен!)\n\n"
            f"<i>💡 наполнение подписки будет меняться в лучшую сторону!</i>\n"
            f"спасибо за поддержку бота!"
        )
    else:
        # Набор Молодой (pack_index == 0)
        reward = pack['reward_money']
        update_user_money(user_id, reward)
        await add_referral_donation_earnings(user_id, reward)
        
        # Выдаем и автоматически одеваем скин молодой
        from accessories import give_user_molodoy_accessory
        from registration import add_user_2x_boost
        
        give_user_molodoy_accessory(user_id)
            
        # Активируем х2 со всего заработка на 24 часа
        add_user_2x_boost(user_id, 86400)
        
        return (
            f"✅ <b>покупка успешна!</b>\n\n"
            f"<b>{pack['title']}</b>\n"
            f"• начислено: <b>{format_money(reward)}</b>\n"
            f"• выдан и автоматически надет скин <b>«молодой»</b> (снимается в шкафу дома)!\n"
            f"• ⚡️ <b>х2 со всего заработка</b> активирован на 24 часа!\n\n"
            f"спасибо за поддержку бота!"
        )

async def process_payment(user_id: int, pack_index: int, amount_paid: float, currency: str, bot=None, chat_id=None, message_id=None):
    """Обрабатывает платеж и активирует пакет"""
    try:
        if not (0 <= pack_index < len(packs)):
            logger.error(f"Invalid pack index: {pack_index}")
            return False
        
        pack = packs[pack_index]
        success_msg = await apply_pack_rewards(user_id, pack_index)
        
        add_donation(user_id, int(amount_paid * 100), currency, "crypto_bot", "completed")
        logger.info(f"Payment processed: user={user_id}, pack={pack_index}")
        
        # Отправляем уведомление о успешном платеже пользователю
        if bot and chat_id:
            try:
                if message_id:
                    # Обновляем сообщение со счетом
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=success_msg,
                            parse_mode='html'
                        )
                    except Exception as e:
                        logger.warning(f"Could not update message {message_id}: {e}")
                        # Если не можем обновить - отправляем новое
                        await bot.send_message(
                            chat_id=chat_id,
                            text=success_msg,
                            parse_mode='html'
                        )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=success_msg,
                        parse_mode='html'
                    )
            except Exception as e:
                logger.error(f"Error sending payment notification: {e}")
        
        return True
    
    except Exception as e:
        logger.error(f"Error processing payment: {e}", exc_info=True)
        return False

# команда для проверки платежа Crypto Bot
async def check_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для проверки статуса платежа Crypto Bot: /checkpay <invoice_id> <pack_index>"""
    user_id = update.effective_user.id
    
    args = getattr(context, 'args', None) or []
    if len(args) < 2:
        await update.message.reply_text(
            "❌ использование: /checkpay <invoice_id> <pack_index>\n\n"
            "пример: /checkpay 1234567890 0\n\n"
            "pack_index: 0 = начальный набор, 1 = гангстер плюс"
        )
        return
    
    invoice_id = args[0]
    
    try:
        pack_index = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ pack_index должен быть числом!")
        return
    
    # Показываем, что проверяем
    checking_msg = await update.message.reply_text("⏳ проверяю статус платежа...")
    
    # Проверяем платеж
    result = await check_crypto_payment_status(user_id, invoice_id, pack_index, context)
    
    if result:
        await checking_msg.edit_text(
            "✅ <b>платеж подтвержден!</b>\n\n"
            "деньги успешно зачислены на счет",
            parse_mode='html'
        )
        logger.info(f"Payment confirmed for user {user_id}")
    else:
        await checking_msg.edit_text(
            "❌ платеж не найден или еще не оплачен\n\n"
            "проверьте invoice_id и попробуйте позже"
        )

# обработка проверки статуса крипто платежа через callback - БОЛЬШЕ НЕ ИСПОЛЬЗУЕТСЯ
# Вместо этого используется автоматическая фоновая проверка check_all_pending_crypto_payments
# async def handle_crypto_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Обработчик для кнопки проверки статуса крипто платежа (УСТАРЕЛО)"""
#     pass

# автоматическая фоновая проверка всех ожидающих крипто-платежей
async def check_all_pending_crypto_payments(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет все ожидающие крипто-платежи и обновляет их статусы"""
    global pending_crypto_payments
    
    if not crypto_bot_token or crypto_bot_token == "вставить_токен_сюда":
        logger.debug("Crypto bot token not configured, skipping payment checks")
        return
    
    # Получаем список всех пользователей с ожидающими платежами
    users_to_check = list(pending_crypto_payments.keys())
    logger.debug(f"Checking {len(users_to_check)} users for pending crypto payments")
    
    for user_id in users_to_check:
        packs_to_check = list(pending_crypto_payments[user_id].keys())
        
        for pack_index in packs_to_check:
            payment_info = pending_crypto_payments[user_id][pack_index]
            invoice_id = payment_info.get('invoice_id')
            created_at = payment_info.get('created_at')
            check_count = payment_info.get('check_count', 0)
            
            # Не проверяем платежи старше 24 часов
            if time.time() - created_at > 86400:  # 24 часа
                logger.info(f"Removing expired payment for user {user_id}, invoice {invoice_id}")
                del pending_crypto_payments[user_id][pack_index]
                continue
            
            # Проверяем платеж
            try:
                result = await check_crypto_payment_status(user_id, invoice_id, pack_index, context)
                
                if result:
                    # Платеж успешен - удаляем из ожидающих
                    del pending_crypto_payments[user_id][pack_index]
                    logger.info(f"Payment confirmed for user {user_id}, invoice {invoice_id}")
                else:
                    # Платеж еще не прошел - обновляем счетчик проверок
                    pending_crypto_payments[user_id][pack_index]['check_count'] = check_count + 1
            except Exception as e:
                logger.error(f"Error checking crypto payment for user {user_id}: {e}")

# ==========================================
# СИСТЕМА ПРОМОКОДОВ
# ==========================================

def init_promocodes_db():
    """Инициализация таблиц БД для промокодов"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_type TEXT NOT NULL,
            reward_value INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 0,
            uses_count INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_promocodes (
            user_id INTEGER,
            code TEXT,
            activated_at REAL,
            PRIMARY KEY (user_id, code)
        )
    ''')
    # Заполняем стартовыми промокодами при пустой БД
    cursor.execute("SELECT COUNT(*) FROM promocodes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value) VALUES ('GANGSTER', 'money', 50000)")
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value) VALUES ('START', 'money', 25000)")
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value) VALUES ('BONUS', 'money', 100000)")
    
    # Всегда гарантируем наличие 3 эксклюзивных одноразовых промокодов на пистолет
    tester_codes = ['TESTER-GUN-777', 'BETA-PISTOLET-2026', 'GANGSTER-EXCLUSIVE-999']
    for code in tester_codes:
        cursor.execute("INSERT OR IGNORE INTO promocodes (code, reward_type, reward_value, max_uses, uses_count) VALUES (?, 'gun_accessory', 1, 1, 0)", (code,))
    conn.commit()
    conn.close()

def activate_promocode(user_id: int, code_str: str) -> tuple[bool, str]:
    """Активирует промокод для пользователя"""
    init_promocodes_db()
    code_str = code_str.strip().upper()
    
    if not code_str:
        return False, "❌ введите промокод!"
        
    conn = sqlite3.connect('gangster_bot.db', timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT reward_type, reward_value, max_uses, uses_count FROM promocodes WHERE UPPER(code) = ?", (code_str,))
        promo = cursor.fetchone()
        
        if not promo:
            conn.close()
            return False, "❌ такой промокод не найден или истек!"
            
        reward_type, reward_value, max_uses, uses_count = promo
        
        if max_uses > 0 and uses_count >= max_uses:
            conn.close()
            return False, "❌ этот промокод больше недействителен (закончились активации)!"
            
        cursor.execute("SELECT 1 FROM user_promocodes WHERE user_id = ? AND UPPER(code) = ?", (user_id, code_str))
        if cursor.fetchone():
            conn.close()
            return False, "❌ вы уже активировали этот промокод!"
            
        current_time = time.time()
        cursor.execute("INSERT INTO user_promocodes (user_id, code, activated_at) VALUES (?, ?, ?)", (user_id, code_str, current_time))
        cursor.execute("UPDATE promocodes SET uses_count = uses_count + 1 WHERE UPPER(code) = ?", (code_str,))
        conn.commit()
        conn.close()
        
        if reward_type == 'money':
            update_user_money(user_id, reward_value)
            msg = f"✅ промокод <b>{code_str}</b> успешно активирован!\n\n💰 начислено: <b>{format_money(reward_value)}</b>"
        elif reward_type == 'coins':
            from registration import update_admin_currency
            update_admin_currency(user_id, reward_value)
            msg = f"✅ промокод <b>{code_str}</b> успешно активирован!\n\n💎 начислено: <b>{reward_value} админ-коинов</b>"
        elif reward_type == 'gangster_plus':
            from registration import update_user_field
            update_user_field(user_id, 'is_gangster_plus', True)
            msg = f"✅ промокод <b>{code_str}</b> успешно активирован!\n\n⭐️ вам активирована подписка <b>Гангстер Плюс</b>!"
        elif reward_type == 'gun_accessory':
            from accessories import give_user_gun_accessory
            give_user_gun_accessory(user_id)
            msg = f"✅ эксклюзивный промокод <b>{code_str}</b> активирован!\n\n🔫 вам выдан и надет эксклюзивный аксессуар: <b>пистолет</b>!\nуправлять им можно в меню ⚙️ Настройки."
        else:
            update_user_money(user_id, reward_value)
            msg = f"✅ промокод <b>{code_str}</b> успешно активирован!"
            
        return True, msg
    except Exception as e:
        logger.error(f"Ошибка активации промокода: {e}")
        return False, f"❌ ошибка активации промокода: {e}"

async def prompt_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает у пользователя ввод промокода"""
    context.user_data['waiting_for_promocode'] = True
    reply_keyboard = [
        [KeyboardButton("🎁 промокод"), KeyboardButton("назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🎟️ <b>введите промокод:</b>\n\nнапишите ваш промокод сообщением в чат.",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def process_gangster_plus_weekly_payouts(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача для выдачи 5кк каждую неделю подписчикам Гангстер Плюс и проверки срока подписок"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        now = time.time()
        cursor.execute('''
            SELECT user_id, gangster_plus_until, last_plus_weekly_payout 
            FROM users 
            WHERE is_gangster_plus = TRUE
        ''')
        rows = cursor.fetchall()
        
        for user_id, plus_until, last_payout in rows:
            plus_until = plus_until or 0.0
            last_payout = last_payout or 0.0
            
            # Проверяем не истекла ли подписка
            if plus_until > 0.0 and now > plus_until:
                cursor.execute('UPDATE users SET is_gangster_plus = FALSE WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"Gangster plus expired for user {user_id}")
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="⚠️ <b>срок действия подписки Гангстер Плюс истек!</b>\n\nпродлите подписку в меню доната 💎",
                        parse_mode='html'
                    )
                except Exception:
                    pass
                continue
            
            # Проверяем, прошло ли 7 дней (604800 сек) с последней выплаты
            if last_payout > 0.0 and (now - last_payout >= 604800):
                update_user_money(user_id, 5000000)
                cursor.execute('UPDATE users SET last_plus_weekly_payout = ? WHERE user_id = ?', (now, user_id))
                conn.commit()
                logger.info(f"Weekly 5kk gangster plus payout sent to user {user_id}")
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🎉 <b>еженедельный бонус Гангстер Плюс!</b>\n\nвам зачислено: <b>5.000.000$</b> 💎",
                        parse_mode='html'
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error in process_gangster_plus_weekly_payouts: {e}")
    finally:
        conn.close()
