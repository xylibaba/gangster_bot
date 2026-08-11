import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import os
import sqlite3
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, get_user_by_username, get_user_by_name, log_financial_transaction, DB_PATH
from utils import format_money, maybe_send_channel_reminder

logger = logging.getLogger(__name__)

# Конфигурация домов
HOMES = [
    {
        "id": 1,
        "name": "номерок в отеле",
        "description": "скромный номерок в отеле с компактным шкафом",
        "price": 2500000,
        "image_file": "images/home_1.jpg",
        "base_slots": 5
    },
    {
        "id": 2,
        "name": "дом Сиджея",
        "description": "легендарный дом Сиджея на Гроув Стрит с просторным шкафом",
        "price": 10000000,
        "image_file": "images/home_2.jpg",
        "base_slots": 10
    }
]

def init_homes_db():
    """Инициализация таблиц домов, подселения и шкафа"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица владения домом
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_homes (
            user_id INTEGER PRIMARY KEY,
            home_id INTEGER,
            use_as_background BOOLEAN DEFAULT FALSE,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Миграция: если таблица user_homes уже существовала до обновления
    try:
        cursor.execute("ALTER TABLE user_homes ADD COLUMN use_as_background BOOLEAN DEFAULT FALSE;")
    except Exception:
        pass
    
    # Таблица подселенных жильцов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS home_roommates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            roommate_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(owner_id, roommate_id)
        )
    ''')
    
    # Таблица слотов шкафа
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS home_wardrobe_slots (
            owner_id INTEGER,
            slot_number INTEGER,
            accessory_id INTEGER DEFAULT NULL,
            is_locked BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (owner_id, slot_number)
        )
    ''')
    
    conn.commit()
    conn.close()

# Инициализируем таблицы при импорте
init_homes_db()

def get_user_home(user_id):
    """Получает дом, которым владеет пользователь"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, home_id, use_as_background FROM user_homes WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_home_for_user_or_roommate(user_id):
    """Возвращает (owner_id, home_id, is_owner, use_as_background) для пользователя"""
    own_home = get_user_home(user_id)
    if own_home:
        return own_home[0], own_home[1], True, bool(own_home[2])
    
    # Проверяем, подселен ли пользователь к кому-то
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT uh.user_id, uh.home_id, uh.use_as_background 
        FROM home_roommates hr
        JOIN user_homes uh ON hr.owner_id = uh.user_id
        WHERE hr.roommate_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0], row[1], False, bool(row[2])
    return None

def get_total_slots_for_owner(owner_id, home_id):
    """Вычисляет общее количество слотов с учетом подписки Гангстер Плюс"""
    home_config = next((h for h in HOMES if h['id'] == home_id), HOMES[0])
    base_slots = home_config['base_slots']
    
    user = get_user(owner_id)
    has_plus = user[18] if user and len(user) > 18 else False
    
    return base_slots + (5 if has_plus else 0)

