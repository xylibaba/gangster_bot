import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from telegram.ext import ContextTypes
from registration import get_user, update_user_money, is_admin
from utils import format_money, safe_delete_message

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

def clear_character_cache(user_id):
    """Очищает кэш отрисованного персонажа"""
    try:
        from main_menu import character_cache
        # Очищаем кэш основного меню
        if user_id in character_cache:
            del character_cache[user_id]
        # Очищаем кэш профиля
        profile_key = f"profile_{user_id}"
        if profile_key in character_cache:
            del character_cache[profile_key]
    except:
        pass

# ==========================================
# 📦 АКСЕССУАРЫ И ФОНЫ
# ==========================================

# Встроенные скины (персонажи)
DEFAULT_SKINS = [
    {
        "name": "черный персонаж",
        "description": "стандартный черный персонаж",
        "price": 0,
        "image_file": "images/character_black.jpg",
        "is_default": True
    },
    {
        "name": "белый персонаж",
        "description": "стандартный белый персонаж",
        "price": 0,
        "image_file": "images/character_white.jpg",
        "is_default": False
    }
]

# Встроенные аксессуары (для быстрого старта)
DEFAULT_ACCESSORIES = [
    {
        "name": "пистолет",
        "type": "hand",
        "description": "крутой пистолет в руке",
        "price": 50000,
        "image_file": "images/accessory_gun.png"
    }
]

# Встроенные фоны
DEFAULT_BACKGROUNDS = [
    {
        "name": "дом",
        "description": "красивый дом со скатной крышей",
        "price": 200000,
        "image_file": "images/background_home.jpg"
    },
    {
        "name": "офис",
        "description": "современный офис",
        "price": 150000,
        "image_file": "images/background_office.jpg"
    },
    {
        "name": "казино",
        "description": "люксовое казино",
        "price": 250000,
        "image_file": "images/background_casino.jpg"
    },
    {
        "name": "пляж",
        "description": "экзотический пляж",
        "price": 180000,
        "image_file": "images/background_beach.jpg"
    },
    {
        "name": "улица",
        "description": "модная городская улица",
        "price": 120000,
        "image_file": "images/background_street.jpg"
    }
]

# Инициализация стандартных скинов, аксессуаров и фонов в БД
def init_accessories_and_backgrounds():
    """Добавляет встроенные скины, аксессуары и фоны в базу, если их там еще нет"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Добавляем стандартные скины - ОЧЕНЬ ВАЖНО
        for skin in DEFAULT_SKINS:
            cursor.execute('''
                INSERT OR IGNORE INTO skins (name, description, price, image_file, is_available)
                VALUES (?, ?, ?, ?, TRUE)
            ''', (skin['name'], skin['description'], skin['price'], skin['image_file']))
            logger.info(f"📦 скин инициализирован: {skin['name']}")
        
        # Добавляем стандартные аксессуары (проверяем что их еще нет)
        for acc in DEFAULT_ACCESSORIES:
            cursor.execute('SELECT accessory_id FROM accessories WHERE name = ? AND type = ?', 
                          (acc['name'], acc['type']))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO accessories (name, type, description, price, image_file, is_available)
                    VALUES (?, ?, ?, ?, ?, TRUE)
                ''', (acc['name'], acc['type'], acc['description'], acc['price'], acc['image_file']))
        
        # Добавляем стандартные фоны (проверяем что их еще нет)
        for bg in DEFAULT_BACKGROUNDS:
            cursor.execute('SELECT background_id FROM backgrounds WHERE name = ?', (bg['name'],))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO backgrounds (name, description, price, image_file, is_available)
                    VALUES (?, ?, ?, ?, TRUE)
                ''', (bg['name'], bg['description'], bg['price'], bg['image_file']))
        
        conn.commit()
        
        # Проверим что скины действительно создались
        cursor.execute('SELECT COUNT(*) FROM skins')
        skin_count = cursor.fetchone()[0]
        logger.info(f"✅ инициализация завершена: {skin_count} скин(ов) в БД")
        
    except Exception as e:
        logger.error(f"❌ ошибка инициализации аксессуаров: {e}")
    finally:
        conn.close()

# Получение всех доступных аксессуаров
def get_all_accessories():
    """Получает все доступные аксессуары"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM accessories WHERE is_available = TRUE ORDER BY type, price')
    accessories = cursor.fetchall()
    conn.close()
    
    return accessories

