import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
"""
Система домов с шкафом для скинов
"""

import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, get_user_stats
from utils import format_money

# Конфигурация домов
HOMES = [
    {
        "id": 1,
        "name": "уютная квартира",
        "description": "маленькая, но уютная квартира с шкафом на 5 скинов",
        "price": 5000000,  # 5млн
        "image_file": "images/home_apartment.jpg"
    },
    {
        "id": 2,
        "name": "роскошный пентхаус",
        "description": "люксовый пентхаус с огромным шкафом на 5 скинов",
        "price": 15000000,  # 15млн
        "image_file": "images/home_penthouse.jpg"
    }
]

# Показать каталог домов (карусель)
async def show_homes_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает каталог домов в виде карусели"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:  # не зарегистрирован
        await update.message.reply_text("❌ сначала зарегистрируйся! напиши /start")
        return
    
    # Получаем текущий индекс карусели
    current_index = context.user_data.get('homes_carousel_index', 0)
    context.user_data['homes_carousel_index'] = current_index
    
    # Получаем купленный дом
    user_home = get_user_home(user_id)
    
    current_home = HOMES[current_index]
    
    # Проверяем, куплен ли этот дом
    is_purchased = user_home and user_home[1] == current_home['id']
    
    money = user[5] if len(user) > 5 else 0
    
    message_text = f"""🏠 <b>{current_home['name'].upper()}</b>

{current_home['description']}

💰 цена: {format_money(current_home['price'])}
у вас: {format_money(money)}

шкаф на 5 скинов для хранения"""
    
    keyboard = []
    
    # Кнопка навигации
    keyboard.append([
        InlineKeyboardButton("⬅️", callback_data="homes_prev"),
        InlineKeyboardButton("➡️", callback_data="homes_next")
    ])
    
    # Кнопка покупки/управления
    if is_purchased:
        keyboard.append([InlineKeyboardButton("🔓 открыть шкаф", callback_data="homes_wardrobe")])
    elif current_home['price'] <= money:
        keyboard.append([InlineKeyboardButton("✅ купить дом", callback_data=f"homes_buy_{current_index}")])
    else:
        keyboard.append([InlineKeyboardButton(f"❌ недостаточно денег ({format_money(current_home['price'] - money)})", callback_data="homes_no_money")])
    
    keyboard.append([InlineKeyboardButton("назад", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Навигация по карусели домов
async def handle_homes_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE, action):
    """Навигация вперед/назад по каталогу домов"""
    query = update.callback_query
    await query.answer()
    
    current_index = context.user_data.get('homes_carousel_index', 0)
    
    if action == "next":
        current_index = (current_index + 1) % len(HOMES)
    elif action == "prev":
        current_index = (current_index - 1) % len(HOMES)
    
    context.user_data['homes_carousel_index'] = current_index
    await show_homes_shop(update, context)

# Покупка дома
async def buy_home(update: Update, context: ContextTypes.DEFAULT_TYPE, home_index):
    """Покупка дома"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if home_index < 0 or home_index >= len(HOMES):
            await query.answer("❌ неверный дом!", show_alert=True)
            return
        
        home = HOMES[home_index]
        user = get_user(user_id)
        
        if not user:
            await query.answer("❌ пользователь не найден!", show_alert=True)
            return
        
        # Проверяем баланс
        money = user[5] if len(user) > 5 else 0
        if money < home['price']:
            await query.answer(f"❌ недостаточно денег! нужно {format_money(home['price'] - money)}", show_alert=True)
            return
        
        # Проверяем, не куплен ли уже дом
        existing_home = get_user_home(user_id)
        if existing_home:
            await query.answer("❌ вы уже владеете домом!", show_alert=True)
            return
        
        # Снимаем деньги
        update_user_money(user_id, -home['price'])
        
        # Добавляем дом в БД
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO user_homes (user_id, home_id)
                VALUES (?, ?)
            ''', (user_id, home['id']))
            
            # Создаем шкаф
            cursor.execute('''
                INSERT OR IGNORE INTO home_wardrobe (user_id)
                VALUES (?)
            ''', (user_id,))
            
            conn.commit()
        finally:
            conn.close()
        
        await query.answer(f"✅ дом куплен! {home['name']}", show_alert=True)
        await show_homes_shop(update, context)
        
    except Exception as e:
        print(f"❌ ошибка при покупке дома: {e}")
        await query.answer("❌ ошибка при покупке!", show_alert=True)

# Получить дом пользователя
def get_user_home(user_id):
    """Получить информацию о доме пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM user_homes WHERE user_id = ?', (user_id,))
        home = cursor.fetchone()
        return home
    finally:
        conn.close()

# Показать шкаф
async def show_wardrobe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать содержимое шкафа дома"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        user_home = get_user_home(user_id)
        if not user_home:
            await query.answer("❌ у вас нет дома!", show_alert=True)
            return
        
        home = next((h for h in HOMES if h['id'] == user_home[1]), None)
        if not home:
            await query.answer("❌ дом не найден!", show_alert=True)
            return
        
        # Получаем содержимое шкафа
        wardrobe = get_wardrobe(user_id)
        
        message_text = f"""🏠 <b>шкаф в {home['name'].lower()}</b>

вместимость: 5 слотов\n"""
        
        # Показываем содержимое каждого слота
        slots = [
            (wardrobe[1], "слот 1"),
            (wardrobe[2], "слот 2"),
            (wardrobe[3], "слот 3"),
            (wardrobe[4], "слот 4"),
            (wardrobe[5], "слот 5")
        ]
        
        keyboard = []
        for i, (skin_id, slot_name) in enumerate(slots, 1):
            if skin_id:
                # Получаем имя скина
                skin_name = get_skin_name(skin_id)
                keyboard.append([
                    InlineKeyboardButton(f"{slot_name}: {skin_name} ❌", callback_data=f"wardrobe_remove_{i}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(f"{slot_name}: пусто ➕", callback_data=f"wardrobe_add_{i}")
                ])
            message_text += f"\n{i}. {slots[i-1][1]}: "
            if skin_id:
                message_text += f"**{get_skin_name(skin_id)}** 🔒"
            else:
                message_text += "пусто"
        
        message_text += "\n\n⚠️ скины в шкафу нельзя использовать в магазине!"
        
        keyboard.append([InlineKeyboardButton("назад", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        print(f"❌ ошибка при открытии шкафа: {e}")
        await query.answer("❌ ошибка!", show_alert=True)

# Получить содержимое шкафа
def get_wardrobe(user_id):
    """Получить содержимое шкафа"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM home_wardrobe WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        if not result:
            # Создаем пустой шкаф
            cursor.execute('INSERT INTO home_wardrobe (user_id) VALUES (?)', (user_id,))
            conn.commit()
            return (user_id, None, None, None, None, None)
        return result
    finally:
        conn.close()

# Получить имя скина по ID
def get_skin_name(skin_id):
    """Получить имя скина по его ID"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT name FROM skins WHERE skin_id = ?', (skin_id,))
        result = cursor.fetchone()
        return result[0] if result else "неизвестный скин"
    finally:
        conn.close()

# Добавить скин в шкаф
async def add_skin_to_wardrobe(update: Update, context: ContextTypes.DEFAULT_TYPE, slot):
    """Добавить скин в слот шкафа"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if slot < 1 or slot > 5:
            await query.answer("❌ неверный слот!", show_alert=True)
            return
        
        # TODO: Показать список доступных скинов для добавления в шкаф
        await query.answer("📋 функция будет реализована позже", show_alert=True)
        
    except Exception as e:
        print(f"❌ ошибка при добавлении скина: {e}")
        await query.answer("❌ ошибка!", show_alert=True)

# Удалить скин из шкафа
async def remove_skin_from_wardrobe(update: Update, context: ContextTypes.DEFAULT_TYPE, slot):
    """Удалить скин из слота шкафа"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if slot < 1 or slot > 5:
            await query.answer("❌ неверный слот!", show_alert=True)
            return
        
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        try:
            # Получаем текущий скин
            field_name = f'slot{slot}_skin_id'
            cursor.execute(f'''
                UPDATE home_wardrobe
                SET {field_name} = NULL
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            
            await query.answer(f"✅ скин удален из слота {slot}", show_alert=True)
            await show_wardrobe(update, context)
            
        finally:
            conn.close()
        
    except Exception as e:
        print(f"❌ ошибка при удалении скина: {e}")
        await query.answer("❌ ошибка!", show_alert=True)
