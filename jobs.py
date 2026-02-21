from registration import get_user_stats
from utils import format_money

# Показать статистику - ОБНОВЛЕННАЯ
async def show_stats(update, context):
    from registration import get_user
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user or not user[8]:
        return

    # Инвалидируем предыдущие сообщения работы
    if 'shit_cleaner_message_id' in context.user_data and 'shit_cleaner_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['shit_cleaner_chat_id'],
                message_id=context.user_data['shit_cleaner_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['shit_cleaner_message_id']
        del context.user_data['shit_cleaner_chat_id']
    if 'milker_message_id' in context.user_data and 'milker_chat_id' in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=context.user_data['milker_chat_id'],
                message_id=context.user_data['milker_message_id'],
                reply_markup=None
            )
        except Exception:
            pass
        del context.user_data['milker_message_id']
        del context.user_data['milker_chat_id']
    
    stats = get_user_stats(user_id)
    nickname = user[2]
    username = user[1]  # username
    user_id = user[0]
    
    # ✅ ОБНОВЛЕНО: Создаем кликабельную ссылку
    if username:
        profile_link = f'<a href="https://t.me/{username}"><b>{nickname}</b></a>'
    else:
        profile_link = f'<a href="tg://user?id={user_id}"><b>{nickname}</b></a>'
    
    shit_cleaned = stats[1]
    milk_collected = stats[2]
    total_earned = stats[3]
    
    message_text = f"""📊 <b>Статистика {profile_link}</b>:

💩 <b>Почищено говна:</b> {shit_cleaned}
🥛 <b>Надоено молока:</b> {milk_collected}
💰 <b>Всего заработано:</b> {format_money(total_earned)}"""
    
    # Клавиатура для статистики
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    keyboard = [[KeyboardButton("назад")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    message = await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

    # Сохраняем id сообщения статистики
    if message:
        context.user_data['stats_message_id'] = message.message_id
        context.user_data['stats_chat_id'] = message.chat_id