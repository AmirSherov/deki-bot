import logging
import asyncio
import aiohttp
from typing import Callable, Any, Awaitable
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update as TgUpdate
from aiogram.webhook.aiohttp_server import setup_application
from app.config import load_settings
from app.django_client import DjangoClient
from app.handlers import router
from app.webhook_proxy import ProxyRequestHandler

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, django: DjangoClient, settings, allowed_updates: list[str]) -> None:
    if settings.webhook_url and not settings.use_polling:
        webhook_url = f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=True,
            allowed_updates=allowed_updates,
        )
    else:
        await bot.delete_webhook(drop_pending_updates=True)


async def on_shutdown(bot: Bot, django: DjangoClient) -> None:
    await django.close()
    await bot.session.close()


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')


async def _channel_proxy_middleware(
    handler: Callable[[TgUpdate, dict], Awaitable[Any]],
    event: TgUpdate,
    data: dict,
) -> Any:
    if event.channel_post is not None or event.my_chat_member is not None:
        django: DjangoClient | None = data.get('django')
        if django:
            body = event.model_dump_json(exclude_none=True).encode()
            url = f"{django.base_url}/api/v1/studio/webhook/telegram/"
            session = await django.session()
            try:
                async with session.post(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ):
                    pass
            except Exception:
                logger.exception("Failed to proxy update to Django")
    return await handler(event, data)


def main() -> None:
    setup_logging()
    settings = load_settings()

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    django = DjangoClient(settings.django_base_url, settings.bot_internal_secret)
    dp['django'] = django

    dp.update.outer_middleware(_channel_proxy_middleware)

    allowed_updates = dp.resolve_used_update_types()
    if "pre_checkout_query" not in allowed_updates:
        allowed_updates.append("pre_checkout_query")
    if "channel_post" not in allowed_updates:
        allowed_updates.append("channel_post")
    if "my_chat_member" not in allowed_updates:
        allowed_updates.append("my_chat_member")

    async def _startup():
        await on_startup(bot, django, settings, allowed_updates)

    async def _shutdown():
        await on_shutdown(bot, django)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    if settings.use_polling or not settings.webhook_url:
        asyncio.run(dp.start_polling(bot, allowed_updates=allowed_updates))
        return

    app = web.Application()
    ProxyRequestHandler(
        dispatcher=dp,
        bot=bot,
        proxy_url=settings.django_telegram_webhook_url,
        secret_token=settings.webhook_secret or None,
    ).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host=settings.web_host, port=settings.web_port)


if __name__ == '__main__':
    main()
