import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
"""
Система бизнеса с заказом сырья и доставкой курьером
"""

import sqlite3
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, update_user_money
from utils import format_money, maybe_send_channel_reminder

# Конфигурация бизнеса
BUSINESSES = [
    {
        "id": 1,
        "name": "пиццерия",
        "description": "доставка пиццы, заказывай ингредиенты и жди доставку",
        "price": 10000000,  # 10млн
        "image_file": "images/business_pizza.jpg",
        "raw_material_name": "ингредиенты"
    }
]

# Показать список бизнеса для покупки
async def show_business_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает каталог бизнеса"""
    await maybe_send_channel_reminder(update, context)
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:  # не зарегистрирован
        await update.message.reply_text("❌ сначала зарегистрируйся! напиши /start")
        return
    
    # Получаем текущий индекс
    current_index = context.user_data.get('business_carousel_index', 0)
    context.user_data['business_carousel_index'] = current_index
    
    # Получаем куплен ли бизнес
    user_business = get_user_business(user_id)
    
    current_business = BUSINESSES[current_index]
    
    is_purchased = user_business and user_business[1] == current_business['id']
    
    money = user[5] if len(user) > 5 else 0
    
    message_text = f"""💼 <b>{current_business['name'].upper()}</b>

{current_business['description']}

💰 цена: {format_money(current_business['price'])}
у вас: {format_money(money)}

заказывай сырье, курьер доставляет за 10 минут
сырье используется автоматически за 1 день"""
    
    keyboard = []
    
    # Кнопка покупки/управления
    if is_purchased:
        keyboard.append([InlineKeyboardButton("📦 заказать сырье", callback_data="business_orders")])
    elif current_business['price'] <= money:
        keyboard.append([InlineKeyboardButton("✅ купить бизнес", callback_data=f"business_buy_{current_index}")])
    else:
        keyboard.append([InlineKeyboardButton(f"❌ недостаточно денег", callback_data="business_no_money")])
    
    keyboard.append([InlineKeyboardButton("назад", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Покупка бизнеса
async def buy_business(update: Update, context: ContextTypes.DEFAULT_TYPE, business_index):
    """Покупка бизнеса"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if business_index < 0 or business_index >= len(BUSINESSES):
            await query.answer("❌ неверный бизнес!", show_alert=True)
            return
        
        business = BUSINESSES[business_index]
        user = get_user(user_id)
        
        if not user:
            await query.answer("❌ пользователь не найден!", show_alert=True)
            return
        
        # Проверяем баланс
        money = user[5] if len(user) > 5 else 0
        if money < business['price']:
            await query.answer(f"❌ недостаточно денег!", show_alert=True)
            return
        
        # Проверяем, не куплен ли уже бизнес
        existing_business = get_user_business(user_id)
        if existing_business:
            await query.answer("❌ вы уже владеете бизнесом!", show_alert=True)
            return
        
        # Снимаем деньги
        update_user_money(user_id, -business['price'])
        from registration import log_financial_transaction
        log_financial_transaction(user_id, "buy_business", -business['price'], f"покупка бизнеса '{business['name']}'")
        
        # Добавляем бизнес в БД
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO user_business (user_id, business_id, raw_material)
                VALUES (?, ?, 0)
            ''', (user_id, business['id']))
            
            conn.commit()
        finally:
            conn.close()
        
        await query.answer(f"✅ бизнес куплен! {business['name']}", show_alert=True)
        await show_business_shop(update, context)
        
    except Exception as e:
        print(f"❌ ошибка при покупке бизнеса: {e}")
        await query.answer("❌ ошибка при покупке!", show_alert=True)

# Получить бизнес пользователя
def get_user_business(user_id):
    """Получить информацию о бизнесе пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM user_business WHERE user_id = ?', (user_id,))
        business = cursor.fetchone()
        return business
    finally:
        conn.close()

# Показать меню заказов сырья
async def show_business_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню заказа сырья"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        user_business = get_user_business(user_id)
        if not user_business:
            await query.answer("❌ у вас нет бизнеса!", show_alert=True)
            return
        
        business = next((b for b in BUSINESSES if b['id'] == user_business[1]), None)
        if not business:
            await query.answer("❌ бизнес не найден!", show_alert=True)
            return
        
        current_raw = user_business[3] if len(user_business) > 3 else 0
        
        message_text = f"""📦 <b>{business['name']}</b> - заказ сырья

текущий запас {business['raw_material_name']}: **{current_raw} единиц**

заказать сырье:
(доставка ~10 минут, расходуется за 1 день)"""
        
        # Варианты заказа
        orders = [
            ("100 единиц", 100),
            ("500 единиц", 500),
            ("1000 единиц", 1000),
            ("5000 единиц", 5000),
        ]
        
        keyboard = []
        for label, amount in orders:
            keyboard.append([InlineKeyboardButton(label, callback_data=f"business_order_{amount}")])
        
        keyboard.append([InlineKeyboardButton("назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        print(f"❌ ошибка при открытии меню заказов: {e}")
        await query.answer("❌ ошибка!", show_alert=True)

# Заказать сырье
async def order_raw_material(update: Update, context: ContextTypes.DEFAULT_TYPE, amount):
    """Заказать сырье через курьера"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if amount <= 0:
            await query.answer("❌ неверное количество!", show_alert=True)
            return
        
        user_business = get_user_business(user_id)
        if not user_business:
            await query.answer("❌ у вас нет бизнеса!", show_alert=True)
            return
        
        # Добавляем заказ
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            current_time = time.time()
            delivery_time = current_time + 600  # 10 минут
            expires_at = delivery_time + 86400  # + 1 день (86400 секунд)
            
            cursor.execute('''
                INSERT INTO business_raw_orders (user_id, amount, delivery_time, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, amount, delivery_time, expires_at))
            
            conn.commit()
        finally:
            conn.close()
        
        await query.answer(f"📦 заказ принят! доставка за 10 минут ({amount} единиц)", show_alert=True)
        
        # Запускаем асинхронную доставку
        asyncio.create_task(deliver_raw_material(user_id, context, amount))
        
        await show_business_orders(update, context)
        
    except Exception as e:
        print(f"❌ ошибка при заказе сырья: {e}")
        await query.answer("❌ ошибка при заказе!", show_alert=True)