# Получение аксессуаров по типу
def get_accessories_by_type(acc_type):
    """Получает аксессуары определенного типа (head, hand, body, feet)"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM accessories WHERE type = ? AND is_available = TRUE ORDER BY price', (acc_type,))
    accessories = cursor.fetchall()
    conn.close()
    
    return accessories

# Получение купленных пользователем аксессуаров
def get_user_accessories(user_id):
    """Получает список посчитанных пользователем аксессуаров"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT a.* FROM accessories a
        INNER JOIN user_items ui ON a.accessory_id = ui.accessory_id
        WHERE ui.user_id = ?
        ORDER BY a.type, a.price
    ''', (user_id,))
    
    accessories = cursor.fetchall()
    conn.close()
    
    return accessories

# Проверка, купил ли пользователь аксессуар
def has_accessory(user_id, accessory_id):
    """Проверяет, купил ли пользователь конкретный аксессуар"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT 1 FROM user_items WHERE user_id = ? AND accessory_id = ?', (user_id, accessory_id))
    result = cursor.fetchone()
    conn.close()
    
    return result is not None

# Покупка аксессуара
def buy_accessory(user_id, accessory_id):
    """Покупает аксессуар для пользователя и сразу его надевает"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Получаем информацию об аксессуаре
        cursor.execute('SELECT price, name FROM accessories WHERE accessory_id = ?', (accessory_id,))
        result = cursor.fetchone()
        
        if not result:
            return False, "❌ аксессуар не найден"
        
        price, acc_name = result
        
        # Проверяем, есть ли у пользователя столько денег
        user = get_user(user_id)
        if not user or user[5] < price:
            return False, f"❌ недостаточно денег. нужно {format_money(price)}"
        
        # Проверяем, не купил ли уже пользователь этот аксессуар
        if has_accessory(user_id, accessory_id):
            return False, "❌ ты уже купил этот аксессуар"
        
        # Вычитаем деньги
        update_user_money(user_id, -price)
        
        # Добавляем аксессуар в inventory
        cursor.execute('''
            INSERT INTO user_items (user_id, accessory_id)
            VALUES (?, ?)
        ''', (user_id, accessory_id))
        
        conn.commit()
        
        # АВТОМАТИЧЕСКИ НАДЕВАЕМ АКСЕССУАР
        success_equip, msg_equip = equip_accessory(user_id, accessory_id)
        
        # Кэш уже очищен в equip_accessory()
        
        return True, f"✅ {acc_name} куплен и надет! потрачено {format_money(price)}"
    except Exception as e:
        logger.error(f"Ошибка при покупке аксессуара: {e}")
        return False, "⚠️ ошибка при покупке"
    finally:
        conn.close()

# Надевание аксессуара
def equip_accessory(user_id, accessory_id):
    """Одевает аксессуар"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Получаем тип аксессуара
        cursor.execute('SELECT type FROM accessories WHERE accessory_id = ?', (accessory_id,))
        result = cursor.fetchone()
        
        if not result:
            return False, "❌ аксессуар не найден"
        
        acc_type = result[0]
        
        # Проверяем, купил ли пользователь этот аксессуар
        if not has_accessory(user_id, accessory_id):
            return False, "❌ ты не купил этот аксессуар"
        
        # Обновляем надетый аксессуар
        cursor.execute('SELECT 1 FROM user_equipped WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            # Обновляем существующую запись
            if acc_type == "head":
                cursor.execute('UPDATE user_equipped SET head_accessory = ? WHERE user_id = ?', (accessory_id, user_id))
            elif acc_type == "hand":
                cursor.execute('UPDATE user_equipped SET hand_accessory = ? WHERE user_id = ?', (accessory_id, user_id))
            elif acc_type == "body":
                cursor.execute('UPDATE user_equipped SET body_accessory = ? WHERE user_id = ?', (accessory_id, user_id))
            elif acc_type == "feet":
                cursor.execute('UPDATE user_equipped SET feet_accessory = ? WHERE user_id = ?', (accessory_id, user_id))
        else:
            # Создаем новую запись
            if acc_type == "head":
                cursor.execute('INSERT INTO user_equipped (user_id, head_accessory) VALUES (?, ?)', (user_id, accessory_id))
            elif acc_type == "hand":
                cursor.execute('INSERT INTO user_equipped (user_id, hand_accessory) VALUES (?, ?)', (user_id, accessory_id))
            elif acc_type == "body":
                cursor.execute('INSERT INTO user_equipped (user_id, body_accessory) VALUES (?, ?)', (user_id, accessory_id))
            elif acc_type == "feet":
                cursor.execute('INSERT INTO user_equipped (user_id, feet_accessory) VALUES (?, ?)', (user_id, accessory_id))
        
        conn.commit()
        
        # Очищаем кэш персонажа
        clear_character_cache(user_id)
        
        return True, "✅ аксессуар надет"
    except Exception as e:
        logger.error(f"Ошибка при надевании аксессуара: {e}")
        return False, "⚠️ ошибка при надевании"
    finally:
        conn.close()

# Снятие аксессуара
def unequip_accessory(user_id, acc_type):
    """Снимает аксессуар определенного типа"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        if acc_type == "head":
            cursor.execute('UPDATE user_equipped SET head_accessory = NULL WHERE user_id = ?', (user_id,))
        elif acc_type == "hand":
            cursor.execute('UPDATE user_equipped SET hand_accessory = NULL WHERE user_id = ?', (user_id,))
        elif acc_type == "body":
            cursor.execute('UPDATE user_equipped SET body_accessory = NULL WHERE user_id = ?', (user_id,))
        elif acc_type == "feet":
            cursor.execute('UPDATE user_equipped SET feet_accessory = NULL WHERE user_id = ?', (user_id,))
        
        conn.commit()
        
        # Очищаем кэш персонажа
        clear_character_cache(user_id)
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при снятии аксессуара: {e}")
        return False
    finally:
        conn.close()

# Получение надетых аксессуаров пользователя
def get_user_equipped_accessories(user_id):
    """Получает надетые аксессуары пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM user_equipped WHERE user_id = ?', (user_id,))
    equipped = cursor.fetchone()
    conn.close()
    
    if not equipped:
        return None
    
    return {
        'head': equipped[1],
        'hand': equipped[2],
        'body': equipped[3],
        'feet': equipped[4]
    }

# Получение имен надетых аксессуаров пользователя
def get_user_equipped_names(user_id):
    """Получает имена всех надетых аксессуаров пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            (SELECT name FROM accessories WHERE accessory_id = ue.head_accessory LIMIT 1) as head_name,
            (SELECT name FROM accessories WHERE accessory_id = ue.hand_accessory LIMIT 1) as hand_name,
            (SELECT name FROM accessories WHERE accessory_id = ue.body_accessory LIMIT 1) as body_name,
            (SELECT name FROM accessories WHERE accessory_id = ue.feet_accessory LIMIT 1) as feet_name
        FROM user_equipped ue
        WHERE ue.user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return {'head': None, 'hand': None, 'body': None, 'feet': None}
    
    return {
        'head': result[0],
        'hand': result[1],
        'body': result[2],
        'feet': result[3]
    }

# Проверка, надет ли конкретный аксессуар
def is_accessory_equipped(user_id, accessory_id):
    """Проверяет, надет ли конкретный аксессуар на пользователе"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 1 FROM user_equipped 
        WHERE user_id = ? AND (
            head_accessory = ? OR 
            hand_accessory = ? OR 
            body_accessory = ? OR 
            feet_accessory = ?
        )
    ''', (user_id, accessory_id, accessory_id, accessory_id, accessory_id))
    
    result = cursor.fetchone()
    conn.close()
    
    return result is not None

