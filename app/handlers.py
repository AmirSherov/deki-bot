import logging
import asyncio
import aiohttp
from aiogram import F, Router
from aiogram.types import (
    ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    PreCheckoutQuery, ReplyKeyboardMarkup, WebAppInfo,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from app import texts
from app.django_client import DjangoClient


router = Router()
logger = logging.getLogger(__name__)


@router.channel_post()
async def channel_post_handler(message: Message) -> None:
    pass  # proxied to Django via middleware in main.py


@router.my_chat_member()
async def my_chat_member_handler(update: ChatMemberUpdated) -> None:
    pass  # proxied to Django via middleware in main.py


async def _report_chat_open(django: DjangoClient, tg_id: int) -> None:
    """/start: the user has a private chat with the bot — Django may push to them
    (identity's bot_can_message). Best effort: the greeting goes out regardless."""
    try:
        result = await django.post(
            '/internal/identity/bot-chat-status/', {'tg_id': tg_id, 'can_message': True}, timeout_seconds=5,
        )
        if result.get('status') != 200:
            logger.warning("bot-chat-status for %s answered %s", tg_id, result.get('status'))
    except Exception:
        logger.exception("bot-chat-status for %s failed", tg_id)


@router.message(CommandStart())
async def start(message: Message, django: DjangoClient):
    await _report_chat_open(django, message.from_user.id)
    name =message.from_user.first_name or message.from_user.username or "друг"
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
            await message.answer(reply)
            return
        if isinstance(result_data, dict) and result_data.get('status') == 'rejected':
            await message.answer(
                "Оплата не подтверждена. Если списание прошло, пожалуйста, напишите в поддержку."
            )
            return

    await message.answer("Payment received. We are processing your subscription.")


# Files people send the bot directly. Uploads come only from the artist's storage channel:
# nothing here is saved, the bot explains where to send it (Django picks the state and
# answers at most once per person per cooldown, so an album of ten files gets one reply).
_UPLOAD_LIKE = F.audio | F.voice | F.video | F.video_note | F.document | F.animation


@router.message(F.chat.type == ChatType.PRIVATE, _UPLOAD_LIKE)
async def private_file_hint(message: Message, django: DjangoClient):
    try:
        result = await django.post(
            '/internal/studio/upload-hint/', {'tg_id': message.from_user.id}, timeout_seconds=5,
        )
    except Exception:
        logger.exception("upload-hint for %s failed", message.from_user.id)
        return
    data = result.get('data')
    hint = data.get('result') if isinstance(data, dict) and data.get('ok') else None
    if result.get('status') != 200 or not isinstance(hint, dict) or not hint.get('reply'):
        return

    text, button_text = texts.upload_hint(
        hint.get('state'), hint.get('channel_title'), message.from_user.language_code,
    )
    markup = None
    if hint.get('button_url'):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=hint['button_url'])]],
        )
    await message.answer(text, reply_markup=markup)


# @router.message(Command("refund"))
# async def refund_handler(message: Message):
#     if not message.text:
#         await message.answer("Usage: /refund <charge_id>")
#         return

#     parts = message.text.strip().split(maxsplit=1)
#     if len(parts) < 2 or not parts[1].strip():
#         await message.answer("Usage: /refund <charge_id>")
#         return

#     charge_id = parts[1].strip()
#     bot = message.bot
#     token = getattr(bot, "token", None)
#     if not token:
#         await message.answer("Refund failed. Bot token not found.")
#         return

#     url = f"https://api.telegram.org/bot{token}/refundStarPayment"
#     data = {
#         'user_id': message.from_user.id,
#         'telegram_payment_charge_id': charge_id,
#     }

#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.post(url, data=data, timeout=10) as resp:
#                 result = await resp.json(content_type=None)
#     except Exception as exc:
#         logger.exception("Refund request failed: %s", exc)
#         await message.answer("Refund failed. Please try again later.")
#         return

#     if isinstance(result, dict) and result.get('ok'):
#         await message.answer("Refund successful. Stars were returned.")
#         return

#     description = None
#     if isinstance(result, dict):
#         description = result.get('description')
#     await message.answer(
#         f"Refund failed. {description}" if description else "Refund failed. Please check the charge id."
#     )
