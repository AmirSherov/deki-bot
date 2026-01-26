import aiohttp
from aiohttp import ClientTimeout


class DjangoClient:
    def __init__(self, base_url: str, bot_secret: str):
        self.base_url = base_url.rstrip('/')
        self.bot_secret = bot_secret
        self._session: aiohttp.ClientSession | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def post(self, path: str, payload: dict, timeout_seconds: float = 15) -> dict:
        url = f"{self.base_url}{path}"
        session = await self.session()
        headers = {
            'X-Bot-Secret': self.bot_secret,
            'Content-Type': 'application/json',
        }
        timeout = ClientTimeout(total=timeout_seconds)
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            data = await resp.json(content_type=None)
            return {
                'status': resp.status,
                'data': data,
            }