# Проверка, применен ли конкретный фон
def is_background_equipped(user_id, background_id):
    """Проверяет, применен ли конкретный фон у пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT background_accessory FROM user_equipped 
        WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return False
    
    return result[0] == background_id

# Получение имени активного фона пользователя
def get_user_background_name(user_id):
    """Получает имя активного фона пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.name FROM backgrounds b
        INNER JOIN user_equipped ue ON b.background_id = ue.background_accessory
        WHERE ue.user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else 'нет'

# ==========================================
# 🎨 ФОНЫ
# ==========================================

# Получение всех доступных фонов
def get_all_backgrounds():
    """Получает все доступные фоны"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM backgrounds WHERE is_available = TRUE ORDER BY price')
    backgrounds = cursor.fetchall()
    conn.close()
    
    return backgrounds

# Получение купленных пользователем фонов
def get_user_backgrounds(user_id):
    """Получает список купленных пользователем фонов"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT b.* FROM backgrounds b
        INNER JOIN user_items ui ON b.background_id = ui.accessory_id
        WHERE ui.user_id = ? AND ui.accessory_id IS NOT NULL
        ORDER BY b.price
    ''', (user_id,))
    
    backgrounds = cursor.fetchall()
    conn.close()
    
    return backgrounds

# Проверка, купил ли пользователь фон
def has_background(user_id, background_id):
    """Проверяет, купил ли пользователь конкретный фон"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # В таблице user_items используем наоборот - background_id как accessory_id
    cursor.execute('''
        SELECT 1 FROM user_items WHERE user_id = ? AND accessory_id = ?
    ''', (user_id, background_id))
    result = cursor.fetchone()
    conn.close()
    
    return result is not None

# Покупка фона
def buy_background(user_id, background_id):
    """Покупает фон для пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Получаем цену фона
        cursor.execute('SELECT price FROM backgrounds WHERE background_id = ?', (background_id,))
        result = cursor.fetchone()
        
        if not result:
            return False, "❌ фон не найден"
        
        price = result[0]
        
        # Проверяем, есть ли у пользователя столько денег
        user = get_user(user_id)
        if not user or user[5] < price:
            return False, f"❌ недостаточно денег. нужно {format_money(price)}"
        
        # Проверяем, не купил ли уже пользователь этот фон
        if has_background(user_id, background_id):
            return False, "❌ ты уже купил этот фон"
        
        # Вычитаем деньги
        update_user_money(user_id, -price)
        
        # Добавляем фон в inventory (используем background_id как accessory_id)
        cursor.execute('''
            INSERT INTO user_items (user_id, accessory_id)
            VALUES (?, ?)
        ''', (user_id, background_id))
        
        conn.commit()
        
        # Очищаем кэш персонажа при покупке фона
        clear_character_cache(user_id)
        
        return True, f"✅ фон куплен! потрачено {format_money(price)}"
    except Exception as e:
        logger.error(f"Ошибка при покупке фона: {e}")
        return False, "⚠️ ошибка при покупке"
    finally:
        conn.close()

# Установка активного фона
def set_active_background(user_id, background_id):
    """Устанавливает активный фон для пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Проверяем, купил ли пользователь этот фон
        if not has_background(user_id, background_id):
            return False, "❌ ты не купил этот фон"
        
        # Обновляем фон в таблице user_equipped
        cursor.execute('SELECT 1 FROM user_equipped WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            cursor.execute('UPDATE user_equipped SET background_accessory = ? WHERE user_id = ?', (background_id, user_id))
        else:
            cursor.execute('INSERT INTO user_equipped (user_id, background_accessory) VALUES (?, ?)', (user_id, background_id))
        
        conn.commit()
        
        # Очищаем кэш персонажа при смене фона
        clear_character_cache(user_id)
        
        return True, "✅ фон установлен"
    except Exception as e:
        logger.error(f"Ошибка при установке фона: {e}")
        return False, "⚠️ ошибка при установке"
    finally:
        conn.close()

# Получение активного фона пользователя
def get_user_background(user_id):
    """Получает активный фон пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT b.* FROM backgrounds b
        INNER JOIN user_equipped ue ON b.background_id = ue.background_accessory
        WHERE ue.user_id = ?
    ''', (user_id,))
    
    background = cursor.fetchone()
    conn.close()
    
    return background

# ==========================================
# 🎭 СКИНЫ (ПЕРСОНАЖИ)
# ==========================================

# Получение активного скина пользователя
def get_user_skin(user_id):
    """Получает активный скин пользователя"""
    # Если не в кэше, загружаем из БД
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT image_file FROM skins WHERE skin_id = (SELECT skin_id FROM user_skin WHERE user_id = ?)', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    # Возвращаем скин или дефолт
    return result[0] if result else 'images/character_black.jpg'

# Получение имени активного скина пользователя
def get_user_skin_name(user_id):
    """Получает имя активного скина пользователя"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM skins WHERE skin_id = (SELECT skin_id FROM user_skin WHERE user_id = ?)', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    # Возвращаем имя скина или дефолт
    return result[0] if result else 'черный персонаж'

# Установка активного скина пользователю
def set_user_skin(user_id, skin_id):
    """Устанавливает активный скин пользователю"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT 1 FROM user_skin WHERE user_id = ?', (user_id,))
        if cursor.fetchone():
            cursor.execute('UPDATE user_skin SET skin_id = ? WHERE user_id = ?', (skin_id, user_id))
        else:
            cursor.execute('INSERT INTO user_skin (user_id, skin_id) VALUES (?, ?)', (user_id, skin_id))
        
        conn.commit()
        
        # Очищаем кэши персонажа
        clear_character_cache(user_id)
        
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

