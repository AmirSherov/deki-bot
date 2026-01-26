import logging
import uuid
import asyncio
from aiogram import Router
from aiogram.types import Message, PreCheckoutQuery, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from app.django_client import DjangoClient


router = Router()
logger = logging.getLogger(__name__)


def _parse_intent_id(payload: str) -> str | None:
    if not payload:
        return None
    if payload.startswith('dp:'):
        payload = payload.split('dp:', 1)[1]
    try:
        uuid.UUID(payload)
        return payload
    except ValueError:
        return None


@router.message(CommandStart())
async def start(message: Message):
    name = message.from_user.first_name or message.from_user.username or "друг"
    text = (
        f"Добро пожаловать в Deki Your Music, {name}!\n\n"
        "Deki - это твоя музыкальная платформа где ты можешь:\n\n"
        "🎧 Слушать треки и открывать новую музыку\n"
        "🎤 Стать исполнителем и загружать свои треки\n"
        "📈 Получать персональные рекомендации\n"
        "📊 Анализировать статистику прослушиваний\n"
        "🌟 Поддерживать любимых артистов\n\n"
        "Нажми кнопку ниже, чтобы открыть приложение!"
    )

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Открыть Deki", web_app=WebAppInfo(url="https://deki.one"))]],
        resize_keyboard=True,
    )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, django: DjangoClient):
    payload = {
        'payload': pre_checkout_query.invoice_payload,
        'total_amount': pre_checkout_query.total_amount,
        'currency': pre_checkout_query.currency,
        'telegram_user_id': pre_checkout_query.from_user.id,
    }

    try:
        result = await django.post('/internal/payments/precheckout/', payload, timeout_seconds=7)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.exception("Precheckout failed: %s", exc)
        try:
            await pre_checkout_query.answer(ok=False, error_message="Payment validation failed")
        except TelegramBadRequest:
            await pre_checkout_query.answer(ok=False, error_message="Payment validation failed")
        return
    data = result.get('data', {})
    ok = False
    error_message = 'Payment validation failed'

    if isinstance(data, dict) and data.get('ok') and data.get('result'):
        result_data = data['result']
        ok = bool(result_data.get('ok'))
        if not ok:
            error_message = result_data.get('error_message') or error_message

    try:
        await pre_checkout_query.answer(ok=ok, error_message=error_message if not ok else None)
    except TelegramBadRequest:
        await pre_checkout_query.answer(ok=False, error_message="Payment validation failed")


@router.message(lambda message: message.successful_payment is not None)
async def successful_payment_handler(message: Message, django: DjangoClient):
    payment = message.successful_payment

    intent_id = _parse_intent_id(payment.invoice_payload or "")
    payload = {
        'payload': payment.invoice_payload,
        'total_amount': payment.total_amount,
        'currency': payment.currency,
        'telegram_user_id': message.from_user.id,
        'telegram_payment_charge_id': payment.telegram_payment_charge_id,
        'provider_payment_charge_id': payment.provider_payment_charge_id,
        'raw_update': {
            'message_id': message.message_id,
            'chat_id': message.chat.id,
            'successful_payment': payment.model_dump(),
        },
    }

    result = await django.post('/internal/payments/success/', payload)
    data = result.get('data', {})
    if isinstance(data, dict) and data.get('ok'):
        result_data = data.get('result', {})
        if isinstance(result_data, dict) and result_data.get('status') == 'applied':
            reply = (
                "🎉 Поздравляем! Подписка Deki Plus активирована.\n\n"
                "Теперь тебе доступны все премиум-возможности.\n"
                "Открывай приложение и наслаждайся музыкой!"
            )
            if intent_id:
                reply += f"\nIntent ID: {intent_id}"
            if payment.telegram_payment_charge_id:
                reply += f"\nCharge ID: {payment.telegram_payment_charge_id}"
            await message.answer(reply)
            return
        if isinstance(result_data, dict) and result_data.get('status') == 'rejected':
            await message.answer(
                "Оплата не подтверждена. Если списание прошло, пожалуйста, напишите в поддержку."
            )
            return

    await message.answer("Payment received. We are processing your subscription.")
