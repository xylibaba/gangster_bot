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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, LabeledPrice, InputMediaPhoto
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, is_main_admin, DB_PATH
from utils import safe_delete_message, format_money, maybe_send_channel_reminder
from scam import add_referral_donation_earnings

# загружаем переменные окружения
load_dotenv()

# настройка логгера
logger = logging.getLogger(__name__)

import rollypay_client

# ==========================================
# Глобальное хранилище ожидающих платежей
# ==========================================
# Структура: {user_id: {pack_index: {invoice_id, created_at, message_id, chat_id}}}
pending_crypto_payments = {}
# Структура RollyPay: {user_id: {payment_id: {payment_id, pack_index, order_id, user_id, amount, created_at, chat_id, message_id, payment_method}}}
pending_rollypay_payments = {}

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
        "price_rub": 100,
        "price_stars": 52,
        "price_crypto": 1.0,
        "reward_money": 10000000,
        "is_subscription": False,
        "photo": "images/donation_1.jpg"
    },
    {
        "id": "gangster_plus",
        "title": "💎 гангстер плюс",
        "description": "• 💬 VIP-чат с админами\n• ⚡️ х4 прибыль со всех работ\n• 💎 алмаз около ника\n• 💰 5.000.000$ каждую неделю (автоматически)\n\n💡 <i>наполнение подписки будет меняться в лучшую сторону!</i>\n✨ <i>все действует пока активна подписка (1 месяц)</i>",
        "price_rub": 150,
        "price_stars": 77,
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
    
    rub_price = pack.get('price_rub', 100)
    text = (
        f"<b>{pack['title']}</b>\n\n"
        f"{pack['description']}\n\n"
        f"💰 цена: <b>{rub_price} ₽ (СБП)</b> | <b>{pack['price_crypto']}$ (crypto)</b> | <b>{pack['price_stars']} ⭐️</b>"
    )
    if has_plus:
        text += "\n\n✅ <b>у вас активна эта подписка!</b>"

    buy_button_text = "уже куплено" if has_plus else "купить"

    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="pack_prev"),
            InlineKeyboardButton(buy_button_text, callback_data=f"pack_buy_{index}"),
            InlineKeyboardButton("➡️", callback_data="pack_next")
        ],
        [
            InlineKeyboardButton("📜 оферта", url="https://telegra.ph/PUBLICHNAYA-OFERTA-POLZOVATELSKOE-SOGLASHENIE-08-11"),
            InlineKeyboardButton("🔒 приватность", url="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-11-81")
        ]
    ]
    if has_plus:
        keyboard.append([InlineKeyboardButton("💬 VIP-чат с админами", url=get_main_admin_chat_link())])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            # Обновляем фото и подпись медиа-сообщения
            with open(pack['photo'], 'rb') as photo:
                await update.callback_query.edit_message_media(
                    media=InputMediaPhoto(media=photo, caption=text, parse_mode='html'),
                    reply_markup=reply_markup
                )
        except Exception:
            # если ошибка, удаляем и отправляем заново
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
        f"выберите удобный способ оплаты:"
    )
    
    rub_price = pack.get('price_rub', 100)
    keyboard = [
        [InlineKeyboardButton(f"💳 СБП ({rub_price} ₽)", callback_data=f"pay_rollypay_sbp_{index}")],
        [InlineKeyboardButton(f"💎 Криптовалюта / CryptoBot / xRocket ({pack['price_crypto']}$)", callback_data=f"pay_rollypay_crypto_{index}")],
        [InlineKeyboardButton(f"⭐️ Telegram Stars ({pack['price_stars']} зв.)", callback_data=f"pay_stars_{index}")]
    ]
    
    # 🧪 Для Главного Админа добавляем кнопку бесплатного тестового платежа (Sandbox)
    if is_main_admin(user_id):
        keyboard.append([InlineKeyboardButton("🧪 Тестовый платёж (Sandbox 0₽)", callback_data=f"pay_rollypay_test_{index}")])
        
    keyboard.append([InlineKeyboardButton("назад", callback_data="pack_back")])
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