# ==========================================# 🎨 ОТОБРАЖЕНИЕ ПЕРСОНАЖА С АКСЕССУАРАМИ
# ==========================================

def create_character_with_accessories(user_id, output_file='temp/temp_character.png'):
    """Создает изображение персонажа с фоном и аксессуарами"""
    if not PIL_AVAILABLE:
        return None
    
    try:
        # Обеспечиваем наличие папки temp
        os.makedirs('temp', exist_ok=True)
        # Открываем одно соединение для всех запросов
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Получаем фон и аксессуары одним запросом
        cursor.execute('''
            SELECT ue.background_accessory, ue.head_accessory, ue.hand_accessory, ue.body_accessory, ue.feet_accessory
            FROM user_equipped ue
            WHERE ue.user_id = ?
        ''', (user_id,))
        equipped_result = cursor.fetchone()
        
        bg_id = None
        accessory_ids = []
        if equipped_result:
            bg_id = equipped_result[0]
            accessory_ids = [equipped_result[1], equipped_result[2], equipped_result[3], equipped_result[4]]
        
        bg_file = None
        # Загружаем файл фона если нужен
        if bg_id:
            cursor.execute('SELECT image_file FROM backgrounds WHERE background_id = ?', (bg_id,))
            bg_result = cursor.fetchone()
            if bg_result:
                bg_file = bg_result[0]
        
        # Загружаем файлы аксессуаров - фильтруем None и загружаем одним запросом
        acc_files = {}
        valid_acc_ids = [aid for aid in accessory_ids if aid is not None]
        if valid_acc_ids:
            placeholders = ','.join('?' * len(valid_acc_ids))
            cursor.execute(f'SELECT accessory_id, image_file FROM accessories WHERE accessory_id IN ({placeholders})', valid_acc_ids)
            for acc_id, img_file in cursor.fetchall():
                acc_files[acc_id] = img_file
        
        conn.close()
        
        # Загружаем изображения
        # Загружаем фон
        background_image = None
        if bg_file and os.path.exists(bg_file):
            try:
                background_image = Image.open(bg_file).convert('RGBA')
            except Exception:
                pass
        
        # Если нет фона, используем дефолтный
        if background_image is None and os.path.exists('images/default_background.jpg'):
            background_image = Image.open('images/default_background.jpg').convert('RGBA')
        
        # Загружаем скин персонажа
        skin_path = get_user_skin(user_id)
        try:
            character_image = Image.open(skin_path).convert('RGBA')
        except FileNotFoundError:
            logger.error(f"Скин не найден: {skin_path}")
            return None
        
        # Комбинируем фон и персонажа
        if background_image:
            # Убеждаемся что размеры совпадают
            if character_image.size != background_image.size:
                character_image = character_image.resize(background_image.size, Image.Resampling.LANCZOS)
            
            base_image = Image.alpha_composite(background_image, character_image)
        else:
            base_image = character_image
        
        # Накладываем аксессуары
        for acc_id in accessory_ids:
            if acc_id is None or acc_id not in acc_files:
                continue
            
            acc_file = acc_files[acc_id]
            try:
                accessory_image = Image.open(acc_file)
                
                if accessory_image.mode != 'RGBA':
                    accessory_image = accessory_image.convert('RGBA')
                
                # Убеждаемся что размеры совпадают
                if accessory_image.size != base_image.size:
                    accessory_image = accessory_image.resize(base_image.size, Image.Resampling.LANCZOS)
                
                # Накладываем аксессуар
                base_image = Image.alpha_composite(base_image, accessory_image)
            except Exception as e:
                pass
        
        # Преобразуем в RGB и сохраняем
        base_image = base_image.convert('RGB')
        base_image.save(output_file, 'PNG')
        return output_file
    except Exception as e:
        logger.error(f"Ошибка при создании персонажа с аксессуарами: {e}")
        return None

# Создание персонажа с одним аксессуаром для предпросмотра в магазине
def create_character_with_single_accessory(user_id, accessory_id, output_file='temp/temp_preview.png'):
    """Создает персонажа с одним конкретным аксессуаром для предпросмотра"""
    if not PIL_AVAILABLE:
        return None
    
    try:
        # Обеспечиваем наличие папки temp
        os.makedirs('temp', exist_ok=True)
        # Получаем скин пользователя
        base_image_path = get_user_skin(user_id)
        
        try:
            base_image = Image.open(base_image_path).convert('RGBA')
        except FileNotFoundError:
            return None
        
        # Получаем информацию об аксессуаре
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT image_file FROM accessories WHERE accessory_id = ?', (accessory_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        accessory_file = result[0]
        
        try:
            # Загружаем аксессуар
            accessory_image = Image.open(accessory_file)
            
            if accessory_image.mode != 'RGBA':
                accessory_image = accessory_image.convert('RGBA')
            
            # Убеждаемся что размеры совпадают
            if accessory_image.size != base_image.size:
                accessory_image = accessory_image.resize(base_image.size, Image.Resampling.LANCZOS)
            
            # Накладываем аксессуар
            base_image = Image.alpha_composite(base_image, accessory_image)
        except Exception as e:
            return None
        
        # Сохраняем
        base_image = base_image.convert('RGB')
        base_image.save(output_file, 'PNG')
        return output_file
    except Exception as e:
        logger.error(f"Ошибка при создании персонажа с аксессуаром: {e}")
        return None

