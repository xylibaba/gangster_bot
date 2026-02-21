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

# функция для безопасного удаления сообщения
async def safe_delete_message(context, chat_id, message_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception as e:
        print(f"⚠️ не удалось удалить сообщение: {e}")
        return False