# Асинхронная доставка сырья курьером
async def deliver_raw_material(user_id, context, amount):
    """Доставить сырье курьером через 10 минут"""
    try:
        # Ждем 10 минут (600 секунд)
        await asyncio.sleep(600)
        
        # Добавляем сырье в запас
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE user_business
                SET raw_material = raw_material + ?
                WHERE user_id = ?
            ''', (amount, user_id))
            conn.commit()
        finally:
            conn.close()
        
        # Отправляем уведомление пользователю
        try:
            user = get_user(user_id)
            if user:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📦 <b>доставка сырья!</b>\n\nкурьер доставил {amount} единиц сырья на ваше производство!",
                    parse_mode='HTML'
                )
        except Exception as e:
            print(f"⚠️ не удалось отправить уведомление доставки: {e}")
        
    except Exception as e:
        print(f"❌ ошибка при доставке сырья: {e}")

# Автоматический расход сырья (вызывается каждый час или при проверке)
async def consume_raw_material(user_id):
    """Автоматически расходует сырье за истекший период"""
    try:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            # Получаем все истекшие заказы сырья
            current_time = time.time()
            cursor.execute('''
                SELECT * FROM business_raw_orders
                WHERE user_id = ? AND expires_at <= ? AND expires_at > 0
            ''', (user_id, current_time))
            
            expired_orders = cursor.fetchall()
            
            # Удаляем истекшие заказы (сырье закончилось)
            for order in expired_orders:
                cursor.execute('''
                    UPDATE business_raw_orders
                    SET expires_at = 0
                    WHERE order_id = ?
                ''', (order[0],))
            
            conn.commit()
            
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ ошибка при расходе сырья: {e}")
