import logging
import sqlite3
import os
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from registration import get_user, update_user_money
from utils import safe_delete_message, format_money

# загружаем переменные окружения
load_dotenv()

# настройка логгера
logger = logging.getLogger(__name__)

# ==========================================
# 🔑 настройки платежных систем
# ==========================================

# 1. crypto bot
# 🔐 загружаем из .env файла
crypto_bot_token = os.getenv("CRYPTO_BOT_TOKEN", "")

# ==========================================

# конфигурация наборов
packs = [
    {
        "id": "starter_pack",
        "title": "📦 начальный набор",
        "description": "• 1.000.000$\n• отличный старт для новичка!",
        "price_stars": 1,
        "price_crypto": 1.0,
        "reward_money": 1000000,
        "is_subscription": False,
        "photo": "images/registration.jpg" # используем существующее фото как заглушку
    },
    {
        "id": "gangster_plus",
        "title": "💎 гангстер плюс",
        "description": "• x3 заработок на работах\n• алмаз 💎 около ника",
        "price_stars": 1,
        "price_crypto": 1.0,
        "reward_money": 0,
        "is_subscription": True,
        "photo": "images/registration.jpg" # используем существующее фото как заглушку
    }
]

# меню донатов (карусель)
async def show_donation_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # по умолчанию первый набор
    current_pack_index = 0
    context.user_data['current_pack_index'] = current_pack_index
    
    await show_pack(update, context, current_pack_index)

async def show_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, index: int):
    pack = packs[index]
    
    text = (
        f"<b>{pack['title']}</b>\n\n"
        f"{pack['description']}\n\n"
        f"💰 цена: <b>{pack['price_stars']} ⭐️</b> или <b>{pack['price_crypto']}$ (crypto)</b>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="pack_prev"),
            InlineKeyboardButton("купить", callback_data=f"pack_buy_{index}"),
            InlineKeyboardButton("➡️", callback_data="pack_next")
        ],
        [InlineKeyboardButton("назад", callback_data="main_menu")]
    ]
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
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.answer("❌ ошибка: некорректные данные", show_alert=True)
            return
        index = int(parts[-1])
        if not (0 <= index < len(packs)):
            await query.answer("❌ ошибка: неверный пакет", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("❌ ошибка: некорректные данные", show_alert=True)
        return
    
    pack = packs[index]
    
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
    
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.answer("❌ ошибка: некорректные данные", show_alert=True)
            return
        index = int(parts[-1])
        if not (0 <= index < len(packs)):
            await query.answer("❌ ошибка: неверный пакет", show_alert=True)
            return
        
        pack = packs[index]
        
        await query.answer()
        
        # Для Telegram Stars используем целые числа, без умножения на 100
        price = int(pack['price_stars']) if isinstance(pack['price_stars'], (int, float)) else 1
        prices = [LabeledPrice(pack['title'], price)]
        
        # Для xtr валюты provider_token должен быть пустой
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=pack['title'][:32],  # максимум 32 символа
            description=pack['description'][:255],  # максимум 255 символов
            payload=f"pack_{index}",
            provider_token="",
            currency="xtr",
            prices=prices
        )
        logger.info(f"Stars invoice sent for user {update.effective_user.id}, pack {index}")
    except Exception as e:
        logger.error(f"Error sending stars invoice: {e}", exc_info=True)
        await query.answer(f"❌ ошибка: {str(e)}", show_alert=True)

# запуск оплаты crypto bot
async def start_pack_crypto_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.answer("❌ ошибка: некорректные данные", show_alert=True)
            return
        index = int(parts[-1])
        if not (0 <= index < len(packs)):
            await query.answer("❌ ошибка: неверный пакет", show_alert=True)
            return
    except (ValueError, IndexError):
        await query.answer("❌ ошибка: некорректные данные", show_alert=True)
        return
    
    pack = packs[index]
    
    if crypto_bot_token == "вставить_токен_сюда":
        await query.answer("⚠️ токен crypto bot не настроен!", show_alert=True)
        return

    try:
        await query.answer()
        
        url = "https://pay.crypt.bot/api/invoices/create"
        headers = {"Crypto-Pay-API-Token": crypto_bot_token}
        payload_data = {
            "asset": "USDT",
            "amount": str(round(float(pack['price_crypto']), 2)),
            "description": pack['title'][:255]
        }
        
        logger.info(f"Sending crypto request: {payload_data}")
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers=headers, json=payload_data)
            logger.info(f"Crypto response status: {response.status_code}")
            logger.info(f"Crypto response: {response.text}")
            
            result = response.json()
            
            if result.get("ok") and result.get("result"):
                invoice_url = result["result"].get("bot_invoice_url")
                if invoice_url:
                    keyboard = [[InlineKeyboardButton("💎 оплатить", url=invoice_url)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"<b>счет для оплаты:</b>\n\n{invoice_url}",
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
                    logger.info(f"Crypto invoice created for user {update.effective_user.id}")
                else:
                    await query.answer("❌ ошибка: нет ссылки в ответе", show_alert=True)
            else:
                error_msg = result.get('error', {}).get('name', 'Unknown error')
                await query.answer(f"❌ ошибка: {error_msg}", show_alert=True)
                logger.error(f"Crypto API error: {result}")
    except Exception as e:
        logger.error(f"Crypto bot error: {e}", exc_info=True)
        await query.answer(f"❌ ошибка соединения: {str(e)}", show_alert=True)

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
        
        if payload.startswith("pack_"):
            try:
                index = int(payload.split("_")[-1])
                if 0 <= index < len(packs):
                    pack = packs[index]
                    
                    if pack['is_subscription']:
                        result = activate_gangster_plus(user_id)
                        if result:
                            await update.message.reply_text(
                                f"✅ <b>{pack['title']}</b> активирован!\n"
                                f"теперь у вас x3 заработок на работах и 💎 около ника",
                                parse_mode='html'
                            )
                        else:
                            await update.message.reply_text("⚠️ ошибка активации подписки")
                    else:
                        reward = pack['reward_money']
                        update_user_money(user_id, reward)
                        await update.message.reply_text(
                            f"✅ <b>оплата прошла успешно!</b>\n"
                            f"вам начислено <b>{format_money(reward)}</b> на баланс",
                            parse_mode='html'
                        )
                    
                    add_donation(user_id, amount_paid, currency, "telegram_stars", "completed")
                    logger.info(f"Pack payment processed: user={user_id}, pack={index}")
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
