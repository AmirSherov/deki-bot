"""The bot's copy by the user's Telegram language: Russian by default, English for "en*"."""

DEFAULT_LANGUAGE = 'ru'
HINT_STATES = ('listener', 'no_storage', 'storage')

# A file sent to the bot in a private chat is not an upload (nothing is saved): Django
# (/internal/studio/upload-hint/) says the person's state, the text explains what to do.
UPLOAD_HINTS = {
    'ru': {
        'listener': (
            'Этот файл не сохранён: треки и клипы в Deki загружаются не в чат с ботом, '
            'а через ваш приватный канал-хранилище.\n\n'
            'Сначала станьте артистом в приложении, затем подключите хранилище на экране «Каналы».'
        ),
        'no_storage': (
            'Этот файл не сохранён: треки и клипы загружаются не в чат с ботом, '
            'а через ваш приватный канал-хранилище.\n\n'
            'Подключите его: создайте приватный канал, добавьте туда бота администратором '
            'и назначьте канал хранилищем на экране «Каналы».'
        ),
        'storage': (
            'Этот файл не сохранён: треки и клипы загружаются не в чат с ботом, '
            'а через ваш канал-хранилище.\n\n'
            'Отправьте файл в {channel} — Deki примет его автоматически.'
        ),
        'button': 'Открыть «Каналы»',
        'channel': 'канал «{title}»',
        'channel_unnamed': 'ваш канал-хранилище',
    },
    'en': {
        'listener': (
            "This file wasn't saved: tracks and clips are uploaded to Deki through your private "
            "storage channel, not this chat.\n\n"
            "Become an artist in the app first, then connect a storage channel on the Channels screen."
        ),
        'no_storage': (
            "This file wasn't saved: tracks and clips are uploaded through your private storage "
            "channel, not this chat.\n\n"
            "Connect one: create a private channel, add the bot as an admin and make it your "
            "storage on the Channels screen."
        ),
        'storage': (
            "This file wasn't saved: tracks and clips are uploaded through your storage channel, "
            "not this chat.\n\n"
            "Send the file to {channel} and Deki will pick it up automatically."
        ),
        'button': 'Open Channels',
        'channel': '«{title}»',
        'channel_unnamed': 'your storage channel',
    },
}


def language(language_code: str | None) -> str:
    return 'en' if (language_code or '').lower().startswith('en') else DEFAULT_LANGUAGE


def upload_hint(state: str | None, channel_title: str | None, language_code: str | None) -> tuple[str, str]:
    """(text, button text) for a file sent to the bot; an unknown state reads as a listener's."""
    copy = UPLOAD_HINTS[language(language_code)]
    text = copy[state] if state in HINT_STATES else copy['listener']
    channel = copy['channel'].format(title=channel_title) if channel_title else copy['channel_unnamed']
    return text.format(channel=channel), copy['button']
