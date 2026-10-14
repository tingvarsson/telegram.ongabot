"""/gifs: show and switch the GIFs at the bot's big moments."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from ongabot.chat import Chat
from ongabot.handler.gifscommandhandler import ATTRIBUTION, callback
from ongabot.utils.commands import GIFS

CHAT_ID = 42


def _context(chat: Chat, args):
    context = MagicMock()
    context.args = args
    context.bot_data.get_chat.return_value = chat
    return context


def _update():
    update = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.message.reply_text = AsyncMock()
    return update


class GifsCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chat = Chat(CHAT_ID)
        self.update = _update()

    async def _run(self, *args) -> str:
        await callback(self.update, _context(self.chat, list(args)))
        self.update.message.reply_text.assert_awaited_once()
        return self.update.message.reply_text.await_args.args[0]

    async def test_shows_that_gifs_are_on_by_default(self):
        reply = await self._run()
        self.assertIn("GIFs are on in this chat", reply)
        self.assertIn("/gifs off", reply)
        self.assertIn(ATTRIBUTION, reply)

    async def test_off_turns_them_off(self):
        with self.assertLogs("ongabot.handler.gifscommandhandler", level="INFO"):
            reply = await self._run("off")
        self.assertFalse(self.chat.gifs_enabled)
        self.assertIn("plain text", reply)

    async def test_on_turns_them_back_on(self):
        self.chat.gifs_enabled = False
        reply = await self._run("ON")
        self.assertTrue(self.chat.gifs_enabled)
        self.assertIn(ATTRIBUTION, reply)

    async def test_already_on(self):
        self.assertEqual(await self._run("on"), "GIFs are already on in this chat.")

    async def test_already_off(self):
        self.chat.gifs_enabled = False
        self.assertEqual(await self._run("off"), "GIFs are already off in this chat.")

    async def test_shows_off_when_off(self):
        self.chat.gifs_enabled = False
        self.assertIn("GIFs are off in this chat", await self._run())

    async def test_bad_arguments_get_the_usage(self):
        for args in (["maybe"], ["on", "off"]):
            with self.subTest(args=args):
                self.update = _update()
                self.assertEqual(await self._run(*args), GIFS.usage)
                self.assertTrue(self.chat.gifs_enabled)

    async def test_logs_an_error_without_a_message(self):
        update = MagicMock()
        update.message = None
        with self.assertLogs("ongabot.handler.gifscommandhandler", level="ERROR"):
            await callback(update, MagicMock())


class ChatGifsMigrationTest(unittest.TestCase):
    def test_old_pickles_get_gifs_on(self):
        state = dict(Chat(CHAT_ID).__dict__)
        del state["gifs_enabled"]
        restored = Chat.__new__(Chat)
        restored.__setstate__(state)
        self.assertTrue(restored.gifs_enabled)

    def test_a_chat_that_turned_them_off_keeps_them_off(self):
        chat = Chat(CHAT_ID)
        chat.gifs_enabled = False
        restored = Chat.__new__(Chat)
        restored.__setstate__(dict(chat.__dict__))
        self.assertFalse(restored.gifs_enabled)
