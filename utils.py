import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
# функция для форматирования денег
def format_money(amount: int) -> str:
    # защита от None
    if amount is None:
        return "0$"
    
    # преобразуем в целое число если нужно
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return "0$"
    
    if amount < 1000:
        return f"{amount}$"
    elif amount < 1000000:
        return f"{amount:,}$".replace(",", ".")
    else:
        return f"{amount:,}$".replace(",", ".")

# Глобальная ссылка на инстанс бота Telegram для фоновых уведомлений
_global_bot = None

def set_global_bot(bot):
    global _global_bot
    _global_bot = bot

def get_global_bot():
    return _global_bot

# функция для безопасного удаления сообщения
async def safe_delete_message(context, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as e:
        print(f"⚠️ не удалось удалить сообщение: {e}")
        return False

# функция для парсинга суммы денег с поддержкой сокращений и дробных чисел
def parse_amount(amount_str: str, max_amount: int = None) -> int:
    """
    Парсит сумму денег из строки с поддержкой сокращений и дробных чисел:
    1.5кк / 1,5кк -> 1 500 000
    1.5к / 1,5к -> 1 500
    1000 -> 1 000
    1.500.000 -> 1 500 000
    'все' / 'all' -> max_amount (если передан)
    """
    if not amount_str:
        return 0
        
    amount_str = str(amount_str).strip().lower()
    
    if amount_str in ['все', 'всё', 'all']:
        return max_amount if max_amount is not None else 0
        
    multipliers = [
        ('ккккк', 1000000000000000),
        ('kkkkk', 1000000000000000),
        ('кккк', 1000000000000),
        ('kkkk', 1000000000000),
        ('ккк', 1000000000),
        ('kkk', 1000000000),
        ('кк', 1000000),
        ('kk', 1000000),
        ('к', 1000),
        ('k', 1000)
    ]
    
    cleaned_str = amount_str.replace(' ', '')
    
    for suffix, multiplier in multipliers:
        if suffix in cleaned_str:
            number_part = cleaned_str.replace(suffix, '').strip()
            number_part = number_part.replace(',', '.')
            try:
                val = float(number_part)
                return int(val * multiplier)
            except ValueError:
                return 0
                
    raw_str = cleaned_str
    if raw_str.count('.') > 1:
        raw_str = raw_str.replace('.', '')
    if raw_str.count(',') > 1:
        raw_str = raw_str.replace(',', '')
        
    raw_str = raw_str.replace(',', '.')
    
    try:
        return int(float(raw_str))
    except ValueError:
        return 0

# Функция для проверки подписки на канал
async def is_user_subscribed_to_channel(bot, user_id: int, channel_username: str = "@botgangster") -> bool:
    """Проверяет, подписан ли пользователь на Telegram канал"""
    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator', 'restricted']:
            return True
    except Exception:
        pass
    return False

# Функция для отправки напоминания о подписке на канал с вероятностью 25%
async def maybe_send_channel_reminder(update, context):
    """С шансом 25% отправляет сообщение с напоминанием подписаться на канал telegram.me/botgangster (если юзер НЕ подписан)"""
    import random
    if random.random() < 0.25:
        try:
            user_id = update.effective_user.id if update and update.effective_user else None
            if not user_id:
                return
                
            # Проверяем подписку
            subscribed = await is_user_subscribed_to_channel(context.bot, user_id, "@botgangster")
            if subscribed:
                # Если уже подписан — не отправляем
                return
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            reminder_text = (
                "📢 <b>не забудь подписаться на наш канал!</b>\n\n"
                "там выходят свежие новости, бонусы и промокоды:\n"
                "👉 telegram.me/botgangster"
            )
            keyboard = [
                [InlineKeyboardButton("📢 подписаться на канал", url="https://telegram.me/botgangster")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            chat_id = update.effective_chat.id if update and update.effective_chat else None
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=reminder_text,
                    parse_mode='HTML',
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
        except Exception as e:
            print(f"⚠️ не удалось отправить напоминание о канале: {e}")