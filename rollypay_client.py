import os
import uuid
import hmac
import hashlib
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ROLLYPAY_BASE_URL = os.getenv("ROLLYPAY_BASE_URL", "https://api.rollypay.io")
ROLLYPAY_API_KEY = os.getenv("ROLLYPAY_API_KEY", "")
ROLLYPAY_TERMINAL_ID = os.getenv("ROLLYPAY_TERMINAL_ID", "d53f2ee7-b6ce-433e-93c8-3ae752024517")
ROLLYPAY_SIGNING_SECRET = os.getenv("ROLLYPAY_SIGNING_SECRET", "")


def get_headers():
    """Формирует заголовки с API ключом и одноразовым Nonce"""
    api_key = os.getenv("ROLLYPAY_API_KEY", ROLLYPAY_API_KEY)
    return {
        "X-API-Key": api_key.strip(),
        "X-Nonce": str(uuid.uuid4()),
        "Content-Type": "application/json"
    }


async def create_payment(
    amount: float or str,
    description: str,
    order_id: str,
    user_id: int or str,
    payment_method: str = None,
    currency: str = "RUB",
    metadata: dict = None
) -> dict:
    """
    Создает платеж в RollyPay.
    
    :param amount: сумма (например 100 или "100.00")
    :param description: описание платежа
    :param order_id: уникальный ID заказа на вашей стороне
    :param user_id: ID пользователя в Telegram
    :param payment_method: 'sbp', 'crypto', 'card', 'intl_card' или None (общая форма)
    :param currency: 'RUB' (или 'EUR' для intl_card)
    :param metadata: доп. метаданные
    :return: dict с результатом (ok: True/False, pay_url, payment_id и т.д.)
    """
    api_key = os.getenv("ROLLYPAY_API_KEY", ROLLYPAY_API_KEY).strip()
    terminal_id = os.getenv("ROLLYPAY_TERMINAL_ID", ROLLYPAY_TERMINAL_ID).strip()
    
    if not api_key:
        logger.error("ROLLYPAY_API_KEY is not configured")
        return {"ok": False, "error": "RollyPay API ключ не настроен в .env"}

    formatted_amount = f"{float(amount):.2f}"
    
    payload = {
        "amount": formatted_amount,
        "payment_currency": currency,
        "order_id": str(order_id),
        "terminal_id": terminal_id,
        "description": description[:255],
        "customer_id": str(user_id),
    }
    
    if payment_method:
        payload["payment_method"] = payment_method
        
    if metadata:
        payload["metadata"] = metadata

    url = f"{ROLLYPAY_BASE_URL.rstrip('/')}/api/v1/payments"
    headers = get_headers()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            logger.info(f"Creating RollyPay payment for user {user_id}, order {order_id}, amount {formatted_amount} {currency}")
            response = await client.post(url, headers=headers, json=payload)
            logger.info(f"RollyPay response code: {response.status_code}, body: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "ok": True,
                    "payment_id": data.get("payment_id"),
                    "order_id": data.get("order_id"),
                    "pay_url": data.get("pay_url"),
                    "status": data.get("status", "created"),
                    "amount": data.get("amount", formatted_amount),
                    "currency": data.get("payment_currency", currency)
                }
            else:
                error_text = response.text
                try:
                    err_json = response.json()
                    error_text = err_json.get("error", error_text)
                except Exception:
                    pass
                return {"ok": False, "error": f"Ошибка {response.status_code}: {error_text}"}
    except Exception as e:
        logger.error(f"RollyPay connection error: {e}", exc_info=True)
        return {"ok": False, "error": f"Ошибка соединения: {str(e)}"}


async def get_payment_status(payment_id: str) -> dict:
    """
    Получает информацию и статус платежа из RollyPay по payment_id.
    """
    api_key = os.getenv("ROLLYPAY_API_KEY", ROLLYPAY_API_KEY).strip()
    if not api_key:
        return {"ok": False, "error": "ROLLYPAY_API_KEY is not configured"}

    url = f"{ROLLYPAY_BASE_URL.rstrip('/')}/api/v1/payments/{payment_id}"
    headers = get_headers()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return {
                    "ok": True,
                    "payment_id": data.get("payment_id"),
                    "order_id": data.get("order_id"),
                    "status": data.get("status"),
                    "amount": data.get("amount"),
                    "currency": data.get("payment_currency"),
                    "raw": data
                }
            else:
                return {"ok": False, "error": f"Status {response.status_code}: {response.text}"}
    except Exception as e:
        logger.error(f"Error checking RollyPay status for {payment_id}: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def verify_webhook_signature(raw_body: bytes or str, timestamp: str, signature: str, secret: str = None) -> bool:
    """
    Проверяет HMAC-SHA256 подпись входящего вебхука от RollyPay.
    """
    signing_secret = (secret or os.getenv("ROLLYPAY_SIGNING_SECRET", ROLLYPAY_SIGNING_SECRET)).strip()
    if not signing_secret:
        logger.warning("No ROLLYPAY_SIGNING_SECRET configured for webhook verification")
        return False

    if isinstance(raw_body, str):
        raw_body = raw_body.encode('utf-8')

    message = f"{timestamp}.".encode('utf-8') + raw_body
    expected = hmac.new(signing_secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