def create_accessory_preview_with_background(user_id, accessory_id, output_file='temp/temp_accessory_preview.png'):
    """Создает превью аксессуара с персонажем и его текущим фоном в размере 600х300"""
    if not PIL_AVAILABLE:
        return None
    
    try:
        # Обеспечиваем наличие папки temp
        os.makedirs('temp', exist_ok=True)
        # Обеспечиваем наличие папки temp
        os.makedirs('temp', exist_ok=True)
        # Фиксированный размер для вывода
        OUTPUT_WIDTH = 600
        OUTPUT_HEIGHT = 300
        
        # Получаем текущий фон пользователя
        background = get_user_background(user_id)
        background_file = background[3] if background else 'images/default_background.jpg'
        
        # Загружаем фон и масштабируем до 600х300
        try:
            background_image = Image.open(background_file).convert('RGB')
            # Масштабируем фон пропорционально до размера 600х300
            background_image.thumbnail((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
            
            # Создаем финальное изображение белого цвета
            final_image = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(255, 255, 255))
            
            # Вставляем фон в центр
            bg_x = (OUTPUT_WIDTH - background_image.width) // 2
            bg_y = (OUTPUT_HEIGHT - background_image.height) // 2
            final_image.paste(background_image, (bg_x, bg_y))
            
            background_image = final_image
        except Exception:
            background_image = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(255, 255, 255))
        
        # Получаем скин пользователя
        skin_path = get_user_skin(user_id)
        try:
            character_image = Image.open(skin_path).convert('RGBA')
        except Exception:
            return None
        
        # Получаем аксессуар
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT image_file FROM accessories WHERE accessory_id = ?', (accessory_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        accessory_file = result[0]
        
        try:
            accessory_image = Image.open(accessory_file).convert('RGBA')
        except Exception:
            return None
        
        # Объединяем скин с аксессуаром (оба в их естественном размере)
        if accessory_image.size != character_image.size:
            accessory_image = accessory_image.resize(character_image.size, Image.Resampling.LANCZOS)
        
        character_with_accessory = Image.alpha_composite(character_image, accessory_image)
        
        # Масштабируем персонажа+аксессуар пропорционально до 600х300
        character_with_accessory.thumbnail((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
        
        # Создаем финальное изображение
        final_image = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), color=(255, 255, 255))
        
        # Вставляем фон (уже в размере 600х300 или меньше)
        final_image.paste(background_image, (0, 0))
        
        # Вставляем персонажа в центр снизу
        char_x = (OUTPUT_WIDTH - character_with_accessory.width) // 2
        char_y = OUTPUT_HEIGHT - character_with_accessory.height
        final_image.paste(character_with_accessory, (char_x, char_y), character_with_accessory)
        
        # Сохраняем результат
        final_image.save(output_file, 'PNG')
        return output_file
    except Exception as e:
        logger.error(f"Ошибка при создании превью аксессуара: {e}")
        return None

def create_background_preview(user_id, background_id, output_file='temp/temp_background_preview.png'):
    """Создает превью фона с персонажем и всеми текущими аксессуарами"""
    if not PIL_AVAILABLE:
        return None
    
    try:
        # Обеспечиваем наличие папки temp
        os.makedirs('temp', exist_ok=True)
        # Загружаем фон
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT image_file FROM backgrounds WHERE background_id = ?', (background_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return None
        
        background_file = result[0]
        
        try:
            background_image = Image.open(background_file).convert('RGB')
            bg_width, bg_height = background_image.size
        except Exception:
            background_image = Image.new('RGB', (400, 500), color=(200, 200, 200))
            bg_width, bg_height = 400, 500
        
        # Получаем скин пользователя
        skin_path = get_user_skin(user_id)
        try:
            character_image = Image.open(skin_path).convert('RGBA')
        except Exception:
            conn.close()
            return None
        
        # Получаем все надетые аксессуары
        equipped = get_user_equipped_accessories(user_id)
        character_with_accessories = character_image.copy()
        
        if equipped:
            # Наслаиваем аксессуары в порядке (head, hand, body, feet)
            for slot_name in ['head', 'hand', 'body', 'feet']:
                accessory_id = equipped.get(slot_name)
                
                if accessory_id:
                    try:
                        cursor.execute('SELECT image_file FROM accessories WHERE accessory_id = ?', (accessory_id,))
                        acc_result = cursor.fetchone()
                        
                        if acc_result:
                            accessory_file = acc_result[0]
                            accessory_image = Image.open(accessory_file).convert('RGBA')
                            
                            # Масштабируем аксессуар под размер персонажа
                            if accessory_image.size != character_with_accessories.size:
                                accessory_image = accessory_image.resize(
                                    character_with_accessories.size, 
                                    Image.Resampling.LANCZOS
                                )
                            
                            # Наслаиваем аксессуар
                            character_with_accessories = Image.alpha_composite(
                                character_with_accessories, 
                                accessory_image
                            )
                    except Exception:
                        pass
        
        conn.close()
        
        # Вычисляем позицию для центрирования персонажа на фоне
        char_width, char_height = character_with_accessories.size
        x_position = (bg_width - char_width) // 2
        y_position = (bg_height - char_height) // 2
        
        # Создаем финальное изображение с фоном
        final_image = Image.new('RGBA', (bg_width, bg_height))
        background_rgba = background_image.convert('RGBA')
        final_image.paste(background_rgba, (0, 0))
        
        # Накладываем персонажа со всеми аксессуарами на фон
        final_image.paste(character_with_accessories, (x_position, y_position), character_with_accessories)
        
        # Сохраняем результат
        final_image = final_image.convert('RGB')
        final_image.save(output_file, 'PNG')
        return output_file
    except Exception as e:
        logger.error(f"Ошибка при создании превью фона: {e}")
        return None

# ==========================================# �️ МАГАЗИН (UI)
# ==========================================

async def show_shop_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню магазина"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ пользователь не найден")
        return
    
    money = user[5]
    is_user_admin = is_admin(user_id)
    
    keyboard = [
        [KeyboardButton("👕 магазин аксессуаров"), KeyboardButton("🎨 магазин фонов")]
    ]
    
    # Добавляем адміс магазин для администраторов
    if is_user_admin:
        keyboard.append([KeyboardButton("💎 админ магазин")])
    
    keyboard.append([KeyboardButton("назад")])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    text = f"""🛍️ <b>магазин</b>

баланс: <b>{format_money(money)}</b>

<b>👕 аксессуары:</b> украшения для персонажа
<b>🎨 фоны:</b> интерьеры для главного меню"""
    
    if is_user_admin:
        text += "\n<b>💎 админ магазин:</b> обмен коинов и товары для админов"
    
    text += "\n\nчто выбираешь?"
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='html')
        elif update.message:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='html')
    except Exception:
        pass

