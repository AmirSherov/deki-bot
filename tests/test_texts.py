import unittest

from app import texts


class UploadHintTextTests(unittest.TestCase):
    def test_three_states_get_their_own_text(self):
        listener, _ = texts.upload_hint('listener', None, 'ru')
        no_storage, _ = texts.upload_hint('no_storage', None, 'ru')
        storage, button = texts.upload_hint('storage', 'Моё хранилище', 'ru')
        self.assertIn('станьте артистом', listener)
        self.assertIn('Подключите', no_storage)
        self.assertIn('канал «Моё хранилище»', storage)
        self.assertEqual(button, 'Открыть «Каналы»')
        self.assertEqual(len({listener, no_storage, storage}), 3)

    def test_english_for_english_clients(self):
        text, button = texts.upload_hint('storage', 'Vault', 'en-US')
        self.assertIn('«Vault»', text)
        self.assertEqual(button, 'Open Channels')

    def test_unknown_language_and_state_fall_back(self):
        text, _ = texts.upload_hint('button', None, 'de')
        self.assertEqual(text, texts.UPLOAD_HINTS['ru']['listener'])

    def test_storage_without_title_and_braces_in_title(self):
        text, _ = texts.upload_hint('storage', None, 'ru')
        self.assertIn('ваш канал-хранилище', text)
        text, _ = texts.upload_hint('storage', '{x}', 'ru')
        self.assertIn('«{x}»', text)


if __name__ == '__main__':
    unittest.main()
