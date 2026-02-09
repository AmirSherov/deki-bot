import asyncio
import logging
import secrets
from typing import Any, Dict, Optional, Set

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
        **data: Any,
    ) -> None:
        self.dispatcher = dispatcher
        self.bot = bot
        self.proxy_url = proxy_url
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

    async def _proxy(self, body: bytes) -> None:
        if self._proxy_session is None or self._proxy_session.closed:
            self._proxy_session = aiohttp.ClientSession()
        timeout = ClientTimeout(total=10)
        try:
            async with self._proxy_session.post(
                self.proxy_url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            ):
                return
        except Exception:
            self._logger.exception("Proxying telegram update failed")

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
        body = await request.read()
        try:
            update = self.bot.session.json_loads(body.decode("utf-8"))
        except Exception:
            return web.Response(body="Bad Request", status=400)

        if isinstance(update, dict) and ("channel_post" in update or "my_chat_member" in update):
            task = asyncio.create_task(self._proxy(body))
            task.add_done_callback(lambda t: t.exception())
            return web.Response(status=200, text="OK")

        if not self.verify_secret(request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")):
            return web.Response(body="Unauthorized", status=401)

        if self.handle_in_background:
            return await self._handle_request_background(update=update)
        return await self._handle_request(update=update)

    __call__ = handle
