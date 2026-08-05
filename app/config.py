import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    bot_token: str
    webhook_url: str
    webhook_path: str
    webhook_secret: str
    web_host: str
    web_port: int
    django_base_url: str
    django_telegram_webhook_url: str
    bot_internal_secret: str
    use_polling: bool
    telegram_api_base_url: str
    telegram_api_is_local: bool


def _get_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() in {'1', 'true', 'yes', 'y', 'on'}


def load_settings() -> Settings:
    bot_token = os.getenv('BOT_TOKEN', '').strip()
    webhook_url = os.getenv('WEBHOOK_URL', '').strip()
    webhook_path = os.getenv('WEBHOOK_PATH', '/webhook')
    webhook_secret = os.getenv('WEBHOOK_SECRET', '').strip()
    web_host = os.getenv('WEBAPP_HOST', '0.0.0.0')
    web_port = int(os.getenv('WEBAPP_PORT', '8080'))
    django_base_url = os.getenv('DJANGO_INTERNAL_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
    django_telegram_webhook_url = os.getenv(
        'DJANGO_TELEGRAM_WEBHOOK_URL',
        f'{django_base_url}/api/v1/studio/webhook/telegram/',
    ).strip()
    bot_internal_secret = os.getenv('BOT_INTERNAL_SECRET', '').strip()
    use_polling = _get_bool(os.getenv('USE_POLLING'), default=False)
    telegram_api_base_url = os.getenv('TELEGRAM_API_BASE_URL', 'https://api.telegram.org').strip().rstrip('/')
    telegram_api_is_local = _get_bool(os.getenv('TELEGRAM_API_IS_LOCAL'), default=False)

    if not bot_token:
        raise RuntimeError('BOT_TOKEN is required')
    if not bot_internal_secret:
        raise RuntimeError('BOT_INTERNAL_SECRET is required')

    return Settings(
        bot_token=bot_token,
        webhook_url=webhook_url,
        webhook_path=webhook_path,
        webhook_secret=webhook_secret,
        web_host=web_host,
        web_port=web_port,
        django_base_url=django_base_url,
        django_telegram_webhook_url=django_telegram_webhook_url,
        bot_internal_secret=bot_internal_secret,
        use_polling=use_polling,
        telegram_api_base_url=telegram_api_base_url,
        telegram_api_is_local=telegram_api_is_local,
    )