async def _show_accessory_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает карусель аксессуаров"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    money = user[5]
    accessories = get_all_accessories()
    
    # Отправляем список всех аксессуаров при первом входе (только если это не редактирование)
    if not update.callback_query:
        try:
            # Создаем список всех доступных аксессуаров
            accessories_list = "<b>список аксессуаров для покупки:</b>\n\n"
            for i, acc in enumerate(accessories, 1):
                acc_name = acc[1]
                acc_price = acc[4]
                accessories_list += f"{i}. {acc_name} — {format_money(acc_price)}\n"
            
            back_keyboard = [[KeyboardButton("назад")]]
            back_reply_markup = ReplyKeyboardMarkup(back_keyboard, resize_keyboard=True, one_time_keyboard=False)
            await update.message.reply_text(
                accessories_list,
                reply_markup=back_reply_markup,
                parse_mode='html'
            )
        except:
            pass
    
    # Дальше показываем карусель только при callback (навигация)
    if not accessories:
        text = "❌ аксессуаров не найдено"
        keyboard = [[InlineKeyboardButton("назад", callback_data="shop_menu")]]
    else:
        # Берем текущий индекс из контекста (по умолчанию 0)
        current_index = context.user_data.get('current_accessory_index', 0)
        if current_index >= len(accessories):
            current_index = 0
        
        context.user_data['current_accessory_index'] = current_index
        
        acc = accessories[current_index]
        acc_id = acc[0]
        acc_name = acc[1]
        acc_type = acc[2]
        acc_desc = acc[3]
        acc_price = acc[4]
        acc_image = acc[5]
        
        # Проверяем, есть ли у пользователя этот аксессуар
        owned = has_accessory(user_id, acc_id)
        equipped = is_accessory_equipped(user_id, acc_id) if owned else False
        
        type_emoji = {
            'head': '👒',
            'hand': '🖐️',
            'body': '📿',
            'feet': '👟'
        }.get(acc_type, '📦')
        
        # Статус одет/не одет
        status_icon = "✅" if (owned and equipped) else "❌"
        
        # Текст карточки
        if owned:
            status = "надет" if equipped else "не надет"
            text = (
                f"<b>{type_emoji} {acc_name}</b>\n"
                f"<i>{acc_desc}</i>\n\n"
                f"💰 цена: {format_money(acc_price)}\n"
                f"<b>уже куплен - {status}</b>"
            )
        else:
            text = (
                f"<b>{type_emoji} {acc_name}</b>\n"
                f"<i>{acc_desc}</i>\n\n"
                f"💰 цена: <b>{format_money(acc_price)}</b>\n"
                f"баланс: {format_money(money)}"
            )
        
        # Определяем callback_data для стрелок (отключены если только один аксессуар)
        arrow_callback = "shop_acc_disabled" if len(accessories) <= 1 else "shop_acc_prev"
        arrow_next_callback = "shop_acc_disabled" if len(accessories) <= 1 else "shop_acc_next"
        
        # Оформляем кнопки в зависимости от статуса владения
        if owned:
            # Если куплен - статусная кнопка с текстом состояния
            status_text = "открепить" if equipped else "прикрепить"
            keyboard = [
                [
                    InlineKeyboardButton("⬅️", callback_data=arrow_callback),
                    InlineKeyboardButton(status_icon, callback_data=f"shop_acc_toggle_{acc_id}"),
                    InlineKeyboardButton("➡️", callback_data=arrow_next_callback)
                ],
                [InlineKeyboardButton(status_text, callback_data=f"shop_acc_toggle_{acc_id}")]
            ]
        else:
            # Если не куплен - кнопка покупки
            keyboard = [
                [
                    InlineKeyboardButton("⬅️", callback_data=arrow_callback),
                    InlineKeyboardButton(status_icon, callback_data="shop_acc_status"),
                    InlineKeyboardButton("➡️", callback_data=arrow_next_callback)
                ],
                [InlineKeyboardButton("купить", callback_data=f"shop_acc_buy_{acc_id}")]
            ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Создаем превью аксессуара с фоном
    # Если аксессуар куплен но НЕ одет - показываем персонажа со всеми ДРУГИМИ одетыми аксессуарами
    # Если аксессуар не куплен - всегда показываем с этим аксессуаром
    acc_id = accessories[current_index][0] if accessories else None
    preview_file = None
    if acc_id:
        if owned and not equipped:
            # Если куплен но не одет - показываем персонажа со всеми одетыми аксессуарами (кроме этого)
            preview_file = create_character_with_accessories(user_id, output_file='temp/temp_acc_preview_no_current.png')
        else:
            # Если не куплен или одет - показываем с этим аксессуаром
            preview_file = create_accessory_preview_with_background(user_id, acc_id)
    
    # Обновляем сообщение или отправляем новое
    try:
        if update.callback_query:
            # Если есть callback_query - редактируем существующее сообщение
            try:
                # Всегда используем preview_file, если он есть
                if preview_file and os.path.exists(preview_file):
                    photo_file = preview_file
                else:
                    # На случай если превью не создалось - используем обычное изображение
                    photo_file = accessories[current_index][5] if accessories else None
                
                if photo_file and os.path.exists(photo_file):
                    with open(photo_file, 'rb') as photo:
                        await update.callback_query.edit_message_media(
                            media=InputMediaPhoto(
                                media=photo,
                                caption=text,
                                parse_mode='html'
                            ),
                            reply_markup=reply_markup
                        )
            except Exception as e:
                # Если не можем отредактировать медиа, пробуем отредактировать текст
                try:
                    await update.callback_query.edit_message_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
                except:
                    logger.error(f"Ошибка при редактировании сообщения: {e}")
        else:
            try:
                # Всегда используем preview_file для отправки
                if preview_file and os.path.exists(preview_file):
                    photo_file = preview_file
                else:
                    # На случай если превью не создалось - используем обычное изображение
                    photo_file = accessories[current_index][5] if accessories else None
                
                if photo_file and os.path.exists(photo_file):
                    with open(photo_file, 'rb') as photo:
                        await update.message.reply_photo(
                            photo=photo,
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode='html'
                        )
            except:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode='html'
                )
    except Exception as e:
        logger.error(f"Ошибка при показе карусели аксессуаров: {e}")

