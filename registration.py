import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import logging
import os
import time
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

# настройка логирования для библиотеки httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# используем локальные файлы или вообще убираем фото
USE_PHOTOS = True

# кэш для проверки существования фото файлов
photo_cache = {}

def cached_photo_exists(filename):
    """Кэшированная проверка существования файла"""
    if filename not in photo_cache:
        photo_cache[filename] = os.path.exists(filename)
    return photo_cache[filename]

from utils import format_money

# функция для проверки находится ли пользователь в процессе чистки
def is_cleaning_in_progress(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    user_data = context.user_data
    return user_data.get('is_cleaning', False)

# инициализация базы данных - ИСПРАВЛЕННАЯ ВЕРСИЯ (без удаления таблиц)
def init_db():
    conn = sqlite3.connect('gangster_bot.db', timeout=30.0, check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    
    # СОЗДАЕМ ТАБЛИЦЫ ТОЛЬКО ЕСЛИ ИХ НЕТ (без DROP TABLE)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            gender TEXT,
            color TEXT,
            money INTEGER DEFAULT 1000,
            is_admin BOOLEAN DEFAULT FALSE,
            is_main_admin BOOLEAN DEFAULT FALSE,
            registered BOOLEAN DEFAULT FALSE,
            banned BOOLEAN DEFAULT FALSE,
            ban_duration INTEGER DEFAULT 0,
            ban_start_time REAL DEFAULT 0,
            banned_by INTEGER,
            ban_reason TEXT,
            disable_transfer_confirmation BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_transfers (
            transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_user_id INTEGER,
            tg_user_id INTEGER,
            transfer_data TEXT,
            completed BOOLEAN DEFAULT FALSE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            shit_cleaned INTEGER DEFAULT 0,
            milk_collected INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS money_transfers (
            transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            amount INTEGER,
            transfer_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users (user_id),
            FOREIGN KEY (to_user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            timestamp REAL
        )
    ''')
    
    # Добавляем недостающие колонки в таблицу users, если их нет
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN banned BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass  # колонка уже существует

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN ban_duration INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN ban_start_time REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN banned_by INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN disable_transfer_confirmation BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN disable_transfer_notifications BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN disable_news_notifications BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN disable_system_notifications BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN disable_referral_notifications BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_gangster_plus BOOLEAN DEFAULT FALSE")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # Новые колонки для админ системы
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN admin_currency INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_admin_exchange_time REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN admin_exchange_week_start REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN admin_exchanged_this_week INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN admin_warnings INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN boost_2x_until REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN gangster_plus_until REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_plus_weekly_payout REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_skins (
            user_id INTEGER,
            skin_id INTEGER,
            PRIMARY KEY (user_id, skin_id)
        )
    ''')

    # Таблица для статистики реферала
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referral_stats (
            user_id INTEGER PRIMARY KEY,
            referrals_count INTEGER DEFAULT 0,
            total_referral_earnings INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для донатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS donations (
            donation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            currency TEXT,
            payment_system TEXT,
            status TEXT,
            donation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для аксессуаров (костюмов)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accessories (
            accessory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            price INTEGER DEFAULT 0,
            image_file TEXT,
            is_available BOOLEAN DEFAULT TRUE
        )
    ''')

    # Таблица для купленных пользователем предметов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            accessory_id INTEGER NOT NULL,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (accessory_id) REFERENCES accessories (accessory_id)
        )
    ''')

    # Таблица для надетых предметов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_equipped (
            user_id INTEGER PRIMARY KEY,
            head_accessory INTEGER DEFAULT NULL,
            hand_accessory INTEGER DEFAULT NULL,
            body_accessory INTEGER DEFAULT NULL,
            feet_accessory INTEGER DEFAULT NULL,
            background_accessory INTEGER DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для фонов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backgrounds (
            background_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER DEFAULT 0,
            image_file TEXT,
            is_available BOOLEAN DEFAULT TRUE
        )
    ''')

    # Таблица для скинов (персонажей)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skins (
            skin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER DEFAULT 0,
            image_file TEXT,
            is_available BOOLEAN DEFAULT TRUE
        )
    ''')

    # Таблица для активного скина пользователя
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_skin (
            user_id INTEGER PRIMARY KEY,
            skin_id INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (skin_id) REFERENCES skins (skin_id)
        )
    ''')

    # Таблица для домов пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_homes (
            user_id INTEGER PRIMARY KEY,
            home_id INTEGER NOT NULL,
            purchased_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для шкафа со скинами в доме
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS home_wardrobe (
            user_id INTEGER PRIMARY KEY,
            slot1_skin_id INTEGER,
            slot2_skin_id INTEGER,
            slot3_skin_id INTEGER,
            slot4_skin_id INTEGER,
            slot5_skin_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для бизнеса пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_business (
            user_id INTEGER PRIMARY KEY,
            business_id INTEGER NOT NULL,
            purchased_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_material INTEGER DEFAULT 0,
            last_delivery_time REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Таблица для истории заказов сырья
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS business_raw_orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            ordered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivery_time REAL,
            expires_at REAL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ база данных инициализирована (таблицы созданы при необходимости)")

# функции для временного бана
def temp_ban_user(user_id, duration_seconds, banned_by_admin_id=None, reason=""):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET banned = TRUE, ban_duration = ?, ban_start_time = ?, banned_by = ?, ban_reason = ?
        WHERE user_id = ?
    ''', (duration_seconds, time.time(), banned_by_admin_id, reason, user_id))
    conn.commit()
    conn.close()

def get_ban_remaining_time(user_id):
    try:
        user = get_user(user_id)
        if not user or not user[9]:  # banned
            return 0
        
        ban_duration = user[10] if len(user) > 10 else 0  # ban_duration
        ban_start_time = user[11] if len(user) > 11 else 0  # ban_start_time
        
        # Защита от None значений
        if ban_duration is None:
            ban_duration = 0
        if ban_start_time is None:
            ban_start_time = 0
        
        if ban_duration == 0:  # перманентный бан
            return -1
        
        elapsed = time.time() - ban_start_time
        remaining = max(0, ban_duration - elapsed)
        return remaining
    except Exception as e:
        print(f"❌ ошибка в get_ban_remaining_time: {e}")
        return 0

def format_ban_time(seconds):
    if seconds == -1:
        return "навсегда"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    elif hours > 0:
        return f"{hours}ч {minutes}м {secs}с"
    elif minutes > 0:
        return f"{minutes}м {secs}с"
    else:
        return f"{secs}с"

# функция для проверки является ли пользователь главным админом
def is_main_admin(user_id):
    user = get_user(user_id)
    return user and user[7]  # is_main_admin

# функция для проверки прав на бан
def can_ban_user(admin_id, target_id):
    if admin_id == target_id:
        return False, "нельзя забанить самого себя!"
    
    admin = get_user(admin_id)
    target = get_user(target_id)
    
    if not admin or not target:
        return False, "пользователь не найден!"
    
    if target[7]:  # is_main_admin
        return False, "нельзя забанить главного админа!"
    
    if target[6] and not admin[7]:  # target is admin and admin not main
        return False, "нельзя банить других админов!"
    
    return True, ""

# функция для логирования действий админов
def log_admin_action(admin_id, action, target_id=None, details=""):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (admin_id, action, target_id, details, time.time()))
    conn.commit()
    conn.close()

def init_financial_logs_db():
    """Инициализация таблицы логирования финансовых операций"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS financial_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            details TEXT,
            timestamp REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def log_financial_transaction(user_id: int, action_type: str, amount: int, details: str = ""):
    """Логирует финансовую операцию пользователя и удаляет логи старше 7 дней"""
    try:
        init_financial_logs_db()
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        current_time = time.time()
        
        cursor.execute('''
            INSERT INTO financial_logs (user_id, action_type, amount, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action_type, amount, details, current_time))
        
        # Удаляем логи старше 7 дней (7 * 86400 = 604800 секунд)
        seven_days_ago = current_time - 604800
        cursor.execute('DELETE FROM financial_logs WHERE timestamp < ?', (seven_days_ago,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка при логировании финансовой транзакции: {e}")

def get_user_activity_logs(user_id: int, limit: int = 30):
    """Получает логи финансовой активности пользователя за последние 7 дней"""
    init_financial_logs_db()
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    seven_days_ago = time.time() - 604800
    
    try:
        cursor.execute('''
            SELECT action_type, amount, details, timestamp
            FROM financial_logs
            WHERE user_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, seven_days_ago, limit))
        
        logs = cursor.fetchall()
    finally:
        conn.close()
    
    return logs

def contains_emoji(text: str) -> bool:
    """Проверяет наличие эмодзи в строке"""
    import unicodedata
    for char in text:
        cat = unicodedata.category(char)
        if cat in ('So', 'Cn'):
            return True
        code = ord(char)
        if (0x1F600 <= code <= 0x1F64F) or \
           (0x1F300 <= code <= 0x1F5FF) or \
           (0x1F680 <= code <= 0x1F6FF) or \
           (0x1F700 <= code <= 0x1F77F) or \
           (0x1F780 <= code <= 0x1F7FF) or \
           (0x1F800 <= code <= 0x1F8FF) or \
           (0x1F900 <= code <= 0x1F9FF) or \
           (0x1FA00 <= code <= 0x1FA6F) or \
           (0x1FA70 <= code <= 0x1FAFF) or \
           (0x2600 <= code <= 0x26FF) or \
           (0x2700 <= code <= 0x27BF) or \
           (0xFE00 <= code <= 0xFE0F) or \
           (0x1F1E6 <= code <= 0x1F1FF):
            return True
    return False

# функция для проверки ника
def is_nickname_valid(nickname: str) -> tuple:
    if contains_emoji(nickname):
        return False, "❌ в нике нельзя использовать эмодзи! придумай имя без смайликов."

    nickname_lower = nickname.lower().strip()
    
    bot_gangster_variants = ['бот гангстер', 'ботгангстер', 'gangster bot', 'бот-гангстер']
    for variant in bot_gangster_variants:
        if variant in nickname_lower:
            return False, "😂 ой-ой! меня тоже зовут бот гангстер! давай не будем путаться - придумай другое имя!"
    
    if len(nickname) < 2:
        return False, "❌ слишком короткое имя. минимальная длина - 2 символа."
    
    if len(nickname) > 20:
        return False, "❌ слишком длинное имя. максимальная длина - 20 символов."
    
    if not any(c.isalpha() for c in nickname):
        return False, "❌ имя должно содержать буквы."
    
    return True, "✅ имя допустимо!"

def get_user(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()

    # Если пользователь найден и кортеж имеет меньше 19 элементов (старая схема БД), дополняем значениями по умолчанию
    if user and len(user) < 19:
        full_user = list(user)
        # Заполняем недостающие элементы в правильном порядке (с индекса 6 добавляем новые поля)
        expected_fields = [
            False, False, False, False,  # [6-9]: is_admin, is_main_admin, registered, banned
            0, 0, None, "",              # [10-13]: ban_duration, ban_start_time, banned_by, ban_reason
            False, False, False, False,  # [14-17]: disable_transfer_confirmation, disable_transfer_notifications, disable_news_notifications, disable_system_notifications
            False                        # [18]: is_gangster_plus
        ]
        
        for i in range(len(full_user) - 6, 19 - 6):
            if i < len(expected_fields):
                full_user.append(expected_fields[i])
            else:
                full_user.append(None)
        user = tuple(full_user)

    return user

# проверка является ли пользователь админом
def is_admin(user_id):
    """Проверяет, является ли пользователь админом или главным админом"""
    user = get_user(user_id)
    return user and (user[6] or user[7])  # is_admin (индекс 6) или is_main_admin (индекс 7)

def save_user(user_data):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Если передано меньше полей, дополняем значениями по умолчанию
    if len(user_data) < 19:
        full_user_data = list(user_data)
        # Заполняем недостающие поля в правильном порядке (с индекса 6 добавляем новые поля)
        expected_fields = [
            False, False, False, False,  # [6-9]: is_admin, is_main_admin, registered, banned
            0, 0, None, "",              # [10-13]: ban_duration, ban_start_time, banned_by, ban_reason
            False, False, False, False,  # [14-17]: disable_transfer_confirmation, disable_transfer_notifications, disable_news_notifications, disable_system_notifications
            False                        # [18]: is_gangster_plus
        ]
        
        for i in range(len(full_user_data) - 6, 19 - 6):
            if i < len(expected_fields):
                full_user_data.append(expected_fields[i])
            else:
                full_user_data.append(None)
        
        user_data = tuple(full_user_data)
    
    cursor.execute('''
        INSERT OR REPLACE INTO users
        (user_id, username, name, gender, color, money, is_admin, is_main_admin, registered, banned, ban_duration, ban_start_time, banned_by, ban_reason, disable_transfer_confirmation, disable_transfer_notifications, disable_news_notifications, disable_system_notifications, is_gangster_plus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', user_data)
    
    conn.commit()
    conn.close()

# функция для назначения админа
def make_admin(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    # Назначаем админом БЕЗ изменения баланса
    cursor.execute('UPDATE users SET is_admin = TRUE WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
        stats = cursor.fetchone()
        
        if not stats:
            # создаем запись статистики если ее нет (используем INSERT OR IGNORE в одно действие)
            cursor.execute('INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)', (user_id,))
            conn.commit()
            
            cursor.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
            stats = cursor.fetchone()
    finally:
        conn.close()
    
    return stats

def update_user_stats(user_id, shit_cleaned=0, milk_collected=0, money_earned=0):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    stats = get_user_stats(user_id)
    if not stats:
        conn.close()
        return
    
    new_shit_cleaned = (stats[1] if stats[1] is not None else 0) + shit_cleaned
    new_milk_collected = (stats[2] if stats[2] is not None else 0) + milk_collected
    new_total_earned = (stats[3] if stats[3] is not None else 0) + money_earned
    
    cursor.execute('''
        UPDATE user_stats 
        SET shit_cleaned = ?, milk_collected = ?, total_earned = ?
        WHERE user_id = ?
    ''', (new_shit_cleaned, new_milk_collected, new_total_earned, user_id))
    
    # обновляем деньги пользователя
    if money_earned > 0:
        user = get_user(user_id)
        new_money = user[5] + money_earned
        cursor.execute('UPDATE users SET money = ? WHERE user_id = ?', (new_money, user_id))
    
    conn.commit()
    conn.close()
    
    # Добавляем заработок рефэру (50% от заработка на работе)
    if money_earned > 0:
        from scam import add_referral_job_earnings
        add_referral_job_earnings(user_id, money_earned)

def update_user_money(user_id, amount, check_balance=False):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN IMMEDIATE")
        
        # Если нужно проверить баланс перед списанием
        if check_balance and amount < 0:
            cursor.execute("SELECT money FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or row[0] + amount < 0:
                conn.rollback()
                return None

        cursor.execute('UPDATE users SET money = money + ? WHERE user_id = ?', (amount, user_id))
        
        # Получаем новый баланс
        cursor.execute("SELECT money FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        new_money = row[0] if row else None
        
        conn.commit()
        return new_money
    except Exception as e:
        print(f"⚠️ Ошибка обновления денег: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def ban_user(user_id):
    update_user_field(user_id, 'banned', True)

def unban_user(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET banned = FALSE, ban_duration = 0, ban_start_time = 0, banned_by = NULL, ban_reason = "" WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# функции для администраторской валюты
def update_admin_currency(user_id, amount):
    """Обновить баланс администраторской валюты"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN IMMEDIATE")
        
        # Проверяем баланс при отрицательной сумме
        if amount < 0:
            cursor.execute("SELECT admin_currency FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or row[0] + amount < 0:
                conn.rollback()
                return None

        # Получаем текущее значение
        cursor.execute("SELECT admin_currency FROM users WHERE user_id = ?", (user_id,))
        old_row = cursor.fetchone()
        old_currency = old_row[0] if old_row else 0
        
        cursor.execute('UPDATE users SET admin_currency = admin_currency + ? WHERE user_id = ?', (amount, user_id))
        
        # Получаем новый баланс
        cursor.execute("SELECT admin_currency FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        new_currency = row[0] if row else None
        
        conn.commit()
        
        # Логируем операцию
        print(f"💎 обновлена админ валюта: user_id={user_id}, было={old_currency}, добавлено={amount}, теперь={new_currency}")
        
        return new_currency
    except Exception as e:
        print(f"❌ Ошибка обновления админ валюты: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def get_admin_currency(user_id):
    """Получить баланс администраторской валюты"""
    try:
        # Всегда берем свежие данные из БД
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Прямой запрос из БД для свежих данных
        cursor.execute('SELECT admin_currency FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return 0
        
        admin_currency = row[0]
        
        # Защита от None
        if admin_currency is None:
            admin_currency = 0
        
        # Преобразуем в целое число если нужно
        try:
            admin_currency = int(admin_currency)
        except (ValueError, TypeError):
            admin_currency = 0
        
        return max(0, admin_currency)  # гарантируем что результат >= 0
    except Exception as e:
        print(f"❌ ошибка в get_admin_currency: {e}")
        return 0

def can_exchange_admin_currency(user_id):
    """Проверить, может ли админ обменять валюту на деньги (максимум 5 коинов в неделю)"""
    try:
        MAX_EXCHANGE_PER_WEEK = 5
        
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT admin_exchange_week_start, admin_exchanged_this_week 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return True  # Если нет записи, можно обменять
        
        week_start = row[0] if row[0] else 0
        exchanged_this_week = row[1] if row[1] else 0
        
        current_time = time.time()
        week_seconds = 7 * 24 * 3600
        
        # Если прошла неделя, счетчик сбрасывается
        if week_start != 0 and (current_time - week_start) >= week_seconds:
            return True  # Можно обменять
        
        # Если не прошла неделя, проверяем лимит
        if exchanged_this_week < MAX_EXCHANGE_PER_WEEK:
            return True  # Еще есть лимит
        
        return False  # Лимит исчерпан
    except Exception as e:
        print(f"❌ ошибка в can_exchange_admin_currency: {e}")
        return False

def get_exchange_remaining_time(user_id):
    """Получить время до возможности следующего обмена (в секундах)"""
    try:
        MAX_EXCHANGE_PER_WEEK = 5
        
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT admin_exchange_week_start, admin_exchanged_this_week 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return 0
        
        week_start = row[0] if row[0] else 0
        exchanged_this_week = row[1] if row[1] else 0
        
        current_time = time.time()
        week_seconds = 7 * 24 * 3600
        
        # Если еще не было обмена
        if week_start == 0:
            return 0  # Обмен доступен
        
        time_passed = current_time - week_start
        
        # Если прошло более недели
        if time_passed >= week_seconds:
            return 0  # Обмен доступен
        
        remaining_time = week_seconds - time_passed
        return max(0, remaining_time)  # Время до конца недели
    except Exception as e:
        print(f"❌ ошибка в get_exchange_remaining_time: {e}")
        return 0

def get_exchange_remaining_coins(user_id):
    """Получить сколько коинов осталось обменять за эту неделю"""
    try:
        MAX_EXCHANGE_PER_WEEK = 5
        
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT admin_exchange_week_start, admin_exchanged_this_week 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return MAX_EXCHANGE_PER_WEEK
        
        week_start = row[0] if row[0] else 0
        exchanged_this_week = row[1] if row[1] else 0
        
        current_time = time.time()
        week_seconds = 7 * 24 * 3600
        
        # Если прошла неделя, сбрасываем счетчик
        if week_start != 0 and (current_time - week_start) >= week_seconds:
            return MAX_EXCHANGE_PER_WEEK
        
        remaining = MAX_EXCHANGE_PER_WEEK - exchanged_this_week
        return max(0, remaining)
    except Exception as e:
        print(f"❌ ошибка в get_exchange_remaining_coins: {e}")
        return 0

def exchange_admin_currency_to_money(user_id, amount):
    """Обменять администраторскую валюту на деньги (1 коин = 1млн денег, максимум 5 коинов в неделю)"""
    # Максимум 5 коинов в неделю
    MAX_EXCHANGE_PER_WEEK = 5
    EXCHANGE_RATE = 1000000  # 1 коин = 1 млн денег
    
    # Проверяем возможность обмена
    if not can_exchange_admin_currency(user_id):
        return None
    
    # Проверяем баланс админ валюты
    current_currency = get_admin_currency(user_id)
    if current_currency < amount:
        return None
    
    # Проверяем лимит за неделю
    if amount > MAX_EXCHANGE_PER_WEEK:
        return None
    
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN IMMEDIATE")
        
        # Получаем текущие данные пользователя
        cursor.execute("""
            SELECT admin_currency, admin_exchange_week_start, admin_exchanged_this_week 
            FROM users WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if not row or row[0] < amount:
            conn.rollback()
            return None
        
        current_time = time.time()
        week_start = row[1] if row[1] else 0
        exchanged_this_week = row[2] if row[2] else 0
        week_seconds = 7 * 24 * 3600
        
        # Проверяем прошла ли неделя
        if week_start != 0 and (current_time - week_start) >= week_seconds:
            # Неделя прошла, сбрасываем счетчик
            exchanged_this_week = 0
            week_start = current_time
        elif week_start == 0:
            # Первый раз обменивается
            week_start = current_time
        
        # Проверяем лимит за эту неделю
        if exchanged_this_week + amount > MAX_EXCHANGE_PER_WEEK:
            conn.rollback()
            return None
        
        # Рассчитываем деньги за обмен
        money_to_add = amount * EXCHANGE_RATE
        
        # Снимаем админ валюту
        cursor.execute('UPDATE users SET admin_currency = admin_currency - ? WHERE user_id = ?', (amount, user_id))
        
        # Добавляем деньги
        cursor.execute('UPDATE users SET money = money + ? WHERE user_id = ?', (money_to_add, user_id))
        
        # Обновляем статистику обмена на неделю
        cursor.execute('''
            UPDATE users 
            SET admin_exchange_week_start = ?, 
                admin_exchanged_this_week = admin_exchanged_this_week + ?,
                last_admin_exchange_time = ?
            WHERE user_id = ?
        ''', (week_start, amount, current_time, user_id))
        
        # Логируем транзакцию
        cursor.execute('''
            INSERT INTO money_transfers (from_user_id, to_user_id, amount)
            VALUES (?, ?, ?)
        ''', (user_id, user_id, -amount))
        
        conn.commit()
        
        # Возвращаем новый баланс денег
        cursor.execute("SELECT money FROM users WHERE user_id = ?", (user_id,))
        new_row = cursor.fetchone()
        new_money = new_row[0] if new_row else None
        
        print(f"💱 обмен валюты: user_id={user_id}, коинов={amount}, денег={money_to_add}, новый баланс денег={new_money}")
        
        return new_money
    except Exception as e:
        print(f"❌ Ошибка обмена админ валюты: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def add_admin_warning(user_id):
    """Добавить предупреждение админу"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        cursor.execute("BEGIN IMMEDIATE")
        
        cursor.execute('UPDATE users SET admin_warnings = admin_warnings + 1 WHERE user_id = ?', (user_id,))
        
        # Получаем новое количество предупреждений  
        cursor.execute("SELECT admin_warnings FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        warnings = row[0] if row else 0
        
        # Если 3+ предупреждения, убираем админа
        if warnings >= 3:
            cursor.execute('UPDATE users SET is_admin = FALSE WHERE user_id = ?', (user_id,))
            # Логируем это действие
            cursor.execute('''
                INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (-1, 'admin_removed', user_id, 'Снятие с должности: 3 предупреждения', time.time()))
        
        conn.commit()
        return warnings
    except Exception as e:
        print(f"⚠️ Ошибка добавления предупреждения: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def get_admin_warnings(user_id):
    """Получить количество предупреждений админа"""
    user = get_user(user_id)
    if not user:
        return 0
    return user[21] if len(user) > 21 else 0

def reset_admin_warnings(user_id):
    """Сбросить предупреждения админа"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET admin_warnings = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def is_user_banned(user_id):
    user = get_user(user_id)
    if not user:
        return False
    
    # проверяем временный бан
    if user[9] and len(user) > 10 and user[10] is not None and user[10] > 0:  # banned and ban_duration > 0
        ban_start = user[11] if len(user) > 11 and user[11] is not None else 0  # ban_start_time
        if time.time() - ban_start >= user[10]:
            # бан истек - разбаниваем
            unban_user(user_id)
            return False
        return True
    
    return user[9] if user else False  # banned

# функция для записи перевода в историю
def log_money_transfer(from_user_id, to_user_id, amount):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO money_transfers (from_user_id, to_user_id, amount)
        VALUES (?, ?, ?)
    ''', (from_user_id, to_user_id, amount))
    conn.commit()
    conn.close()

async def safe_send_photo(update, photo_file, caption, reply_markup=None, parse_mode=None):
    """Безопасная отправка фото с обработкой ошибок"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            if not photo_file or not cached_photo_exists(photo_file):
                return await update.message.reply_text(
                    caption, 
                    reply_markup=reply_markup, 
                    parse_mode=parse_mode
                )
            
            with open(photo_file, 'rb') as photo:
                return await update.message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    read_timeout=20,
                    write_timeout=20
                )
                
        except Exception as e:
            print(f"⚠️ Попытка {attempt + 1} отправки фото не удалась: {e}")
            if attempt == max_retries - 1:  # последняя попытка
                return await update.message.reply_text(
                    caption, 
                    reply_markup=reply_markup, 
                    parse_mode=parse_mode
                )
            await asyncio.sleep(1)  # ждем перед повторной попыткой

# стартовое сообщение с регистрацией
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, main_admin_id: int):
    user_id = update.effective_user.id
    
    # обновляем username при каждом старте
    username = update.effective_user.username
    if username:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
        conn.commit()
        conn.close()
        
        # если это главный админ, логируем обновление
        if user_id == main_admin_id:
            print(f"✅ username главного админа обновлен: {username}")
    
    # обрабатываем параметр реф ссылки
    args = getattr(context, 'args', None)
    if args and len(args) > 0:
        try:
            referrer_id = int(args[0])
            # проверяем что реферер существует
            referrer = get_user(referrer_id)
            if referrer:
                context.user_data['referrer_id'] = referrer_id
                print(f"✅ параметр реф ссылки получен: {referrer_id}")
        except (ValueError, TypeError):
            print(f"⚠️ неверный параметр реф ссылки: {args[0]}")
    
    # проверяем бан
    if is_user_banned(user_id):
        await update.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    user = get_user(user_id)
    
    if user and user[8]:  # если пользователь уже зарегистрирован
        from main_menu import show_main_menu
        await show_main_menu(update, context)
        return
    
    keyboard = [
        [InlineKeyboardButton("зарегистрироваться", callback_data="register")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = """👋 здарова! я тут заметил, что у тебя еще нет человечка в бот гангстер.
    
    для начала регистрации, жми кнопку ниже"""
    
    if update.message:
        if USE_PHOTOS:
            try:
                photo_path = 'images/registration.jpg'
                if cached_photo_exists(photo_path):
                    with open(photo_path, 'rb') as photo:
                        await update.message.reply_photo(
                            photo=photo,
                            caption=message_text,
                            reply_markup=reply_markup
                        )
                else:
                    await update.message.reply_text(message_text, reply_markup=reply_markup)
            except Exception as e:
                await update.message.reply_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        try:
            if USE_PHOTOS:
                photo_path = 'images/registration.jpg'
                if os.path.exists(photo_path):
                    with open(photo_path, 'rb') as photo:
                        await update.callback_query.edit_message_media(
                            media=InputMediaPhoto(
                                photo,
                                caption=message_text
                            ),
                            reply_markup=reply_markup
                        )
                else:
                    await update.callback_query.edit_message_text(
                        message_text,
                        reply_markup=reply_markup
                    )
            else:
                await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=reply_markup
                )
        except Exception:
            await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup
            )

# выбор пола (первый этап после регистрации)
async def choose_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        await update.callback_query.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.callback_query.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    keyboard = [
        [InlineKeyboardButton("мужской", callback_data="gender_male"),
         InlineKeyboardButton("женский", callback_data="gender_female")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "начнем, выбери пол своего персонажа:"
    
    try:
        if USE_PHOTOS:
            photo_path = 'images/gender_choice.jpg'
            fallback_path = 'images/registration.jpg'
            
            if cached_photo_exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            elif cached_photo_exists(fallback_path):
                with open(fallback_path, 'rb') as photo:
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            else:
                await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=reply_markup
                )
        else:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )
    except Exception:
        pass

# выбор цвета персонажа (второй этап)
async def choose_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        await update.callback_query.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.callback_query.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    # сохраняем выбранный пол
    gender = update.callback_query.data.replace("gender_", "")
    context.user_data['gender'] = gender
    
    keyboard = [
        [InlineKeyboardButton("черный", callback_data="color_black"),
         InlineKeyboardButton("белый", callback_data="color_white")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "ок, записал. выбери цвет своего персонажа:"
    
    try:
        if USE_PHOTOS:
            photo_path = 'images/color_choice.jpg'
            fallback_path = 'images/registration.jpg'
            
            if cached_photo_exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            elif cached_photo_exists(fallback_path):
                with open(fallback_path, 'rb') as photo:
                    await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            else:
                await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=reply_markup
                )
        else:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )
    except Exception:
        pass

# выбор имени (третий этап)
async def choose_name(update: Update, context: ContextTypes.DEFAULT_TYPE, color: str):
    user_id = update.effective_user.id
    if is_user_banned(user_id):
        await update.callback_query.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.callback_query.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    context.user_data['color'] = color
    
    keyboard = [
        [InlineKeyboardButton("отмена", callback_data="cancel_registration")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "придумай себе никнейм:"
    
    try:
        if USE_PHOTOS:
            photo_path = 'images/name_choice.jpg'
            fallback_path = 'images/registration.jpg'
            
            if cached_photo_exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    message = await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            elif cached_photo_exists(fallback_path):
                with open(fallback_path, 'rb') as photo:
                    message = await update.callback_query.edit_message_media(
                        media=InputMediaPhoto(
                            photo,
                            caption=message_text
                        ),
                        reply_markup=reply_markup
                    )
            else:
                message = await update.callback_query.edit_message_text(
                    message_text,
                    reply_markup=reply_markup
                )
        else:
            message = await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )
        
        # сохраняем id сообщения с выбором имени для возможного удаления
        if hasattr(update.callback_query, 'message') and update.callback_query.message:
            context.user_data['name_selection_message_id'] = update.callback_query.message.message_id
            context.user_data['name_selection_chat_id'] = update.callback_query.message.chat_id
            
    except Exception as e:
        # если не удалось отредактировать, отправляем новое сообщение
        if USE_PHOTOS:
            photo_path = 'images/name_choice.jpg'
            fallback_path = 'images/registration.jpg'
            
            if cached_photo_exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    message = await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=message_text,
                        reply_markup=reply_markup
                    )
            elif cached_photo_exists(fallback_path):
                with open(fallback_path, 'rb') as photo:
                    message = await update.callback_query.message.reply_photo(
                        photo=photo,
                        caption=message_text,
                        reply_markup=reply_markup
                    )
            else:
                message = await update.callback_query.message.reply_text(
                    message_text,
                    reply_markup=reply_markup
                )
        else:
            message = await update.callback_query.message.reply_text(
                message_text,
                reply_markup=reply_markup
            )
        
        context.user_data['name_selection_message_id'] = message.message_id
        context.user_data['name_selection_chat_id'] = message.chat_id

from utils import safe_delete_message

# обработка ввода имени в регистрации
async def handle_registration_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE, main_admin_id: int):
    user_id = update.message.from_user.id
    if is_user_banned(user_id):
        await update.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    # проверяем, находится ли пользователь в процессе регистрации
    if 'gender' not in context.user_data or 'color' not in context.user_data:
        return  # не обрабатываем, если не в регистрации
    
    name = update.message.text.strip()
    
    # удаляем сообщение пользователя с вводом имени
    try:
        await update.message.delete()
    except:
        pass
    
    if not name:
        # удаляем предыдущее сообщение с выбором имени, если оно есть
        if 'name_selection_message_id' in context.user_data and 'name_selection_chat_id' in context.user_data:
            await safe_delete_message(context, 
                                    context.user_data['name_selection_chat_id'], 
                                    context.user_data['name_selection_message_id'])
        
        keyboard = [[InlineKeyboardButton("отмена", callback_data="cancel_registration")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if USE_PHOTOS:
            message = await update.message.reply_photo(
                photo=open('images/name_choice.jpg', 'rb') if cached_photo_exists('images/name_choice.jpg') else 'images/registration.jpg',
                caption="не забудь ввести имя!\n\nпридумай себе никнейм:",
                reply_markup=reply_markup
            )
        else:
            message = await update.message.reply_text(
                "не забудь ввести имя!\n\nпридумай себе никнейм:",
                reply_markup=reply_markup
            )
        
        # сохраняем id нового сообщения
        context.user_data['name_selection_message_id'] = message.message_id
        context.user_data['name_selection_chat_id'] = message.chat_id
        return
    
    is_valid, error_message = is_nickname_valid(name)
    
    if not is_valid:
        # удаляем предыдущее сообщение с выбором имени, если оно есть
        if 'name_selection_message_id' in context.user_data and 'name_selection_chat_id' in context.user_data:
            await safe_delete_message(context, 
                                    context.user_data['name_selection_chat_id'], 
                                    context.user_data['name_selection_message_id'])
        
        keyboard = [[InlineKeyboardButton("отмена", callback_data="cancel_registration")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if USE_PHOTOS:
            message = await update.message.reply_photo(
                photo=open('images/name_choice.jpg', 'rb') if cached_photo_exists('images/name_choice.jpg') else 'images/registration.jpg',
                caption=f"{error_message}\n\nпридумай другой никнейм:",
                reply_markup=reply_markup
            )
        else:
            message = await update.message.reply_text(
                f"{error_message}\n\nпридумай другой никнейм:",
                reply_markup=reply_markup
            )
        
        # сохраняем id нового сообщения
        context.user_data['name_selection_message_id'] = message.message_id
        context.user_data['name_selection_chat_id'] = message.chat_id
        return
        
    # если имя валидно, сохраняем и переходим к подтверждению
    context.user_data['name'] = name
    
    # удаляем предыдущее сообщение с выбором имени, если оно есть
    if 'name_selection_message_id' in context.user_data and 'name_selection_chat_id' in context.user_data:
        await safe_delete_message(context, 
                                context.user_data['name_selection_chat_id'], 
                                context.user_data['name_selection_message_id'])
    
    keyboard = [[InlineKeyboardButton("я", callback_data="confirm_registration")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # определяем текст в зависимости от пола
    gender_emoji = "👨" if context.user_data['gender'] == 'male' else "👩"
    
    # создаем ссылку на профиль пользователя с жирным шрифтом
    profile_link = f'<a href="tg://user?id={user_id}"><b>{name}</b></a>'
    
    message_text = f"""{profile_link}, поздравляю, ты закончил регистрацию! {gender_emoji}

<b>бот гангстер</b> - это твоя жизнь. тут можно зарабатывать <b>деньги</b>, делать <b>бизнес</b>, покупать <b>дома</b>, <b>тачки</b> и <b>шмотки</b>. чтобы <b>продолжить</b> нажми кнопку <b>"я"</b>."""
    
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# завершение регистрации
async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, main_admin_id: int):
    user_id = update.callback_query.from_user.id
    if is_user_banned(user_id):
        await update.callback_query.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.callback_query.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    user = update.callback_query.from_user
    
    if 'gender' not in context.user_data or 'color' not in context.user_data or 'name' not in context.user_data:
        await start(update, context, main_admin_id)
        return
    
    is_main_admin_user = (user_id == main_admin_id)
    # Создаем полную запись пользователя со всеми полями
    user_data = (
        user_id,
        user.username,
        context.user_data['name'],
        context.user_data['gender'],
        context.user_data['color'],
        0,  # стартовые деньги = 0
        is_main_admin_user,
        is_main_admin_user,
        True,
        False,  # banned
        0,      # ban_duration
        0,      # ban_start_time
        None,   # banned_by
        "",     # ban_reason
        False,  # disable_transfer_confirmation
        False,  # disable_transfer_notifications
        False,  # disable_news_notifications
        False   # disable_system_notifications
    )
    
    save_user(user_data)
    
    # Создаем запись о надетых предметах с дефолтным фоном и скином
    try:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Получаем ID скина на основе выбранного цвета
        color = context.user_data['color']
        if color == "white":
            skin_name = "белый персонаж"
        else:
            skin_name = "черный персонаж"
        
        cursor.execute('SELECT skin_id FROM skins WHERE name = ?', (skin_name,))
        skin_result = cursor.fetchone()
        
        if skin_result:
            skin_id = skin_result[0]
            logger.info(f"✅ найден скин '{skin_name}' с ID {skin_id} для {user_id}")
        else:
            skin_id = 1
            logger.warning(f"⚠️ скин '{skin_name}' не найден, используем дефолтный (ID 1) для {user_id}")
        
        # Дефолтный фон имеет ID 1
        cursor.execute('''
            INSERT OR IGNORE INTO user_equipped (user_id, background_accessory)
            VALUES (?, 1)
        ''', (user_id,))
        
        # Инициализируем скин персонажа (используем INSERT OR IGNORE чтобы не перезаписывать если уже есть)
        cursor.execute('''
            INSERT OR IGNORE INTO user_skin (user_id, skin_id)
            VALUES (?, ?)
        ''', (user_id, skin_id))
        
        conn.commit()
        logger.info(f"✅ регистрация завершена для {user_id}: скин ID {skin_id}, цвет '{color}'")
        conn.close()
    except Exception as e:
        logger.error(f"❌ ошибка при создании user_equipped или user_skin для {user_id}: {e}")
    
    # Обрабатываем реф ссылку если она есть
    referrer_id = context.user_data.get('referrer_id')
    if referrer_id:
        from scam import handle_referral_registration, init_referral_stats
        handle_referral_registration(referrer_id, user_id)
    else:
        # Инициализируем статистику реферала для нового пользователя
        from scam import init_referral_stats
        init_referral_stats(user_id)
    
    # очищаем данные о сообщениях выбора имени
    if 'name_selection_message_id' in context.user_data:
        del context.user_data['name_selection_message_id']
    if 'name_selection_chat_id' in context.user_data:
        del context.user_data['name_selection_chat_id']
    
    # очищаем кэш персонажа чтобы он отрисовался с правильным цветом
    from accessories import clear_character_cache
    clear_character_cache(user_id)
    
    context.user_data.clear()
    
    # сразу открываем главное меню без сообщения о завершении регистрации
    from main_menu import show_main_menu
    
    # создаем искусственный update объект для show_main_menu
    class FakeUpdate:
        def __init__(self, original_update):
            self.effective_user = original_update.effective_user
            self.message = original_update.callback_query.message
            self.callback_query = original_update.callback_query
    
    fake_update = FakeUpdate(update)
    
    try:
        # пытаемся удалить сообщение с кнопкой "я"
        await update.callback_query.message.delete()
    except:
        pass
    
    # открываем главное меню
    await show_main_menu(fake_update, context)

# умный обработчик для всех текстовых сообщений
async def handle_all_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, main_admin_id: int):
    user_id = update.message.from_user.id
    
    # проверяем бан
    if is_user_banned(user_id):
        await update.message.reply_text("❌ вы забанены и не можете использовать бота!")
        return
    
    # проверяем чистку
    if is_cleaning_in_progress(context, user_id):
        await update.message.reply_text("⏳ сейчас ты чистишь говно! дождись окончания или отмени чистку.")
        return
    
    text = update.message.text.strip().lower()
    
    user = get_user(user_id)
    
    # если пользователь в процессе регистрации и есть пол и цвет в контексте - обрабатываем как имя
    if 'gender' in context.user_data and 'color' in context.user_data:
        await handle_registration_name_input(update, context, main_admin_id)
        return
    
    # если пользователь не зарегистрирован - кидаем на регистрацию
    if not user or not user[8]:
        await start(update, context, main_admin_id)
        return
    
    # если сообщение "я" - открываем главное меню (регистр не важен)
    if text.lower() == "я":
        from main_menu import show_main_menu
        await show_main_menu(update, context)
        return
    
    # если сообщение "👕" - открываем гардероб
    if text == "👕":
        from accessories import show_wardrobe_menu
        # создаем фальшивый callback_query для функции
        class FakeCallbackQuery:
            async def edit_message_text(self, *args, **kwargs):
                await update.message.reply_text(*args, **kwargs)
        
        context.user_data['_fake_query'] = FakeCallbackQuery()
        
        # Создаем фальшивый update
        class FakeUpdate:
            def __init__(self, original_update):
                self.effective_user = original_update.effective_user
                self.message = original_update.message
                self.callback_query = FakeCallbackQuery()
        
        fake_query = FakeCallbackQuery()
        fake_query.edit_message_text = lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)
        
        fake_update = FakeUpdate(update)
        fake_update.callback_query.edit_message_text = lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)
        
        await show_wardrobe_menu(fake_update, context)
        return
    
    # если сообщение "инструкция" - показываем инструкцию скама
    if text == "инструкция":
        message_text = """📘 <b>инструкция скама:</b>

1️⃣ <b>как получить рефералов:</b>
нажми кнопку 🔗 <b>моя ссылка</b> в меню скама
скопируй свою реферальную ссылку
поделись ей с друзьями или в чатах
каждый, кто перейдет по твоей ссылке и зарегистрируется - твой реферал

2️⃣ <b>как зарабатывать:</b>
когда твой реферал делает донат - ты получаешь 50% от этой суммы
когда твой реферал работает (чистит говно, доит коров) - ты получаешь 50% от его заработка
это начисляется автоматически, реферал ничего не теряет

3️⃣ <b>как проверить статистику:</b>
в меню скама ты видишь сколько мамонтов ты заскамил
и сколько всего заработал от них

💡 <b>совет:</b>
делись ссылкой везде где можно
чем больше рефералов - тем больше заработок! 💸"""
        
        keyboard = [[KeyboardButton("назад")]]
        reply_mark = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(message_text, reply_markup=reply_mark, parse_mode='HTML')
        return

# функция для обновления username пользователя
def update_user_username(user_id, username):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
    conn.commit()
    conn.close()

# функция для поиска пользователя по username
def get_user_by_username(username):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False, timeout=30)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

# функция для поиска пользователя по имени
def get_user_by_name(name):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False, timeout=30)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE name = ?', (name,))
    user = cursor.fetchone()
    conn.close()
    return user

# универсальная функция для обновления любого поля пользователя
def update_user_field(user_id, field_name, value):
    # Защита от SQL инъекций - белый список разрешенных полей
    allowed_fields = {'name', 'color', 'gender', 'money', 'is_admin', 'is_main_admin', 
                     'registered', 'banned', 'ban_duration', 'ban_start_time', 'banned_by', 
                     'ban_reason', 'disable_transfer_confirmation', 'disable_transfer_notifications',
                     'disable_news_notifications', 'disable_system_notifications', 'is_gangster_plus',
                     'referrer_id', 'admin_currency', 'last_admin_exchange_time', 'admin_exchange_week_start',
                     'admin_exchanged_this_week', 'admin_warnings', 'username'}
    
    if field_name not in allowed_fields:
        raise ValueError(f"Invalid field: {field_name}")
    
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute(f'UPDATE users SET {field_name} = ? WHERE user_id = ?', (value, user_id))
        conn.commit()
    except Exception as e:
        print(f"⚠️ ошибка при обновлении {field_name}: {e}")
        conn.rollback()
    finally:
        conn.close()

# функция для обновления имени пользователя
def update_user_name(user_id, new_name):
    update_user_field(user_id, 'name', new_name)

# функция для обновления цвета пользователя
def update_user_color(user_id, new_color):
    update_user_field(user_id, 'color', new_color)
    
    # Обновляем скин в таблице user_skin на основе цвета
    try:
        conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Получаем ID скина на основе цвета
        if new_color == "white":
            skin_name = "белый персонаж"
        else:
            skin_name = "черный персонаж"
        
        cursor.execute('SELECT skin_id FROM skins WHERE name = ?', (skin_name,))
        skin_result = cursor.fetchone()
        skin_id = skin_result[0] if skin_result else 1
        
        # Используем INSERT OR REPLACE чтобы гарантировать что запись будет создана или обновлена
        cursor.execute('''
            INSERT OR REPLACE INTO user_skin (user_id, skin_id)
            VALUES (?, ?)
        ''', (user_id, skin_id))
        
        conn.commit()
        logger.info(f"✅ скин обновлен для {user_id}: {skin_name} (ID: {skin_id})")
        conn.close()
    except Exception as e:
        logger.error(f"❌ ошибка при обновлении скина для {user_id}: {e}")

# функция для обновления пола пользователя
def update_user_gender(user_id, new_gender):
    update_user_field(user_id, 'gender', new_gender)

# функция для обновления настройки отключения подтверждения переводов
def update_user_disable_transfer_confirmation(user_id, disable):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET disable_transfer_confirmation = ? WHERE user_id = ?', (disable, user_id))
    conn.commit()
    conn.close()

# функция для обновления настройки отключения уведомлений о переводах
def update_user_disable_transfer_notifications(user_id, disable):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET disable_transfer_notifications = ? WHERE user_id = ?', (disable, user_id))
    conn.commit()
    conn.close()

# функция для обновления настройки отключения новостных уведомлений
def update_user_disable_news_notifications(user_id, disable):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET disable_news_notifications = ? WHERE user_id = ?', (disable, user_id))
    conn.commit()
    conn.close()

# функция для обновления настройки отключения системных уведомлений
def update_user_disable_system_notifications(user_id, disable):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET disable_system_notifications = ? WHERE user_id = ?', (disable, user_id))
    conn.commit()
    conn.close()

# функция для обновления настройки отключения уведомлений о мамонтах (рефералах)
def update_user_disable_referral_notifications(user_id, disable):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET disable_referral_notifications = ? WHERE user_id = ?', (disable, user_id))
    conn.commit()
    conn.close()

# функция для проверки, отключены ли уведомления о мамонтах
def is_referral_notifications_disabled(user_id):
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT disable_referral_notifications FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        if res and res[0]:
            return True
    except Exception:
        pass
    finally:
        conn.close()
    return False

def get_all_user_ids():
    """Получить список всех зарегистрированных не забаненных пользователей для рассылки"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT user_id FROM users WHERE banned = FALSE')
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error fetching all user ids: {e}")
        return []
    finally:
        conn.close()

def get_news_subscribed_user_ids():
    """Получить список пользователей для обычной новостной рассылки (не забаненные и с включенными новостными уведомлениями)"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT user_id FROM users WHERE banned = FALSE AND (disable_news_notifications = FALSE OR disable_news_notifications IS NULL)')
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error fetching news subscribed user ids: {e}")
        return []
    finally:
        conn.close()

def get_user_boost_2x_until(user_id: int) -> float:
    """Получает время окончания х2 буста заработка"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT boost_2x_until FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        return res[0] if res and res[0] else 0.0
    except Exception:
        return 0.0
    finally:
        conn.close()

def add_user_2x_boost(user_id: int, duration_seconds: int = 86400):
    """Активирует или продлевает х2 со всего заработка"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT boost_2x_until FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        current_until = res[0] if res and res[0] else 0.0
        now = time.time()
        new_until = max(now, current_until) + duration_seconds
        cursor.execute('UPDATE users SET boost_2x_until = ? WHERE user_id = ?', (new_until, user_id))
        conn.commit()
        logger.info(f"x2 boost activated for user {user_id} until {new_until}")
        return new_until
    except Exception as e:
        logger.error(f"Error adding 2x boost for {user_id}: {e}")
        return 0.0
    finally:
        conn.close()

def get_user_earnings_multiplier(user_id: int) -> float:
    """Вычисляет итоговый множитель дохода пользователя (учитывает Гангстер Плюс x4 и Буст x2)"""
    multiplier = 1.0
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT is_gangster_plus, boost_2x_until, gangster_plus_until FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            is_plus, boost_until, plus_until = row[0], row[1] or 0.0, row[2] or 0.0
            now = time.time()
            
            # Если подписка активна (не истекла или бессрочная)
            if is_plus and (plus_until == 0.0 or plus_until > now):
                multiplier *= 4.0
            
            # Если буст х2 активен
            if boost_until > now:
                multiplier *= 2.0
    except Exception as e:
        logger.error(f"Error calculating earnings multiplier for {user_id}: {e}")
    finally:
        conn.close()
    return multiplier

def give_user_skin(user_id: int, skin_id: int):
    """Выдает пользователю скин во владение"""
    conn = sqlite3.connect('gangster_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR IGNORE INTO user_skins (user_id, skin_id) VALUES (?, ?)', (user_id, skin_id))
        conn.commit()
        logger.info(f"Skin {skin_id} granted to user {user_id}")
    except Exception as e:
        logger.error(f"Error giving skin {skin_id} to user {user_id}: {e}")
    finally:
        conn.close()