# запуск оплаты через RollyPay (СБП, Криптовалюта, CryptoBot, xRocket, Тестовый режим)
async def start_pack_rollypay_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_method: str = "sbp", is_test: bool = False):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 🔒 Если запрошен тестовый платёж, строго проверяем права главного админа
    if is_test and not is_main_admin(user_id):
        await query.answer("❌ Тестовый режим доступен только Главному Админу!", show_alert=True)
        return
    
    try:
        parts = query.data.split("_")
        index = int(parts[-1])
        if not (0 <= index < len(packs)):
            logger.warning(f"Invalid pack index: {index}")
            return
    except Exception as e:
        logger.warning(f"Error parsing rollypay payment data: {e}")
        return

    pack = packs[index]
    prefix = "test_pack" if is_test else "pack"
    order_id = f"{prefix}_{index}_{user_id}_{int(time.time())}"
    amount_rub = pack.get('price_rub', 100)
    
    if is_test:
        desc = f"🧪 Тестовая покупка «{pack['title']}» (Sandbox 0₽)"
        method_title = "🧪 Тестовый платёж (Sandbox 0₽)"
        actual_method = "sbp"
    elif payment_method == "crypto":
        desc = f"Покупка «{pack['title']}» (Crypto / CryptoBot / xRocket)"
        method_title = "Криптовалюта (Crypto / CryptoBot / xRocket)"
        actual_method = "crypto"
    else:
        desc = f"Покупка «{pack['title']}» (СБП)"
        method_title = "СБП (Система быстрых платежей)"
        actual_method = "sbp"

    res = await rollypay_client.create_payment(
        amount=amount_rub,
        description=desc,
        order_id=order_id,
        user_id=user_id,
        payment_method=actual_method,
        currency="RUB",
        metadata={"user_id": user_id, "pack_index": index, "is_test": is_test},
        test=is_test
    )

    if not res.get("ok"):
        err = res.get("error", "Неизвестная ошибка")
        await query.answer(f"❌ {err}", show_alert=True)
        return

    payment_id = res["payment_id"]
    pay_url = res["pay_url"]
    
    # Сохраняем в глобальное хранилище ожидающих платежей
    if user_id not in pending_rollypay_payments:
        pending_rollypay_payments[user_id] = {}
        
    pending_rollypay_payments[user_id][payment_id] = {
        'payment_id': payment_id,
        'order_id': order_id,
        'pack_index': index,
        'user_id': user_id,
        'amount': amount_rub,
        'currency': 'RUB',
        'created_at': time.time(),
        'chat_id': update.effective_chat.id,
        'message_id': None,
        'payment_method': payment_method,
        'is_test': is_test
    }

    test_notice = "\n\n⚠️ <i>Это тестовый счет Sandbox (деньги не списываются). На открывшейся странице нажмите «Оплатить успешно» для проверки.</i>" if is_test else ""
    text = (
        f"💳 <b>счет на оплату: {pack['title']}</b>\n\n"
        f"• способ оплаты: <b>{method_title}</b>\n"
        f"• сумма к оплате: <b>{amount_rub} ₽</b>\n"
        f"• ID платежа: <code>{payment_id}</code>{test_notice}\n\n"
        f"👉 <i>нажмите «оплатить» ниже для перехода на форму оплаты. После завершения перевода бот автоматически выдаст награду (или нажмите «проверить оплату»).</i>"
    )

    keyboard = [
        [InlineKeyboardButton("💳 оплатить (Sandbox)" if is_test else "💳 оплатить", url=pay_url)],
        [InlineKeyboardButton("🔄 проверить оплату", callback_data=f"check_rollypay_{payment_id}_{index}")],
        [InlineKeyboardButton("⬅️ назад к наборам", callback_data="pack_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        msg = await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode='html')
        pending_rollypay_payments[user_id][payment_id]['message_id'] = msg.message_id
    except Exception:
        msg = await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='html')
        pending_rollypay_payments[user_id][payment_id]['message_id'] = msg.message_id

# ручная проверка платежа RollyPay по кнопке
async def handle_check_rollypay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        parts = query.data.split("_")
        # format: check_rollypay_{payment_id}_{pack_index}
        payment_id = parts[2]
        pack_index = int(parts[3])
    except Exception as e:
        logger.error(f"Error parsing check_rollypay callback: {e}")
        await query.answer("❌ Ошибка формата запроса", show_alert=True)
        return

    status_res = await rollypay_client.get_payment_status(payment_id)
    if not status_res.get("ok"):
        await query.answer("⚠️ Не удалось проверить статус платежа, попробуйте позже", show_alert=True)
        return

    status = status_res.get("status")
    if status == "paid":
        await query.answer("✅ Оплата подтверждена!")
        success_msg = await apply_pack_rewards(user_id, pack_index)
        pack = packs[pack_index]
        amount = pack.get('price_rub', 100)
        add_donation(user_id, amount, "RUB", "rollypay", "completed")
        
        # Удаляем из pending
        if user_id in pending_rollypay_payments and payment_id in pending_rollypay_payments[user_id]:
            del pending_rollypay_payments[user_id][payment_id]
            
        try:
            await query.edit_message_caption(caption=success_msg, reply_markup=None, parse_mode='html')
        except Exception:
            await query.edit_message_text(text=success_msg, reply_markup=None, parse_mode='html')
    elif status in ["created", "processing"]:
        await query.answer("⏳ Оплата еще не поступила. Если вы уже перевели средства, подождите 1-2 минуты и проверьте снова.", show_alert=True)
    else:
        await query.answer(f"❌ Статус платежа: {status} (не оплачен)", show_alert=True)

# автоматическая фоновая проверка платежей RollyPay
async def check_all_pending_rollypay_payments(context: ContextTypes.DEFAULT_TYPE):
    global pending_rollypay_payments
    bot = context.bot
    
    users = list(pending_rollypay_payments.keys())
    now = time.time()
    
    for user_id in users:
        p_ids = list(pending_rollypay_payments.get(user_id, {}).keys())
        for payment_id in p_ids:
            p_info = pending_rollypay_payments[user_id].get(payment_id)
            if not p_info:
                continue
                
            # Истечение через 24 часа
            if now - p_info.get('created_at', now) > 86400:
                del pending_rollypay_payments[user_id][payment_id]
                continue
                
            pack_index = p_info['pack_index']
            chat_id = p_info.get('chat_id')
            message_id = p_info.get('message_id')
            
            try:
                res = await rollypay_client.get_payment_status(payment_id)
                if res.get("ok") and res.get("status") == "paid":
                    logger.info(f"RollyPay auto-check confirmed payment {payment_id} for user {user_id}")
                    success_msg = await apply_pack_rewards(user_id, pack_index)
                    pack = packs[pack_index]
                    amount = pack.get('price_rub', 100)
                    add_donation(user_id, amount, "RUB", "rollypay", "completed")
                    
                    del pending_rollypay_payments[user_id][payment_id]
                    
                    if chat_id and message_id:
                        try:
                            await bot.edit_message_caption(chat_id=chat_id, message_id=message_id, caption=success_msg, parse_mode='html')
                        except Exception:
                            try:
                                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=success_msg, parse_mode='html')
                            except Exception:
                                await bot.send_message(chat_id=chat_id, text=success_msg, parse_mode='html')
                    elif chat_id:
                        await bot.send_message(chat_id=chat_id, text=success_msg, parse_mode='html')
            except Exception as e:
                logger.error(f"Error in RollyPay auto-check for {payment_id}: {e}")


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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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

def generate_random_promo_code(length: int = 10) -> str:
    """Генерирует случайную комбинацию заглавных букв и цифр"""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

def parse_promo_rewards(rewards_str: str):
    """
    Парсит строку наград для промокода.
    Форматы: 100k, acc:джинсы тянки, bg:Лос-Сантос, skin:молодой, plus
    Возвращает словарь со всеми распарсенными наградами.
    """
    res = {
        'money': 0,
        'acc_name': None,
        'bg_name': None,
        'skin_name': None,
        'is_plus': False
    }
    if not rewards_str:
        return res
    
    parts = rewards_str.replace(',', '+').split('+') if '+' in rewards_str else rewards_str.split()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lower_part = part.lower()
        if lower_part in ['plus', 'гангстер_плюс', 'gangster_plus']:
            res['is_plus'] = True
        elif lower_part.startswith(('acc:', 'акс:', 'шмотка:')):
            res['acc_name'] = part.split(':', 1)[1].strip()
        elif lower_part.startswith(('bg:', 'фон:')):
            res['bg_name'] = part.split(':', 1)[1].strip()
        elif lower_part.startswith(('skin:', 'скин:')):
            res['skin_name'] = part.split(':', 1)[1].strip()
        else:
            money_val = parse_amount(part)
            if money_val > 0:
                res['money'] += money_val
    return res

def resolve_accessory_id_by_name_or_id(val):
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        pass
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT accessory_id FROM accessories WHERE LOWER(name) = LOWER(?) LIMIT 1", (val,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def resolve_background_id_by_name_or_id(val):
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        pass
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT background_id FROM backgrounds WHERE LOWER(name) = LOWER(?) LIMIT 1", (val,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def resolve_skin_id_by_name_or_id(val):
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        pass
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT skin_id FROM skins WHERE LOWER(name) = LOWER(?) LIMIT 1", (val,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def init_promocodes_db():
    """Инициализация таблиц БД для промокодов и авто-миграция"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            reward_money INTEGER DEFAULT 0,
            reward_accessory_id INTEGER DEFAULT NULL,
            reward_background_id INTEGER DEFAULT NULL,
            reward_skin_id INTEGER DEFAULT NULL,
            reward_type TEXT DEFAULT NULL,
            reward_value INTEGER DEFAULT 0,
            target_user_id INTEGER DEFAULT NULL,
            max_uses INTEGER DEFAULT 1,
            uses_count INTEGER DEFAULT 0,
            expires_at REAL DEFAULT NULL,
            created_by INTEGER DEFAULT NULL,
            created_at REAL DEFAULT NULL
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
    
    # Миграция колонок таблицы promocodes
    cursor.execute("PRAGMA table_info(promocodes)")
    cols = [c[1] for c in cursor.fetchall()]
    new_cols = {
        'reward_money': 'INTEGER DEFAULT 0',
        'reward_accessory_id': 'INTEGER DEFAULT NULL',
        'reward_background_id': 'INTEGER DEFAULT NULL',
        'reward_skin_id': 'INTEGER DEFAULT NULL',
        'target_user_id': 'INTEGER DEFAULT NULL',
        'expires_at': 'REAL DEFAULT NULL',
        'created_by': 'INTEGER DEFAULT NULL',
        'created_at': 'REAL DEFAULT NULL'
    }
    for col_name, col_type in new_cols.items():
        if col_name not in cols:
            try:
                cursor.execute(f"ALTER TABLE promocodes ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

    # Заполняем стартовыми промокодами при пустой БД
    cursor.execute("SELECT COUNT(*) FROM promocodes")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value, reward_money) VALUES ('GANGSTER', 'money', 50000, 50000)")
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value, reward_money) VALUES ('START', 'money', 25000, 25000)")
        cursor.execute("INSERT INTO promocodes (code, reward_type, reward_value, reward_money) VALUES ('BONUS', 'money', 100000, 100000)")
    
    # Всегда гарантируем наличие эксклюзивных одноразовых промокодов
    tester_codes = ['TESTER-GUN-777', 'BETA-PISTOLET-2026', 'GANGSTER-EXCLUSIVE-999']
    for code in tester_codes:
        cursor.execute("INSERT OR IGNORE INTO promocodes (code, reward_type, reward_value, max_uses, uses_count) VALUES (?, 'gun_accessory', 1, 1, 0)", (code,))
    conn.commit()
    conn.close()

def create_promocode_entry(
    code: str = None,
    reward_money: int = 0,
    reward_accessory_id: int = None,
    reward_background_id: int = None,
    reward_skin_id: int = None,
    target_user_id: int = None,
    max_uses: int = 1,
    expires_in_hours: float = None,
    created_by: int = None
) -> tuple[bool, str, str]:
    """
    Создает промокод в базе данных.
    Возвращает (success, message, created_code)
    """
    init_promocodes_db()
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        if not code or code.strip().lower() in ['auto', '-']:
            # Генерируем случайную комбинацию заглавных букв и цифр
            for _ in range(50):
                new_code = generate_random_promo_code(10)
                cursor.execute("SELECT 1 FROM promocodes WHERE UPPER(code) = ?", (new_code,))
                if not cursor.fetchone():
                    code = new_code
                    break
            if not code or code.strip().lower() in ['auto', '-']:
                conn.close()
                return False, "❌ не удалось сгенерировать уникальный промокод!", None
        else:
            code = code.strip().upper()
            cursor.execute("SELECT 1 FROM promocodes WHERE UPPER(code) = ?", (code,))
            if cursor.fetchone():
                conn.close()
                return False, f"❌ промокод <code>{code}</code> уже существует!", None
        
        created_at = time.time()
        expires_at = (created_at + expires_in_hours * 3600) if (expires_in_hours and expires_in_hours > 0) else None
        
        cursor.execute('''
            INSERT INTO promocodes (
                code, reward_money, reward_accessory_id, reward_background_id, reward_skin_id,
                reward_type, reward_value, target_user_id, max_uses, uses_count, expires_at, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        ''', (
            code, reward_money, reward_accessory_id, reward_background_id, reward_skin_id,
            'custom', reward_money, target_user_id, max_uses, expires_at, created_by, created_at
        ))
        
        conn.commit()
        conn.close()
        return True, "✅ промокод успешно создан!", code
    except Exception as e:
        logger.error(f"Ошибка создания промокода: {e}")
        return False, f"❌ ошибка создания промокода: {e}", None

def activate_promocode(user_id: int, code_str: str) -> tuple[bool, str]:
    """Активирует промокод для пользователя с расширенной системой наград"""
    init_promocodes_db()
    code_str = code_str.strip().upper()
    
    if not code_str:
        return False, "❌ введите промокод!"
        
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT code, reward_money, reward_accessory_id, reward_background_id, reward_skin_id,
                   reward_type, reward_value, target_user_id, max_uses, uses_count, expires_at
            FROM promocodes 
            WHERE UPPER(code) = ?
        ''', (code_str,))
        promo = cursor.fetchone()
        
        if not promo:
            conn.close()
            return False, "❌ такой промокод не найден или истек!"
            
        (code, reward_money, reward_acc_id, reward_bg_id, reward_skin_id,
         reward_type, reward_value, target_user_id, max_uses, uses_count, expires_at) = promo
        
        current_time = time.time()
        
        # Проверка срока действия
        if expires_at and current_time > expires_at:
            conn.close()
            return False, "❌ срок действия этого промокода истёк!"
        
        # Проверка назначения конкретному пользователю
        if target_user_id and target_user_id != user_id:
            conn.close()
            return False, "❌ этот промокод предназначен для другого пользователя!"
            
        # Проверка лимита использования
        if max_uses and max_uses > 0 and uses_count >= max_uses:
            conn.close()
            return False, "❌ этот промокод больше недействителен (закончились активации)!"
            
        # Проверка повторной активации юзером
        cursor.execute("SELECT 1 FROM user_promocodes WHERE user_id = ? AND UPPER(code) = ?", (user_id, code_str))
        if cursor.fetchone():
            conn.close()
            return False, "❌ вы уже активировали этот промокод!"
            
        cursor.execute("INSERT INTO user_promocodes (user_id, code, activated_at) VALUES (?, ?, ?)", (user_id, code_str, current_time))
        cursor.execute("UPDATE promocodes SET uses_count = uses_count + 1 WHERE UPPER(code) = ?", (code_str,))
        conn.commit()
        conn.close()
        
        # Выдаем все привязанные награды
        rewards_list = []
        
        # 1. Деньги
        money_to_give = reward_money if (reward_money and reward_money > 0) else (reward_value if reward_type in ['money', None] and reward_value > 0 else 0)
        if money_to_give > 0:
            update_user_money(user_id, money_to_give)
            rewards_list.append(f"💰 <b>деньги:</b> +{format_money(money_to_give)}")
            
        # 2. Аксессуар
        if reward_acc_id:
            conn_temp = sqlite3.connect(DB_PATH)
            c_temp = conn_temp.cursor()
            c_temp.execute("SELECT name FROM accessories WHERE accessory_id = ?", (reward_acc_id,))
            acc_row = c_temp.fetchone()
            acc_name = acc_row[0] if acc_row else f"аксессуар #{reward_acc_id}"
            c_temp.execute("INSERT OR IGNORE INTO user_items (user_id, accessory_id) VALUES (?, ?)", (user_id, reward_acc_id))
            conn_temp.commit()
            conn_temp.close()
            rewards_list.append(f"👕 <b>аксессуар:</b> {acc_name}")
            
        # 3. Фон
        if reward_bg_id:
            conn_temp = sqlite3.connect(DB_PATH)
            c_temp = conn_temp.cursor()
            c_temp.execute("SELECT name FROM backgrounds WHERE background_id = ?", (reward_bg_id,))
            bg_row = c_temp.fetchone()
            bg_name = bg_row[0] if bg_row else f"фон #{reward_bg_id}"
            c_temp.execute("INSERT OR IGNORE INTO user_items (user_id, accessory_id) VALUES (?, ?)", (user_id, reward_bg_id))
            conn_temp.commit()
            conn_temp.close()
            rewards_list.append(f"🎨 <b>фон:</b> {bg_name}")
            
        # 4. Скин
        if reward_skin_id:
            conn_temp = sqlite3.connect(DB_PATH)
            c_temp = conn_temp.cursor()
            c_temp.execute("SELECT name FROM skins WHERE skin_id = ?", (reward_skin_id,))
            skin_row = c_temp.fetchone()
            skin_name = skin_row[0] if skin_row else f"скин #{reward_skin_id}"
            c_temp.execute("INSERT OR IGNORE INTO user_skin (user_id, skin_id) VALUES (?, ?)", (user_id, reward_skin_id))
            conn_temp.commit()
            conn_temp.close()
            rewards_list.append(f"👤 <b>скин:</b> {skin_name}")
            
        # 5. Поддержка legacy reward_type:
        if reward_type == 'coins':
            from registration import update_admin_currency
            update_admin_currency(user_id, reward_value)
            rewards_list.append(f"💎 <b>админ-коины:</b> +{reward_value}")
        elif reward_type == 'gangster_plus':
            from registration import update_user_field
            update_user_field(user_id, 'is_gangster_plus', True)
            rewards_list.append("⭐️ <b>подписка:</b> Гангстер Плюс")
        elif reward_type == 'gun_accessory':
            from accessories import give_user_gun_accessory
            give_user_gun_accessory(user_id)
            rewards_list.append("🔫 <b>аксессуар:</b> пистолет")

        if not rewards_list:
            rewards_list.append("🎁 Бонус получен!")
            
        msg = f"🎉 <b>промокод <code>{code_str}</code> успешно активирован!</b>\n\n<b>вы получили:</b>\n" + "\n".join(rewards_list)
        return True, msg
    except Exception as e:
        logger.error(f"Ошибка активации промокода: {e}")
        return False, f"❌ ошибка активации промокода: {e}"

# ==========================================
# ИНТЕРАКТИВНЫЙ КОНСТРУКТОР ПРОМОКОДОВ (КНОПКИ)
# ==========================================

def get_promo_builder_data(context):
    if 'promo_builder' not in context.user_data or not isinstance(context.user_data['promo_builder'], dict):
        context.user_data['promo_builder'] = {
            'code': 'auto',
            'money': 0,
            'acc_id': None,
            'bg_id': None,
            'skin_id': None,
            'is_plus': False,
            'max_uses': 1,
            'target_user_id': None,
            'expires_hours': None
        }
    return context.user_data['promo_builder']

def render_promo_constructor_screen(context):
    data = get_promo_builder_data(context)
    
    code_display = "🎲 [Случайный из букв и цифр]" if data['code'] == 'auto' else f"<code>{data['code']}</code>"
    money_display = format_money(data['money']) if data['money'] > 0 else "❌ Не задано"
    
    acc_display = "❌ Не выбран"
    if data['acc_id']:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM accessories WHERE accessory_id = ?", (data['acc_id'],))
        row = c.fetchone()
        conn.close()
        acc_display = f"👕 {row[0]}" if row else f"#{data['acc_id']}"
        
    bg_display = "❌ Не выбран"
    if data['bg_id']:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM backgrounds WHERE background_id = ?", (data['bg_id'],))
        row = c.fetchone()
        conn.close()
        bg_display = f"🎨 {row[0]}" if row else f"#{data['bg_id']}"
        
    skin_display = "❌ Не выбран"
    if data['skin_id']:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT name FROM skins WHERE skin_id = ?", (data['skin_id'],))
        row = c.fetchone()
        conn.close()
        skin_display = f"👤 {row[0]}" if row else f"#{data['skin_id']}"
        
    plus_display = "✅ [Включено]" if data['is_plus'] else "❌ [Выключено]"
    uses_display = f"{data['max_uses']}" if data['max_uses'] > 0 else "∞ [Безлимит]"
    target_display = f"ID: {data['target_user_id']}" if data['target_user_id'] else "👥 Для всех"
    exp_display = f"{data['expires_hours']} ч." if data['expires_hours'] else "⏳ Бессрочно"
    
    text = (
        "👑 <b>Конструктор промокодов (Главный Админ)</b>\n\n"
        "Выбирайте любые параметры и награды промокода по кнопкам ниже:\n\n"
        f"• 🎟️ <b>Код:</b> {code_display}\n"
        f"• 💰 <b>Деньги:</b> {money_display}\n"
        f"• 👕 <b>Аксессуар:</b> {acc_display}\n"
        f"• 🎨 <b>Фон:</b> {bg_display}\n"
        f"• 👤 <b>Скин:</b> {skin_display}\n"
        f"• ⭐️ <b>Гангстер Плюс:</b> {plus_display}\n"
        f"• 👥 <b>Активаций:</b> {uses_display}\n"
        f"• 🎯 <b>Получатель:</b> {target_display}\n"
        f"• ⏳ <b>Срок действия:</b> {exp_display}\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Деньги", callback_data="pb_set_money"),
            InlineKeyboardButton("🎟️ Задать код", callback_data="pb_set_code")
        ],
        [
            InlineKeyboardButton("👕 Выбрать аксессуар", callback_data="pb_sel_acc"),
            InlineKeyboardButton("🎨 Выбрать фон", callback_data="pb_sel_bg")
        ],
        [
            InlineKeyboardButton("👤 Выбрать скин", callback_data="pb_sel_skin"),
            InlineKeyboardButton(f"⭐️ Гангстер Плюс: {'✅' if data['is_plus'] else '❌'}", callback_data="pb_toggle_plus")
        ],
        [
            InlineKeyboardButton(f"👥 Активации ({uses_display})", callback_data="pb_sel_uses"),
            InlineKeyboardButton(f"⏳ Срок ({exp_display})", callback_data="pb_sel_exp")
        ],
        [
            InlineKeyboardButton(f"🎯 Получатель ({target_display})", callback_data="pb_sel_target")
        ],
        [
            InlineKeyboardButton("✨ 🎁 СОЗДАТЬ ПРОМОКОД ✨", callback_data="pb_create")
        ],
        [
            InlineKeyboardButton("🔄 Сбросить", callback_data="pb_reset"),
            InlineKeyboardButton("❌ Закрыть", callback_data="pb_cancel")
        ]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_acc_selector():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT accessory_id, name, type FROM accessories WHERE is_available = TRUE ORDER BY type, price")
    rows = c.fetchall()
    conn.close()
    
    text = "👕 <b>Выберите аксессуар для добавления в промокод по кнопке:</b>"
    keyboard = []
    
    type_emoji = {'head': '👒', 'hand': '🖐️', 'body': '📿', 'pants': '👖', 'feet': '👟'}
    
    row_btns = []
    for acc_id, name, acc_type in rows:
        emoji = type_emoji.get(acc_type, '👕')
        row_btns.append(InlineKeyboardButton(f"{emoji} {name}", callback_data=f"pb_acc_{acc_id}"))
        if len(row_btns) == 2:
            keyboard.append(row_btns)
            row_btns = []
    if row_btns:
        keyboard.append(row_btns)
        
    keyboard.append([InlineKeyboardButton("🚫 Снять выбор аксессуара", callback_data="pb_acc_none")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")])
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_bg_selector():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT background_id, name FROM backgrounds WHERE is_available = TRUE ORDER BY price")
    rows = c.fetchall()
    conn.close()
    
    text = "🎨 <b>Выберите фон для добавления в промокод по кнопке:</b>"
    keyboard = []
    
    row_btns = []
    for bg_id, name in rows:
        row_btns.append(InlineKeyboardButton(f"🎨 {name}", callback_data=f"pb_bg_{bg_id}"))
        if len(row_btns) == 2:
            keyboard.append(row_btns)
            row_btns = []
    if row_btns:
        keyboard.append(row_btns)
        
    keyboard.append([InlineKeyboardButton("🚫 Снять выбор фона", callback_data="pb_bg_none")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")])
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_skin_selector():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT skin_id, name FROM skins ORDER BY price")
    rows = c.fetchall()
    conn.close()
    
    text = "👤 <b>Выберите скин для добавления в промокод по кнопке:</b>"
    keyboard = []
    
    row_btns = []
    for skin_id, name in rows:
        row_btns.append(InlineKeyboardButton(f"👤 {name}", callback_data=f"pb_skin_{skin_id}"))
        if len(row_btns) == 2:
            keyboard.append(row_btns)
            row_btns = []
    if row_btns:
        keyboard.append(row_btns)
        
    keyboard.append([InlineKeyboardButton("🚫 Снять выбор скина", callback_data="pb_skin_none")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")])
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_money_selector():
    text = "💰 <b>Выберите или укажите сумму денег для промокода:</b>"
    keyboard = [
        [
            InlineKeyboardButton("0$", callback_data="pb_money_val_0"),
            InlineKeyboardButton("50.000$", callback_data="pb_money_val_50000"),
            InlineKeyboardButton("100.000$", callback_data="pb_money_val_100000")
        ],
        [
            InlineKeyboardButton("500.000$", callback_data="pb_money_val_500000"),
            InlineKeyboardButton("1.000.000$", callback_data="pb_money_val_1000000"),
            InlineKeyboardButton("5.000.000$", callback_data="pb_money_val_5000000")
        ],
        [
            InlineKeyboardButton("✏️ Ввести сумму вручную", callback_data="pb_money_custom")
        ],
        [
            InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_uses_selector():
    text = "👥 <b>Выберите лимит активаций промокода:</b>"
    keyboard = [
        [
            InlineKeyboardButton("1 активация", callback_data="pb_uses_val_1"),
            InlineKeyboardButton("3 активации", callback_data="pb_uses_val_3"),
            InlineKeyboardButton("5 активаций", callback_data="pb_uses_val_5")
        ],
        [
            InlineKeyboardButton("10 активаций", callback_data="pb_uses_val_10"),
            InlineKeyboardButton("50 активаций", callback_data="pb_uses_val_50"),
            InlineKeyboardButton("100 активаций", callback_data="pb_uses_val_100")
        ],
        [
            InlineKeyboardButton("∞ Безлимитный", callback_data="pb_uses_val_0"),
            InlineKeyboardButton("✏️ Ввести число вручную", callback_data="pb_uses_custom")
        ],
        [
            InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_exp_selector():
    text = "⏳ <b>Выберите срок действия промокода (время сгорания):</b>"
    keyboard = [
        [
            InlineKeyboardButton("∞ Бессрочно", callback_data="pb_exp_val_0"),
            InlineKeyboardButton("1 час", callback_data="pb_exp_val_1"),
            InlineKeyboardButton("6 часов", callback_data="pb_exp_val_6")
        ],
        [
            InlineKeyboardButton("12 часов", callback_data="pb_exp_val_12"),
            InlineKeyboardButton("24 часа (1 день)", callback_data="pb_exp_val_24"),
            InlineKeyboardButton("48 часов (2 дня)", callback_data="pb_exp_val_48")
        ],
        [
            InlineKeyboardButton("7 дней", callback_data="pb_exp_val_168"),
            InlineKeyboardButton("✏️ Ввести количество часов", callback_data="pb_exp_custom")
        ],
        [
            InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)

def render_promo_target_selector():
    text = "🎯 <b>Выберите для кого предназначен промокод:</b>"
    keyboard = [
        [
            InlineKeyboardButton("👥 Для всех пользователей", callback_data="pb_target_all")
        ],
        [
            InlineKeyboardButton("🎯 Указать ID или @username пользователя", callback_data="pb_target_custom")
        ],
        [
            InlineKeyboardButton("⬅️ Назад в конструктор", callback_data="pb_main")
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def handle_promo_builder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    from registration import is_main_admin
    if not is_main_admin(user_id):
        await query.answer("❌ только главный админ!", show_alert=True)
        return

    bld = get_promo_builder_data(context)

    if data == "pb_main":
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    elif data == "pb_set_money":
        text, reply_markup = render_promo_money_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    elif data.startswith("pb_money_val_"):
        val = int(data.replace("pb_money_val_", ""))
        bld['money'] = val
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    elif data == "pb_money_custom":
        context.user_data['waiting_for_promo_money'] = True
        await query.message.reply_text("💰 <b>Введите сумму денег для промокода в чат:</b>\n<i>(Например: 250k, 1.5kk или 500000)</i>", parse_mode='HTML')
        await query.answer()

    elif data == "pb_set_code":
        context.user_data['waiting_for_promo_code'] = True
        keyboard = [[InlineKeyboardButton("🎲 Сбросить на случайный (буквы + цифры)", callback_data="pb_code_auto")]]
        await query.message.reply_text("🎟️ <b>Введите собственный код промокода в чат:</b>\n<i>(Или нажмите кнопку ниже для случайного)</i>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()

    elif data == "pb_code_auto":
        bld['code'] = 'auto'
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_sel_acc":
        text, reply_markup = render_promo_acc_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_acc_none":
        bld['acc_id'] = None
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("pb_acc_"):
        aid = int(data.replace("pb_acc_", ""))
        bld['acc_id'] = aid
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_sel_bg":
        text, reply_markup = render_promo_bg_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_bg_none":
        bld['bg_id'] = None
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("pb_bg_"):
        bid = int(data.replace("pb_bg_", ""))
        bld['bg_id'] = bid
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_sel_skin":
        text, reply_markup = render_promo_skin_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_skin_none":
        bld['skin_id'] = None
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("pb_skin_"):
        sid = int(data.replace("pb_skin_", ""))
        bld['skin_id'] = sid
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_toggle_plus":
        bld['is_plus'] = not bld['is_plus']
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_sel_uses":
        text, reply_markup = render_promo_uses_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("pb_uses_val_"):
        uval = int(data.replace("pb_uses_val_", ""))
        bld['max_uses'] = uval
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_uses_custom":
        context.user_data['waiting_for_promo_uses'] = True
        await query.message.reply_text("👥 <b>Введите лимит активаций (целое число):</b>", parse_mode='HTML')
        await query.answer()

    elif data == "pb_sel_exp":
        text, reply_markup = render_promo_exp_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("pb_exp_val_"):
        eval_h = float(data.replace("pb_exp_val_", ""))
        bld['expires_hours'] = eval_h if eval_h > 0 else None
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_exp_custom":
        context.user_data['waiting_for_promo_exp'] = True
        await query.message.reply_text("⏳ <b>Введите срок действия в часах (например: 24):</b>", parse_mode='HTML')
        await query.answer()

    elif data == "pb_sel_target":
        text, reply_markup = render_promo_target_selector()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_target_all":
        bld['target_user_id'] = None
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_target_custom":
        context.user_data['waiting_for_promo_target'] = True
        await query.message.reply_text("🎯 <b>Введите ID или @username целевого пользователя:</b>", parse_mode='HTML')
        await query.answer()

    elif data == "pb_reset":
        context.user_data['promo_builder'] = {
            'code': 'auto', 'money': 0, 'acc_id': None, 'bg_id': None,
            'skin_id': None, 'is_plus': False, 'max_uses': 1,
            'target_user_id': None, 'expires_hours': None
        }
        text, reply_markup = render_promo_constructor_screen(context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "pb_cancel":
        try:
            await query.message.delete()
        except Exception:
            pass

    elif data == "pb_create":
        success, msg, created_code = create_promocode_entry(
            code=bld['code'],
            reward_money=bld['money'],
            reward_accessory_id=bld['acc_id'],
            reward_background_id=bld['bg_id'],
            reward_skin_id=bld['skin_id'],
            target_user_id=bld['target_user_id'],
            max_uses=bld['max_uses'],
            expires_in_hours=bld['expires_hours'],
            created_by=user_id
        )
        
        if success:
            res_text = (
                f"🎉 <b>Промокод <code>{created_code}</code> успешно создан!</b>\n\n"
                f"📋 <b>Содержимое:</b>\n"
            )
            if bld['money'] > 0:
                res_text += f"• 💰 Деньги: {format_money(bld['money'])}\n"
            if bld['acc_id']:
                res_text += f"• 👕 Аксессуар ID: {bld['acc_id']}\n"
            if bld['bg_id']:
                res_text += f"• 🎨 Фон ID: {bld['bg_id']}\n"
            if bld['skin_id']:
                res_text += f"• 👤 Скин ID: {bld['skin_id']}\n"
            if bld['is_plus']:
                res_text += "• ⭐️ Подписка Гангстер Плюс\n"
                
            res_text += f"\n👥 Макс. активаций: {bld['max_uses'] if bld['max_uses'] > 0 else 'Безлимит'}\n"
            if bld['target_user_id']:
                res_text += f"🎯 Только для ID: {bld['target_user_id']}\n"
            if bld['expires_hours']:
                res_text += f"⏳ Срок действия: {bld['expires_hours']} ч.\n"
                
            res_text += f"\n👉 Нажмите на код для копирования: <code>{created_code}</code>"
            
            kb = [
                [InlineKeyboardButton("➕ Создать еще один", callback_data="pb_reset")],
                [InlineKeyboardButton("🎟️ Все промокоды", callback_data="pb_list_all")]
            ]
            await query.edit_message_text(res_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        else:
            await query.answer(msg, show_alert=True)
            
    elif data == "pb_list_all":
        from main import promos_list_command
        await promos_list_command(update, context)

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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
