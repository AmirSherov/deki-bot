import asyncio
import logging
import secrets
from typing import Any, Dict, Optional, Set

# Updates Django handles itself (channel uploads, the bot's membership in channels and
# private chats). They are forwarded as they are, with X-Bot-Secret.
PROXIED_UPDATE_TYPES = ("channel_post", "my_chat_member")

import aiohttp
from aiohttp import ClientTimeout, MultipartWriter, web
from aiogram import Bot, Dispatcher
from aiogram.methods import TelegramMethod
from aiogram.types import InputFile


class ProxyRequestHandler:
    def __init__(
        self,
        dispatcher: Dispatcher,
        bot: Bot,
        proxy_url: str,
        handle_in_background: bool = True,
        secret_token: Optional[str] = None,
        bot_secret: str = "",
        **data: Any,
    ) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.proxy_url = proxy_url
        self.bot_secret = bot_secret
        self.handle_in_background = handle_in_background
        self.secret_token = secret_token
        self.data = data
        self._background_feed_update_tasks: Set[asyncio.Task[Any]] = set()
        self._proxy_session: aiohttp.ClientSession | None = None
        self._logger = logging.getLogger(__name__)

    def register(self, app: web.Application, /, path: str, **kwargs: Any) -> None:
        app.on_shutdown.append(self._handle_close)
        app.router.add_route("POST", path, self.handle, **kwargs)

    async def _handle_close(self, app: web.Application) -> None:
        await self.close()

    async def close(self) -> None:
        if self._proxy_session and not self._proxy_session.closed:
            await self._proxy_session.close()
        await self.bot.session.close()

    async def _proxy(self, body: bytes, update_id: Any) -> bool:
        """Forwards the update to Django and waits for its answer. False when Django is
        unreachable or failed (5xx): the update must be delivered again. A 4xx is Django
        rejecting this update for good — retrying would not change it."""
        if self._proxy_session is None or self._proxy_session.closed:
            self._proxy_session = aiohttp.ClientSession()
        timeout = ClientTimeout(total=25)
        try:
            async with self._proxy_session.post(
                self.proxy_url,
                data=body,
                headers={"Content-Type": "application/json", "X-Bot-Secret": self.bot_secret},
                timeout=timeout,
            ) as resp:
                text = await resp.text()
                if resp.status >= 500:
                    self._logger.error("Django failed on update_id=%s: %s %s", update_id, resp.status, text[:300])
                    return False
                if resp.status >= 400:
                    self._logger.warning("Django rejected update_id=%s: %s %s", update_id, resp.status, text[:300])
                else:
                    self._logger.info("Proxied update_id=%s to Django: %s", update_id, resp.status)
                return True
        except Exception:
            self._logger.exception("Proxying update_id=%s to Django failed", update_id)
            return False

    def verify_secret(self, telegram_secret_token: str) -> bool:
        if self.secret_token:
            return secrets.compare_digest(telegram_secret_token, self.secret_token)
        return True

    async def _background_feed_update(self, update: Dict[str, Any]) -> None:
        result = await self.dispatcher.feed_raw_update(bot=self.bot, update=update, **self.data)
        if isinstance(result, TelegramMethod):
            await self.dispatcher.silent_call_request(bot=self.bot, result=result)

    async def _handle_request_background(self, update: Dict[str, Any]) -> web.Response:
        task = asyncio.create_task(self._background_feed_update(update=update))
        self._background_feed_update_tasks.add(task)
        task.add_done_callback(self._background_feed_update_tasks.discard)
        return web.json_response({}, dumps=self.bot.session.json_dumps)

    def _build_response_writer(self, result: Optional[TelegramMethod[Any]]) -> MultipartWriter:
        writer = MultipartWriter(
            "form-data",
            boundary=f"webhookBoundary{secrets.token_urlsafe(16)}",
        )
        if not result:
            return writer

        payload = writer.append(result.__api_method__)
        payload.set_content_disposition("form-data", name="method")

        files: Dict[str, InputFile] = {}
        for key, value in result.model_dump(warnings=False).items():
            value = self.bot.session.prepare_value(value, bot=self.bot, files=files)
            if not value:
                continue
            payload = writer.append(value)
            payload.set_content_disposition("form-data", name=key)

        for key, value in files.items():
            payload = writer.append(value.read(self.bot))
            payload.set_content_disposition(
                "form-data",
                name=key,
                filename=value.filename or key,
            )

        return writer

    async def _handle_request(self, update: Dict[str, Any]) -> web.Response:
        result: Optional[TelegramMethod[Any]] = await self.dispatcher.feed_webhook_update(
            self.bot,
            update,
            **self.data,
        )
        return web.Response(body=self._build_response_writer(result=result))

    async def handle(self, request: web.Request) -> web.Response:
        # Only the Bot API server knows the secret: nothing else gets in, forwarded or not.
        if not self.verify_secret(request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")):
            return web.Response(body="Unauthorized", status=401)

        body = await request.read()
        try:
            update = self.bot.session.json_loads(body.decode("utf-8"))
        except Exception:
            return web.Response(body="Bad Request", status=400)

        if isinstance(update, dict) and any(t in update for t in PROXIED_UPDATE_TYPES):
            # Answered only once Django has it: on an error the Bot API server delivers
            # the update again instead of it being lost (a deploy, a restart).
            if await self._proxy(body, update.get("update_id")):
                return web.Response(status=200, text="OK")
            return web.Response(status=503, text="Django unavailable")

        if self.handle_in_background:
            return await self._handle_request_background(update=update)
        return await self._handle_request(update=update)

    __call__ = handle
