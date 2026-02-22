"""
Магазин администраторской валюты
Здесь админы могут:
- Обменивать админ валюту на деньги (1 раз в неделю)
- Покупать доната
- Покупать аксессуары
- Покупать фоны
"""

import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from registration import (
    get_user, get_user_stats, update_admin_currency, get_admin_currency,
    can_exchange_admin_currency, exchange_admin_currency_to_money,
    get_exchange_remaining_time, get_exchange_remaining_coins
)
from utils import format_money

# Показать магазин админ валюты
async def show_admin_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Всегда берем свежие данные пользователя из БД, а не из кэша
    user = get_user(user_id)
    
    if not user or not user[6]:  # если не админ
        if update.callback_query:
            await update.callback_query.answer("❌ этот магазин доступен только для администраторов!", show_alert=True)
        else:
            await update.message.reply_text("❌ этот магазин доступен только для администраторов!")
        return
    
    # Получаем баланс админ валюты (всегда берем актуальное значение)
    admin_currency = get_admin_currency(user_id)
    if admin_currency is None:
        admin_currency = 0
    
    # Создаем текст
    message_text = f"""💎 <b>магазин администратора</b>

ваша админ валюта: <b>{admin_currency}</b> 💰

здесь вы можете:
• 💵 обменять валюту на деньги (1 раз в неделю)
• 🎁 купить донат
• 👕 купить аксессуары
• 🎨 купить фоны
"""
    
    # Проверяем возможность обмена
    can_exchange = can_exchange_admin_currency(user_id)
    remaining_time = get_exchange_remaining_time(user_id)
    
    if remaining_time is None:
        remaining_time = 0
    
    if not can_exchange and remaining_time is not None and remaining_time > 0:
        # Форматируем оставшееся время
        hours = int(remaining_time // 3600)
        minutes = int((remaining_time % 3600) // 60)
        message_text += f"\n⏳ <b>следующий обмен доступен через:</b> {hours}ч {minutes}мин"
    
    # Создаем клавиатуру
    keyboard = []
    
    # Кнопка обмена
    if admin_currency and admin_currency > 0 and can_exchange:
        keyboard.append([InlineKeyboardButton("💵 обменять валюту", callback_data="admin_shop_exchange")])
    elif admin_currency and admin_currency > 0:
        keyboard.append([InlineKeyboardButton("💵 обменять валюту (недоступно)", callback_data="admin_shop_exchange_blocked")])
    
    # Кнопки покупок
    keyboard.append([InlineKeyboardButton("🎁 донат", callback_data="admin_shop_donate")])
    keyboard.append([InlineKeyboardButton("👕 аксессуары", callback_data="admin_shop_accessories")])
    keyboard.append([InlineKeyboardButton("🎨 фоны", callback_data="admin_shop_backgrounds")])
    
    # Reply клавиатуры для кнопки "назад"
    keyboard.append([InlineKeyboardButton("назад", callback_data="admin_shop_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Обработка как callback так и обычного message
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Обмен валюты на деньги
async def admin_exchange_currency(update: Update, context: ContextTypes.DEFAULT_TYPE, amount=None):
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
        query = None
    
    user = get_user(user_id)
    if not user or not user[6]:
        if query:
            await query.answer("❌ доступ запрещен!", show_alert=True)
        else:
            await update.message.reply_text("❌ доступ запрещен!")
        return
    
    current_currency = get_admin_currency(user_id)
    
    if current_currency is None or current_currency == 0:
        if query:
            await query.answer("❌ у вас нет админ валюты для обмена!", show_alert=True)
        else:
            await update.message.reply_text("❌ у вас нет админ валюты для обмена!")
        return
    
    if not can_exchange_admin_currency(user_id):
        remaining_time = get_exchange_remaining_time(user_id)
        if remaining_time is None:
            remaining_time = 0
        if remaining_time and remaining_time > 0:
            hours = int(remaining_time // 3600)
            minutes = int((remaining_time % 3600) // 60)
            if query:
                await query.answer(f"❌ следующий обмен доступен через {hours}ч {minutes}мин", show_alert=True)
            else:
                await update.message.reply_text(f"❌ следующий обмен доступен через {hours}ч {minutes}мин")
        else:
            if query:
                await query.answer(f"❌ следующий обмен недоступен", show_alert=True)
            else:
                await update.message.reply_text("❌ следующий обмен недоступен")
        return
    
    if amount is None:
        # Предлагаем выбрать сумму
        context.user_data['exchange_currency_mode'] = True
        if query:
            await query.answer()
        
        # Получаем сколько осталось обменять за эту неделю
        remaining_coins = get_exchange_remaining_coins(user_id)
        
        # Показываем варианты обмена (1 коин = 1млн денег)
        exchange_options = [
            ("1 коин → 1'000'000 ₽", 1),
            ("2 коина → 2'000'000 ₽", 2),
            ("3 коина → 3'000'000 ₽", 3),
            ("4 коина → 4'000'000 ₽", 4),
            ("5 коинов → 5'000'000 ₽", 5),
        ]
        
        keyboard = []
        for label, coins in exchange_options:
            if coins <= current_currency and coins <= remaining_coins:
                keyboard.append([InlineKeyboardButton(
                    label,
                    callback_data=f"admin_exchange_amount_{coins}"
                )])
        
        keyboard.append([InlineKeyboardButton("отмена", callback_data="admin_shop_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        exchange_text = f"""💵 <b>обмен валюты на деньги</b>

ваша валюта: {current_currency} коинов
осталось за эту неделю: {remaining_coins} коинов

курс: 1 коин = 1'000'000 ₽
лимит в неделю: 5 коинов

выберите сумму для обмена:"""
        
        if query:
            await query.edit_message_text(
                exchange_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                exchange_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        return
    
    # Проверяем баланс
    if amount > current_currency:
        if query:
            await query.answer(f"❌ недостаточно валюты! (у вас {current_currency})", show_alert=True)
        else:
            await update.message.reply_text(f"❌ недостаточно валюты! (у вас {current_currency})")
        return
    
    # Выполняем обмен
    new_money = exchange_admin_currency_to_money(user_id, amount)
    
    if new_money is None:
        if query:
            await query.answer("❌ ошибка при выполнении обмена!", show_alert=True)
        else:
            await update.message.reply_text("❌ ошибка при выполнении обмена!")
        return
    
    # Успешно
    if query:
        await query.answer(f"✅ обмен выполнен! получено {format_money(amount)}", show_alert=True)
    else:
        await update.message.reply_text(f"✅ обмен выполнен! получено {format_money(amount)}")
    
    # Обновляем магазин
    await show_admin_shop(update, context)

# Показать донаты в магазине админа
async def show_admin_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        await update.message.reply_text("❌ невозможно выполнить эту операцию в этом контексте!")
        return
    
    query = update.callback_query
    user_id = query.from_user.id
    
    user = get_user(user_id)
    if not user or not user[6]:
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
    
    current_currency = get_admin_currency(user_id)
    if current_currency is None:
        current_currency = 0
    
    # Варианты донатов
    donate_packs = [
        ("🎁 тестовый набор", 1, "Получите экспериментальное содержимое"),
        ("👑 гангстер плюс", 5, "Активация премиум статуса на месяц"),
    ]
    
    keyboard = []
    for title, cost, description in donate_packs:
        affordable = "✅" if cost <= current_currency else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{title} ({cost} коин) {affordable}",
            callback_data=f"admin_buy_donate_{cost}" if cost <= current_currency else "admin_shop_no_money"
        )])
    
    keyboard.append([InlineKeyboardButton("назад", callback_data="admin_shop_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "🎁 <b>доступные донаты:</b>\n\n"
    for title, cost, description in donate_packs:
        message_text += f"{title}\n  {description}\n  стоимость: {cost} коин\n\n"
    
    message_text += f"\n💰 ваша валюта: {current_currency} коинов"
    
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Показать аксессуары в магазине админа
async def show_admin_accessories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.callback_query:
        await update.message.reply_text("❌ невозможно выполнить эту операцию в этом контексте!")
        return
    
    query = update.callback_query
    user_id = query.from_user.id
    
    user = get_user(user_id)
    if not user or not user[6]:
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
    
    current_currency = get_admin_currency(user_id)
    if current_currency is None:
        current_currency = 0
    
    message_text = """👕 <b>магазин аксессуаров</b>

📢 уведомление: в данный момент эксклюзивных аксессуаров нет в наличии.

обновления появятся позже!"""
    
    keyboard = [
        [InlineKeyboardButton("назад", callback_data="admin_shop_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if not update.callback_query:
        await update.message.reply_text("❌ невозможно выполнить эту операцию в этом контексте!")
        return
    
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Показать фоны в магазине админа
async def show_admin_backgrounds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    user = get_user(user_id)
    if not user or not user[6]:
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
    
    message_text = """🎨 <b>магазин фонов</b>

📢 уведомление: в данный момент эксклюзивных фонов нет в наличии.

обновления появятся позже!"""
    
    keyboard = [
        [InlineKeyboardButton("назад", callback_data="admin_shop_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Обработчик callback запросов магазина
async def handle_admin_shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data):
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if data == "admin_shop_exchange":
            await admin_exchange_currency(update, context)
        elif data == "admin_shop_exchange_blocked":
            remaining_time = get_exchange_remaining_time(user_id)
            if remaining_time and remaining_time > 0:
                hours = int(remaining_time // 3600)
                minutes = int((remaining_time % 3600) // 60)
                await query.answer(f"⏳ обмен доступен через {hours}ч {minutes}мин", show_alert=True)
            else:
                await query.answer(f"⏳ обмен может быть доступен", show_alert=True)
        elif data == "admin_shop_donate":
            await show_admin_donate(update, context)
        elif data == "admin_shop_accessories":
            await show_admin_accessories(update, context)
        elif data == "admin_shop_backgrounds":
            await show_admin_backgrounds(update, context)
        elif data == "admin_shop_no_money":
            await query.answer("❌ недостаточно админ валюты!", show_alert=True)
        elif data == "admin_shop_back":
            await query.answer()
            await show_admin_shop(update, context)
        elif data.startswith("admin_exchange_amount_"):
            amount = int(data.replace("admin_exchange_amount_", ""))
            await admin_exchange_currency(update, context, amount)
        elif data.startswith("admin_buy_donate_"):
            cost = int(data.replace("admin_buy_donate_", ""))
            await admin_buy_donate(update, context, cost)
        else:
            await query.answer("❌ неизвестная команда!", show_alert=True)
    except Exception as e:
        print(f"❌ ошибка в handle_admin_shop_callback: {e}")
        await query.answer("❌ произошла ошибка!", show_alert=True)

# Функция покупки доната за админ коины
async def admin_buy_donate(update: Update, context: ContextTypes.DEFAULT_TYPE, cost):
    """Покупка доната за админ валюту"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        user = get_user(user_id)
        if not user or not user[6]:
            await query.answer("❌ доступ запрещен!", show_alert=True)
            return
        
        current_currency = get_admin_currency(user_id)
        if current_currency is None or current_currency == 0:
            await query.answer("❌ у вас нет админ валюты!", show_alert=True)
            return
        
        if cost > current_currency:
            await query.answer(f"❌ недостаточно валюты! (нужно {cost}, у вас {current_currency})", show_alert=True)
            return
        
        # Получаем нужный пакет доната
        if cost == 1:
            donate_title = "тестовый набор"
        elif cost == 5:
            donate_title = "гангстер плюс"
        else:
            await query.answer("❌ неизвестный пакет доната!", show_alert=True)
            return
        
        # Вычитаем валюту
        new_currency = update_admin_currency(user_id, -cost)
        
        if new_currency is None:
            await query.answer("❌ ошибка при выполнении покупки!", show_alert=True)
            return
        
        # Показываем успешное сообщение
        await query.answer(f"✅ вы купили {donate_title}!", show_alert=True)
        
        # Возвращаемся в магазин
        await show_admin_donate(update, context)
        
    except ValueError:
        await query.answer("❌ ошибка обработки данных", show_alert=True)
    except Exception as e:
        print(f"❌ ошибка при покупке доната: {e}")
        await query.answer("❌ произошла ошибка!", show_alert=True)