# Показ главного меню Дома (Reply-клавиатура)
async def show_home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню дома (Reply-кнопки)"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user or not user[8]:
        await update.message.reply_text("❌ сначала зарегистрируйся! напиши /start")
        return
        
    home_info = get_home_for_user_or_roommate(user_id)
    if not home_info:
        # Дома нет — показываем магазин покупки домов
        await show_homes_shop(update, context)
        return
        
    owner_id, home_id, is_owner, use_bg = home_info
    home_config = next((h for h in HOMES if h['id'] == home_id), HOMES[0])
    total_slots = get_total_slots_for_owner(owner_id, home_id)
    
    user_data = get_user(owner_id)
    owner_name = user_data[2] if user_data and len(user_data) > 2 else f"ID {owner_id}"
    
    status_str = "владелец" if is_owner else f"жилец (дом пользователя {owner_name})"
    bg_status_str = "включен 🟢" if use_bg else "отключен 🔴"
    
    msg_text = (
        f"🏠 <b>ВАШ ДОМ: {home_config['name'].upper()}</b>\n\n"
        f"<i>{home_config['description']}</i>\n\n"
        f"👤 <b>статус:</b> {status_str}\n"
        f"📦 <b>слотов в шкафу:</b> {total_slots}\n"
        f"🎨 <b>дом как фон:</b> {bg_status_str}\n\n"
        f"выберите действие в меню ниже:"
    )
    
    # Reply клавиатура дома
    reply_keyboard = [
        [KeyboardButton("👕 шкаф"), KeyboardButton("👥 подселение")],
        [KeyboardButton("⚙️ настройки дома"), KeyboardButton("⬅️ назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    image_file = home_config['image_file']
    if os.path.exists(image_file):
        try:
            with open(image_file, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=photo,
                    caption=msg_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            return
        except Exception as e:
            logger.error(f"Ошибка отправки фото дома: {e}")
            
    await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

# Показ магазина домов (для тех у кого нет дома)
async def show_homes_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает карусель покупки домов"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        return
        
    current_index = context.user_data.get('homes_carousel_index', 0)
    if current_index < 0 or current_index >= len(HOMES):
        current_index = 0
    context.user_data['homes_carousel_index'] = current_index
    
    home = HOMES[current_index]
    money = user[5] if len(user) > 5 else 0
    
    has_plus = user[18] if len(user) > 18 else False
    plus_note = " <i>(+5 слотов с Гангстер Плюс)</i>" if has_plus else ""
    
    message_text = (
        f"🏠 <b>{home['name'].upper()}</b>\n\n"
        f"{home['description']}\n\n"
        f"💰 <b>цена:</b> {format_money(home['price'])}\n"
        f"💵 <b>у вас:</b> {format_money(money)}\n"
        f"📦 <b>шкаф:</b> {home['base_slots']} слотов{plus_note}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️", callback_data="homes_prev"),
            InlineKeyboardButton("➡️", callback_data="homes_next")
        ]
    ]
    
    if money >= home['price']:
        keyboard.append([InlineKeyboardButton("✅ купить дом", callback_data=f"homes_buy_{current_index}")])
    else:
        keyboard.append([InlineKeyboardButton(f"❌ недостаточно денег", callback_data="homes_no_money")])
        
    keyboard.append([InlineKeyboardButton("⬅️ назад", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    image_file = home['image_file']
    
    if update.callback_query:
        try:
            if os.path.exists(image_file):
                with open(image_file, 'rb') as photo:
                    from telegram import InputMediaPhoto
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(media=photo, caption=message_text, parse_mode='HTML'),
                        reply_markup=reply_markup
                    )
            else:
                await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception:
            await update.callback_query.answer()
    else:
        if os.path.exists(image_file):
            try:
                with open(image_file, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=message_text, reply_markup=reply_markup, parse_mode='HTML')
                return
            except Exception:
                pass
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')

# Навигация по магазину домов
async def handle_homes_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE, action):
    query = update.callback_query
    current_index = context.user_data.get('homes_carousel_index', 0)
    
    if action == "prev":
        current_index = (current_index - 1) % len(HOMES)
    elif action == "next":
        current_index = (current_index + 1) % len(HOMES)
        
    context.user_data['homes_carousel_index'] = current_index
    await show_homes_shop(update, context)

# Покупка дома
async def buy_home(update: Update, context: ContextTypes.DEFAULT_TYPE, home_index):
    query = update.callback_query
    user_id = query.from_user.id
    
    if home_index < 0 or home_index >= len(HOMES):
        await query.answer("❌ неверный дом!", show_alert=True)
        return
        
    home = HOMES[home_index]
    user = get_user(user_id)
    money = user[5] if user and len(user) > 5 else 0
    
    if money < home['price']:
        await query.answer("❌ недостаточно денег!", show_alert=True)
        return
        
    existing_home = get_user_home(user_id)
    if existing_home:
        await query.answer("❌ вы уже владеете домом!", show_alert=True)
        return
        
    update_user_money(user_id, -home['price'])
    log_financial_transaction(user_id, "buy_home", -home['price'], f"покупка дома '{home['name']}'")
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_homes (user_id, home_id, use_as_background) VALUES (?, ?, FALSE)', (user_id, home['id']))
    conn.commit()
    conn.close()
    
    await query.answer(f"🎉 Вы успешно купили {home['name']}!", show_alert=True)
    from accessories import clear_character_cache
    clear_character_cache(user_id)
    
    await show_home_menu(update, context)

# ==========================================
# 👕 ШКАФ (ПО 5 СЛОТОВ НА СТРАНИЦУ)
# ==========================================

async def show_wardrobe_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page=None):
    """Показывает содержимое шкафа (строго по 5 слотов на странице)"""
    user_id = update.effective_user.id
    home_info = get_home_for_user_or_roommate(user_id)
    
    if not home_info:
        if update.callback_query:
            await update.callback_query.answer("❌ у вас нет доступа к дому!", show_alert=True)
        else:
            await update.message.reply_text("❌ у вас нет дома!")
        return
        
    owner_id, home_id, is_owner, use_bg = home_info
    total_slots = get_total_slots_for_owner(owner_id, home_id)
    
    if page is None:
        page = context.user_data.get('wardrobe_page', 0)
    
    max_pages = (total_slots + 4) // 5  # страниц по 5 слотов
    if page < 0:
        page = 0
    elif page >= max_pages:
        page = max_pages - 1
    context.user_data['wardrobe_page'] = page
    
    # Получаем содержимое слотов
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT slot_number, accessory_id, is_locked 
        FROM home_wardrobe_slots 
        WHERE owner_id = ?
    ''', (owner_id,))
    slot_rows = {row[0]: (row[1], bool(row[2])) for row in cursor.fetchall()}
    
    # Получаем информацию об именах аксессуаров
    acc_ids = [val[0] for val in slot_rows.values() if val[0] is not None]
    acc_names = {}
    if acc_ids:
        placeholders = ','.join('?' * len(acc_ids))
        cursor.execute(f'SELECT accessory_id, name FROM accessories WHERE accessory_id IN ({placeholders})', acc_ids)
        acc_names = dict(cursor.fetchall())
    conn.close()
    
    start_slot = page * 5 + 1
    end_slot = min(start_slot + 4, total_slots)
    
    msg_text = (
        f"👕 <b>ШКАФ ДЛЯ ВЕЩЕЙ (стр. {page + 1}/{max_pages})</b>\n\n"
        f"всего слотов: <b>{total_slots}</b> (по 5 на странице)\n"
        f"здесь хранятся ваши аксессуары.\n"
        f"нажмите на слот для взаимодействия:"
    )
    
    keyboard = []
    
    # Ровно до 5 слотов на текущую страницу (в 1 столбец)
    for slot_num in range(start_slot, end_slot + 1):
        acc_id, is_locked = slot_rows.get(slot_num, (None, False))
        
        lock_icon = "🔒 " if is_locked else ""
        if acc_id and acc_id in acc_names:
            item_name = acc_names[acc_id]
            btn_text = f"{lock_icon}💎 слот {slot_num} ({item_name})"
        else:
            btn_text = f"{lock_icon}слот {slot_num} (пусто)"
            
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"wardrobe_slot_{slot_num}")])
        
    # Пагинация (⏪ / ⏩)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⏪", callback_data="wardrobe_page_prev"))
    if page < max_pages - 1:
        nav_row.append(InlineKeyboardButton("⏩", callback_data="wardrobe_page_next"))
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton("⬅️ назад к дому", callback_data="home_menu_return")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception:
            await update.callback_query.answer()
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

# Клик по слоту шкафа
async def handle_slot_click(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number):
    query = update.callback_query
    user_id = query.from_user.id
    
    home_info = get_home_for_user_or_roommate(user_id)
    if not home_info:
        await query.answer("❌ доступ запрещен!", show_alert=True)
        return
        
    owner_id, home_id, is_owner, use_bg = home_info
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT accessory_id, is_locked FROM home_wardrobe_slots WHERE owner_id = ? AND slot_number = ?', (owner_id, slot_number))
    row = cursor.fetchone()
    conn.close()
    
    acc_id = row[0] if row else None
    is_locked = bool(row[1]) if row else False
    
    # Блокировка: если слот заблокирован владельцем, а смотрит жилец (не владелец):
    if is_locked and not is_owner:
        await query.answer("🔒 Этот слот заблокирован владельцем дома!", show_alert=True)
        return
        
    if not acc_id:
        # Слот пустой — предлагаем положить аксессуар из инвентаря
        await show_deposit_accessory_menu(update, context, slot_number)
    else:
        # Слот занят — меню действия со слотом
        await show_occupied_slot_menu(update, context, slot_number, acc_id, is_locked, is_owner)

# Меню выбора аксессуара для укладывания в пустой слот
async def show_deposit_accessory_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number):
    query = update.callback_query
    user_id = query.from_user.id
    
    home_info = get_home_for_user_or_roommate(user_id)
    owner_id = home_info[0] if home_info else user_id
    
    # Получаем купленные пользователем аксессуары, которые НЕ находятся уже в каком-либо шкафу
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT a.accessory_id, a.name 
        FROM user_items ui
        JOIN accessories a ON ui.accessory_id = a.accessory_id
        WHERE ui.user_id = ? AND ui.accessory_id NOT IN (
            SELECT accessory_id FROM home_wardrobe_slots WHERE owner_id = ? AND accessory_id IS NOT NULL
        )
    ''', (user_id, owner_id))
    available_items = cursor.fetchall()
    conn.close()
    
    if not available_items:
        await query.answer("❌ У вас нет свободных аксессуаров в инвентаре!", show_alert=True)
        return
        
    msg_text = f"📦 <b>ПОЛОЖИТЬ ВЕЩЬ В СЛОТ {slot_number}</b>\n\nвыберите предмет из вашего инвентаря:"
    keyboard = []
    for item_id, item_name in available_items:
        keyboard.append([InlineKeyboardButton(f"📥 {item_name}", callback_data=f"wardrobe_deposit_{slot_number}_{item_id}")])
        
    keyboard.append([InlineKeyboardButton("⬅️ отмена", callback_data="wardrobe_refresh")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

# Положить вещь в слот
async def deposit_accessory_to_slot(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number, accessory_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    home_info = get_home_for_user_or_roommate(user_id)
    if not home_info:
        await query.answer("❌ ошибка!", show_alert=True)
        return
        
    owner_id, home_id, is_owner, use_bg = home_info
    
    # Если предмет надет на персонажа — снимаем его!
    from accessories import is_accessory_equipped, unequip_accessory, clear_character_cache
    if is_accessory_equipped(user_id, accessory_id):
        conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT type FROM accessories WHERE accessory_id = ?', (accessory_id,))
        acc_row = cursor.fetchone()
        conn.close()
        if acc_row:
            unequip_accessory(user_id, acc_row[0])
            
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO home_wardrobe_slots (owner_id, slot_number, accessory_id, is_locked)
        VALUES (?, ?, ?, FALSE)
        ON CONFLICT(owner_id, slot_number) DO UPDATE SET accessory_id = ?
    ''', (owner_id, slot_number, accessory_id, accessory_id))
    conn.commit()
    conn.close()
    
    clear_character_cache(user_id)
    await query.answer("✅ Вещь успешно положена в шкаф!", show_alert=True)
    await show_wardrobe_page(update, context)

# Меню занятого слота
async def show_occupied_slot_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number, accessory_id, is_locked, is_owner):
    query = update.callback_query
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM accessories WHERE accessory_id = ?', (accessory_id,))
    row = cursor.fetchone()
    conn.close()
    
    acc_name = row[0] if row else "аксессуар"
    lock_status = "заблокирован 🔒" if is_locked else "доступен всем жильцам 🔓"
    
    msg_text = (
        f"💎 <b>СЛОТ {slot_number}: {acc_name.upper()}</b>\n\n"
        f"🔒 <b>статус доступа:</b> {lock_status}\n\n"
        f"выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📥 забрать в инвентарь", callback_data=f"wardrobe_withdraw_{slot_number}")]
    ]
    
    if is_owner:
        lock_btn_text = "🔓 разблокировать слот" if is_locked else "🔒 заблокировать слот для жильцов"
        keyboard.append([InlineKeyboardButton(lock_btn_text, callback_data=f"wardrobe_toggle_lock_{slot_number}")])
        
    keyboard.append([InlineKeyboardButton("⬅️ назад в шкаф", callback_data="wardrobe_refresh")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

# Забрать вещь из слота обратно
async def withdraw_accessory_from_slot(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number):
    query = update.callback_query
    user_id = query.from_user.id
    
    home_info = get_home_for_user_or_roommate(user_id)
    if not home_info:
        await query.answer("❌ ошибка доступа!", show_alert=True)
        return
        
    owner_id, home_id, is_owner, use_bg = home_info
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT accessory_id, is_locked FROM home_wardrobe_slots WHERE owner_id = ? AND slot_number = ?', (owner_id, slot_number))
    row = cursor.fetchone()
    
    if not row or not row[0]:
        conn.close()
        await query.answer("❌ слот уже пуст!", show_alert=True)
        await show_wardrobe_page(update, context)
        return
        
    acc_id, is_locked = row[0], bool(row[1])
    if is_locked and not is_owner:
        conn.close()
        await query.answer("🔒 Слот заблокирован владельцем дома!", show_alert=True)
        return
        
    # Освобождаем слот
    cursor.execute('UPDATE home_wardrobe_slots SET accessory_id = NULL WHERE owner_id = ? AND slot_number = ?', (owner_id, slot_number))
    
    # Если в user_items предмета нет (вдруг отдавали), принудительно отдаем забиравшему
    cursor.execute('SELECT 1 FROM user_items WHERE user_id = ? AND accessory_id = ?', (user_id, acc_id))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO user_items (user_id, accessory_id) VALUES (?, ?)', (user_id, acc_id))
        
    conn.commit()
    conn.close()
    
    from accessories import equip_accessory, clear_character_cache
    equip_accessory(user_id, acc_id)
    clear_character_cache(user_id)
    
    await query.answer("✅ Вещь забрана из шкафа и надета на вас!", show_alert=True)
    await show_wardrobe_page(update, context)

# Блокировка / разблокировка слота
async def toggle_slot_lock(update: Update, context: ContextTypes.DEFAULT_TYPE, slot_number):
    query = update.callback_query
    user_id = query.from_user.id
    
    home_info = get_home_for_user_or_roommate(user_id)
    if not home_info or not home_info[2]:  # только owner
        await query.answer("❌ Только владелец дома может блокировать слоты!", show_alert=True)
        return
        
    owner_id = home_info[0]
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT is_locked FROM home_wardrobe_slots WHERE owner_id = ? AND slot_number = ?', (owner_id, slot_number))
    row = cursor.fetchone()
    
    current_locked = bool(row[0]) if row else False
    new_locked = not current_locked
    
    cursor.execute('''
        INSERT INTO home_wardrobe_slots (owner_id, slot_number, accessory_id, is_locked)
        VALUES (?, ?, NULL, ?)
        ON CONFLICT(owner_id, slot_number) DO UPDATE SET is_locked = ?
    ''', (owner_id, slot_number, new_locked, new_locked))
    conn.commit()
    conn.close()
    
    status_str = "заблокирован" if new_locked else "разблокирован"
    await query.answer(f"🔒 Слот {slot_number} {status_str}!", show_alert=True)
    await show_wardrobe_page(update, context)

# ==========================================
# ⚙️ НАСТРОЙКИ ДОМА И ПРОДАЖА
# ==========================================

async def show_home_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает настройки дома"""
    user_id = update.effective_user.id if update.effective_user else 0
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        
    own_home = get_user_home(user_id)
    if not own_home:
        if update.callback_query:
            await update.callback_query.answer("❌ Вы не являетесь владельцем дома!", show_alert=True)
        else:
            await update.message.reply_text("❌ у вас нет дома!")
        return
        
    home_id, use_bg = own_home[1], bool(own_home[2])
    home_config = next((h for h in HOMES if h['id'] == home_id), HOMES[0])
    
    refund_price = int(home_config['price'] * 0.75)
    bg_btn_text = "🎨 дом как фон: включен 🟢" if use_bg else "🎨 дом как фон: отключен 🔴"
    
    msg_text = (
        f"⚙️ <b>НАСТРОЙКИ ДОМА ({home_config['name'].upper()})</b>\n\n"
        f"💰 <b>стоимость при продаже (75%):</b> {format_money(refund_price)}\n"
        f"🎨 <b>дом как фон главного меню:</b> {'включен' if use_bg else 'отключен'}\n\n"
        f"выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton(bg_btn_text, callback_data="home_toggle_bg")],
        [InlineKeyboardButton(f"💰 продать дом ({format_money(refund_price)})", callback_data="home_sell_confirm")],
        [InlineKeyboardButton("👥 выселить жильцов", callback_data="home_roommates_manage")],
        [InlineKeyboardButton("⬅️ назад", callback_data="home_menu_return")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

# Переключение использования дома как фона
async def toggle_home_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    own_home = get_user_home(user_id)
    if not own_home:
        await query.answer("❌ у вас нет дома!", show_alert=True)
        return
        
    current_use = bool(own_home[2])
    new_use = not current_use
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE user_homes SET use_as_background = ? WHERE user_id = ?', (new_use, user_id))
    if new_use:
        # Если включили дом как фон — автоматически снимаем магазинные фоны
        cursor.execute('UPDATE user_equipped SET background_accessory = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    from accessories import clear_character_cache
    clear_character_cache(user_id)
    
    status_str = "включен 🟢" if new_use else "отключен 🔴"
    await query.answer(f"🎨 Дом как фон {status_str}!", show_alert=True)
    await show_home_settings(update, context)

# Продажа дома (75% от стоимости)
async def sell_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    own_home = get_user_home(user_id)
    if not own_home:
        await query.answer("❌ у вас нет дома!", show_alert=True)
        return
        
    home_id = own_home[1]
    home_config = next((h for h in HOMES if h['id'] == home_id), HOMES[0])
    refund_amount = int(home_config['price'] * 0.75)
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    
    # Возвращаем заблокированные/лежащие вещи в инвентарь пользователя
    cursor.execute('SELECT accessory_id FROM home_wardrobe_slots WHERE owner_id = ? AND accessory_id IS NOT NULL', (user_id,))
    stored_items = [row[0] for row in cursor.fetchall()]
    
    for acc_id in stored_items:
        cursor.execute('SELECT 1 FROM user_items WHERE user_id = ? AND accessory_id = ?', (user_id, acc_id))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO user_items (user_id, accessory_id) VALUES (?, ?)', (user_id, acc_id))
            
    cursor.execute('DELETE FROM home_wardrobe_slots WHERE owner_id = ?', (user_id,))
    cursor.execute('DELETE FROM home_roommates WHERE owner_id = ?', (user_id,))
    cursor.execute('DELETE FROM user_homes WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    update_user_money(user_id, refund_amount)
    log_financial_transaction(user_id, "sell_home", refund_amount, f"продажа дома ({home_config['name']})")
    
    from accessories import clear_character_cache
    clear_character_cache(user_id)
    
    await query.answer(f"💰 Дом продан! Возвращено {format_money(refund_amount)}", show_alert=True)
    
    from main_menu import show_main_menu
    await show_main_menu(update, context)

# ==========================================
# 👥 ПОДСЕЛЕНИЕ И УПРАВЛЕНИЕ ЖИЛЬЦАМИ
# ==========================================

async def start_invite_roommate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса приглашения жильца"""
    user_id = update.effective_user.id
    own_home = get_user_home(user_id)
    
    if not own_home:
        await update.message.reply_text("❌ вы должны быть владельцем дома, чтобы подселять игроков!")
        return
        
    context.user_data['waiting_for_roommate_invite'] = True
    await update.message.reply_text(
        "👥 <b>ПОДСЕЛЕНИЕ В ДОМ</b>\n\n"
        "напишите в чат <b>@username</b> или <b>Имя/ID</b> игрока, которого вы хотите подселить:",
        parse_mode='HTML'
    )

async def finish_invite_roommate(update: Update, context: ContextTypes.DEFAULT_TYPE, text_input):
    """Завершение процесса подселения"""
    user_id = update.effective_user.id
    context.user_data.pop('waiting_for_roommate_invite', None)
    
    target_username = text_input.replace('@', '').strip()
    target_user = get_user_by_username(target_username)
    
    if not target_user:
        try:
            target_id = int(target_username)
            target_user = get_user(target_id)
        except ValueError:
            target_user = get_user_by_name(target_username)
            
    if not target_user:
        await update.message.reply_text("❌ пользователь не найден!")
        return
        
    target_id = target_user[0]
    nickname = target_user[2] if len(target_user) > 2 else "игрок"
    
    if target_id == user_id:
        await update.message.reply_text("❌ вы не можете подселить самого себя!")
        return
        
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO home_roommates (owner_id, roommate_id) VALUES (?, ?)', (user_id, target_id))
        conn.commit()
        await update.message.reply_text(f"✅ Игрок <b>{nickname}</b> успешно подселен в ваш дом!", parse_mode='HTML')
        
        # Уведомляем подселенного игрока
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🏠 Вас подселил в свой дом <b>{update.effective_user.first_name}</b>!",
                parse_mode='HTML'
            )
        except Exception:
            pass
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ этот игрок уже подселен в ваш дом!")
    finally:
        conn.close()

async def manage_roommates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список жильцов с возможностью выселения"""
    query = update.callback_query
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT roommate_id FROM home_roommates WHERE owner_id = ?', (user_id,))
    roommate_ids = [r[0] for r in cursor.fetchall()]
    
    if not roommate_ids:
        conn.close()
        await query.answer("❌ у вас нет подселенных жильцов!", show_alert=True)
        return
        
    placeholders = ','.join('?' * len(roommate_ids))
    cursor.execute(f'SELECT user_id, name, username FROM users WHERE user_id IN ({placeholders})', roommate_ids)
    roommates = cursor.fetchall()
    conn.close()
    
    msg_text = "👥 <b>УПРАВЛЕНИЕ ЖИЛЬЦАМИ</b>\n\nнажмите на жильца, чтобы выселить его:"
    keyboard = []
    for r_id, r_name, r_uname in roommates:
        display_name = f"{r_name} (@{r_uname})" if r_uname else r_name
        keyboard.append([InlineKeyboardButton(f"❌ выселить {display_name}", callback_data=f"home_evict_{r_id}")])
        
    keyboard.append([InlineKeyboardButton("⬅️ назад", callback_data="home_settings")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode='HTML')

async def evict_roommate(update: Update, context: ContextTypes.DEFAULT_TYPE, roommate_id):
    query = update.callback_query
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM home_roommates WHERE owner_id = ? AND roommate_id = ?', (user_id, roommate_id))
    conn.commit()
    conn.close()
    
    await query.answer("✅ Жилец выселен!", show_alert=True)
    await manage_roommates(update, context)