async def _show_background_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает карусель фонов"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    money = user[5]
    backgrounds = get_all_backgrounds()
    
    if not backgrounds:
        text = "❌ фонов не найдено"
        keyboard = [[InlineKeyboardButton("назад", callback_data="shop_menu")]]
    else:
        # Берем текущий индекс из контекста (по умолчанию 0)
        current_index = context.user_data.get('current_background_index', 0)
        if current_index >= len(backgrounds):
            current_index = 0
        
        context.user_data['current_background_index'] = current_index
        
        bg = backgrounds[current_index]
        bg_id = bg[0]
        bg_name = bg[1]
        bg_desc = bg[2]
        bg_price = bg[3]
        bg_image = bg[4]
        
        # Проверяем, купил ли пользователь фон
        owned = has_background(user_id, bg_id)
        equipped = is_background_equipped(user_id, bg_id) if owned else False
        
        # Текст карточки
        if owned:
            status = "применен ✅" if equipped else "куплен, не применен"
            text = (
                f"<b>🎨 {bg_name}</b>\n"
                f"<i>{bg_desc}</i>\n\n"
                f"💰 цена: {format_money(bg_price)}\n"
                f"<b>{status}</b>"
            )
        else:
            text = (
                f"<b>🎨 {bg_name}</b>\n"
                f"<i>{bg_desc}</i>\n\n"
                f"💰 цена: <b>{format_money(bg_price)}</b>\n"
                f"баланс: {format_money(money)}"
            )
        
        # Кнопка в зависимости от статуса
        if owned:
            # Если куплен - показываем убрать/применить
            middle_button = InlineKeyboardButton(
                "убрать" if equipped else "применить", 
                callback_data=f"shop_bg_toggle_{bg_id}"
            )
        else:
            # Если не куплен - показываем купить
            middle_button = InlineKeyboardButton("купить", callback_data=f"shop_bg_buy_{bg_id}")
        
        # Кнопки навигации
        keyboard = [
            [
                InlineKeyboardButton("⬅️", callback_data="shop_bg_prev"),
                middle_button,
                InlineKeyboardButton("➡️", callback_data="shop_bg_next")
            ],
            [InlineKeyboardButton("назад", callback_data="shop_menu")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Создаем превью фона с персонажем и аксессуарами
    bg_id = backgrounds[current_index][0] if backgrounds else None
    preview_file = None
    if bg_id:
        preview_file = create_background_preview(user_id, bg_id)
    
    # Обновляем сообщение или отправляем новое
    try:
        if update.callback_query:
            # Если есть callback_query - пытаемся отредактировать
            try:
                # Сначала убираем кнопки старого сообщения
                await update.callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([]))
            except:
                pass
            
            # Отправляем новое сообщение с фотографией
            try:
                photo_file = preview_file if preview_file else backgrounds[current_index][4]
                with open(photo_file, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
            except:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='html'
                )
        else:
            try:
                photo_file = preview_file if preview_file else backgrounds[current_index][4]
                with open(photo_file, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='html'
                    )
            except:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode='html'
                )
    except Exception as e:
        logger.error(f"Ошибка при показе карусели фонов: {e}")

async def show_wardrobe_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню гардероба"""
    user_id = update.effective_user.id
    
    keyboard = [
        [InlineKeyboardButton("👕 аксессуары", callback_data="wardrobe_accessories")],
        [InlineKeyboardButton("🎨 фоны", callback_data="wardrobe_backgrounds")],
        [InlineKeyboardButton("назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """👕 <b>гардероб</b>

здесь можно купить аксессуары и фоны для своего персонажа!

<b>аксессуары:</b> шляпы, цепи, часы, кольца и то всякое
<b>фоны:</b> разные интерьеры для главного меню

выбери что тебе нравится!"""
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='html')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='html')
    except Exception:
        pass

async def show_accessories_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает магазин аксессуаров (категорийный выбор)"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await update.callback_query.answer("❌ пользователь не найден", show_alert=True)
        return
    
    money = user[5]
    accessories = get_all_accessories()
    
    if not accessories:
        text = "❌ нет доступных аксессуаров"
        keyboard = [[InlineKeyboardButton("назад", callback_data="wardrobe_menu")]]
    else:
        # Группируем аксессуары по типам
        by_type = {}
        for acc in accessories:
            acc_type = acc[2]  # type
            if acc_type not in by_type:
                by_type[acc_type] = []
            by_type[acc_type].append(acc)
        
        # Создаем кнопки для каждого типа
        keyboard = []
        type_names = {
            'head': '👒 на голову',
            'hand': '🖐️ на руки',
            'body': '📿 на тело',
            'feet': '👟 на ноги'
        }
        
        for acc_type in sorted(by_type.keys()):
            keyboard.append([InlineKeyboardButton(
                type_names.get(acc_type, acc_type),
                callback_data=f"acc_type_{acc_type}"
            )])
        
        keyboard.append([InlineKeyboardButton("назад", callback_data="wardrobe_menu")])
        
        text = f"👕 <b>магазин аксессуаров</b>\n\nбаланс: {format_money(money)}\n\nвыбери категорию:"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='html')
    except Exception:
        pass

async def show_backgrounds_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает магазин фонов (категорийный выбор)"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        await update.callback_query.answer("❌ пользователь не найден", show_alert=True)
        return
    
    money = user[5]
    backgrounds = get_all_backgrounds()
    
    if not backgrounds:
        text = "❌ нет доступных фонов"
        keyboard = [[InlineKeyboardButton("назад", callback_data="wardrobe_menu")]]
    else:
        # Создаем кнопки для каждого фона
        keyboard = []
        for i, bg in enumerate(backgrounds):
            bg_name = bg[1]  # name
            bg_price = bg[3]  # price
            has_bg = has_background(user_id, bg[0])  # background_id
            
            if has_bg:
                button_text = f"✅ {bg_name}"
            else:
                button_text = f"💰 {bg_name} ({format_money(bg_price)})"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"bg_view_{bg[0]}")])
        
        keyboard.append([InlineKeyboardButton("назад", callback_data="wardrobe_menu")])
        
        text = f"🎨 <b>магазин фонов</b>\n\nбаланс: {format_money(money)}\n\nвыбери фон:"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='html')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='html')
    except Exception:
        pass

# ==========================================
# 🛒 ОБРАБОТЧИКИ CALLBACK'ОВ МАГАЗИНА
# ==========================================

async def handle_shop_accessories_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает показ карусели аксессуаров"""
    context.user_data['current_accessory_index'] = 0
    await _show_accessory_carousel(update, context)

async def handle_shop_backgrounds_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает сообщение о недоступности фонов"""
    query = update.callback_query
    await query.answer("😔 фоны временно недоступны", show_alert=True)
    # Возвращаемся в меню магазина
    await show_shop_main(update, context)

async def handle_shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает в главное меню магазина"""
    await show_shop_main(update, context)

async def handle_shop_acc_nav(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    """Навигация по аксессуарам"""
    accessories = get_all_accessories()
    
    # Если только один аксессуар - просто ответить, не перезагружать
    if len(accessories) <= 1:
        await update.callback_query.answer()
        return
    
    current_index = context.user_data.get('current_accessory_index', 0)
    
    if direction == "next":
        current_index = (current_index + 1) % len(accessories)
    elif direction == "prev":
        current_index = (current_index - 1) % len(accessories)
    
    context.user_data['current_accessory_index'] = current_index
    await _show_accessory_carousel(update, context)

async def handle_shop_bg_nav(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    """Навигация по фонам"""
    backgrounds = get_all_backgrounds()
    current_index = context.user_data.get('current_background_index', 0)
    
    if direction == "next":
        current_index = (current_index + 1) % len(backgrounds)
    elif direction == "prev":
        current_index = (current_index - 1) % len(backgrounds)
    
    context.user_data['current_background_index'] = current_index
    await _show_background_carousel(update, context)

async def handle_shop_buy_accessory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупает аксессуар"""
    query = update.callback_query
    user_id = query.from_user.id
    accessory_id = int(query.data.replace("shop_acc_buy_", ""))
    
    success, message = buy_accessory(user_id, accessory_id)
    
    if success:
        await query.answer(message, show_alert=True)
        # Обновляем текущий аксессуар (показываем обновленную информацию)
        await _show_accessory_carousel(update, context)
    else:
        await query.answer(message, show_alert=True)

async def handle_shop_buy_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупает фон"""
    query = update.callback_query
    user_id = query.from_user.id
    background_id = int(query.data.replace("shop_bg_buy_", ""))
    
    success, message = buy_background(user_id, background_id)
    
    if success:
        await query.answer(message, show_alert=True)
        # Обновляем текущий фон (показываем обновленную информацию)
        await _show_background_carousel(update, context)
    else:
        await query.answer(message, show_alert=True)

async def handle_shop_toggle_accessory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключает аксессуар (одеть/снять)"""
    query = update.callback_query
    user_id = query.from_user.id
    accessory_id = int(query.data.replace("shop_acc_toggle_", ""))
    
    # Проверяем, надет ли аксессуар
    equipped = is_accessory_equipped(user_id, accessory_id)
    
    try:
        # Получаем тип аксессуара для снятия
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT type FROM accessories WHERE accessory_id = ?', (accessory_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await query.answer("❌ аксессуар не найден!", show_alert=True)
            return
        
        acc_type = result[0]
        
        if equipped:
            # Снимаем аксессуар
            unequip_accessory(user_id, acc_type)
            message = "✅ аксессуар снят"
        else:
            # Одеваем аксессуар
            equip_accessory(user_id, accessory_id)
            message = "✅ аксессуар надет"
        
        # Очищаем кэш персонажа
        clear_character_cache(user_id)
        
        await query.answer(message, show_alert=True)
        # Обновляем карусель
        await _show_accessory_carousel(update, context)
    except Exception as e:
        logger.error(f"Ошибка при переключении аксессуара: {e}")
        await query.answer("❌ произошла ошибка!", show_alert=True)

async def handle_shop_toggle_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключает фон (применить/убрать)"""
    query = update.callback_query
    user_id = query.from_user.id
    background_id = int(query.data.replace("shop_bg_toggle_", ""))
    
    try:
        # Проверяем, применен ли фон
        equipped = is_background_equipped(user_id, background_id)
        
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        if equipped:
            # Убираем фон (применяем default)
            default_bg = cursor.execute('SELECT background_id FROM backgrounds WHERE name = ?', ('default',)).fetchone()
            if default_bg:
                cursor.execute('UPDATE user_equipped SET background_accessory = ? WHERE user_id = ?', (default_bg[0], user_id))
            message = "✅ фон убран"
        else:
            # Применяем фон
            cursor.execute('UPDATE user_equipped SET background_accessory = ? WHERE user_id = ?', (background_id, user_id))
            message = "✅ фон применен"
        
        conn.commit()
        conn.close()
        
        # Очищаем кэш персонажа
        clear_character_cache(user_id)
        
        await query.answer(message, show_alert=True)
        # Обновляем карусель
        await _show_background_carousel(update, context)
    except Exception as e:
        logger.error(f"Ошибка при переключении фона: {e}")
        await query.answer("❌ произошла ошибка!", show_alert=True)
