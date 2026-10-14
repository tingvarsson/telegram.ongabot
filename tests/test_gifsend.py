"""send_with_gif: a GIF with the text as caption when one is found, the plain text otherwise."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import ReplyParameters
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from ongabot.chat import Chat
from ongabot.gifs import send
from ongabot.gifs.client import Gif
from ongabot.gifs.moods import Mood
from ongabot.gifs.picker import PickedGif

CHAT_ID = 42
PICKED = PickedGif(Gif("abc", "https://media.giphy.com/abc.mp4"), "rage quit")


def _bot():
    bot = MagicMock()
    bot.send_animation = AsyncMock(return_value=MagicMock(message_id=1))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))
    return bot


class SendWithGifTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chat = Chat(CHAT_ID)
        self.bot = _bot()
        pick = patch.object(send, "pick_gif", AsyncMock(return_value=PICKED))
        self.pick_gif = pick.start()
        self.addCleanup(pick.stop)

    async def test_sends_the_gif_with_the_text_as_caption(self):
        reply = ReplyParameters(7, allow_sending_without_reply=True)

        with self.assertLogs("ongabot.gifs.send", level="INFO") as logs:
            message = await send.send_with_gif(
                self.bot,
                self.chat,
                "<b>hi</b>",
                Mood.POKE,
                parse_mode=ParseMode.HTML,
                reply_parameters=reply,
                disable_notification=True,
            )

        self.assertEqual(message.message_id, 1)
        self.pick_gif.assert_awaited_once_with(CHAT_ID, Mood.POKE)
        self.bot.send_animation.assert_awaited_once_with(
            CHAT_ID,
            PICKED.gif.mp4_url,
            caption="<b>hi</b>",
            parse_mode=ParseMode.HTML,
            reply_parameters=reply,
            disable_notification=True,
        )
        self.bot.send_message.assert_not_awaited()
        output = "\n".join(logs.output)
        self.assertIn("gif_id=abc", output)
        self.assertIn("POKE", output)
        self.assertIn("rage quit", output)

    async def test_plain_text_when_gifs_are_off(self):
        self.chat.gifs_enabled = False

        with self.assertLogs("ongabot.gifs.send", level="INFO") as logs:
            message = await send.send_with_gif(self.bot, self.chat, "hi", Mood.BAIL)

        self.assertEqual(message.message_id, 2)
        self.pick_gif.assert_not_awaited()
        self.bot.send_message.assert_awaited_once_with(CHAT_ID, "hi")
        self.assertIn("GIFs are off", "\n".join(logs.output))

    async def test_plain_text_without_a_mood(self):
        await send.send_with_gif(self.bot, self.chat, "hi", None)

        self.pick_gif.assert_not_awaited()
        self.bot.send_animation.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()

    async def test_plain_text_when_no_gif_is_found(self):
        self.pick_gif.return_value = None

        with self.assertLogs("ongabot.gifs.send", level="INFO") as logs:
            await send.send_with_gif(self.bot, self.chat, "hi", Mood.BAIL, disable_notification=True)

        self.bot.send_animation.assert_not_awaited()
        self.bot.send_message.assert_awaited_once_with(CHAT_ID, "hi", disable_notification=True)
        self.assertIn("no GIF found", "\n".join(logs.output))

    async def test_plain_text_when_the_animation_fails(self):
        """Telegram refusing the GIF, or a caption over its 1024-character limit."""
        self.bot.send_animation.side_effect = BadRequest("Message caption is too long")

        with self.assertLogs("ongabot.gifs.send", level="WARNING") as logs:
            message = await send.send_with_gif(self.bot, self.chat, "hi", Mood.BAIL)

        self.assertEqual(message.message_id, 2)
        self.bot.send_message.assert_awaited_once()
        self.assertIn("caption is too long", "\n".join(logs.output))

    async def test_a_failing_text_send_raises(self):
        self.pick_gif.return_value = None
        self.bot.send_message.side_effect = TelegramError("flood")

        with self.assertRaises(TelegramError):
            await send.send_with_gif(self.bot, self.chat, "hi", Mood.BAIL)

    async def test_gif_only_sends_nothing_without_a_gif(self):
        self.pick_gif.return_value = None

        self.assertIsNone(await send.send_with_gif(self.bot, self.chat, "hi", Mood.CS2_WIN, text_fallback=False))

        self.bot.send_message.assert_not_awaited()

    async def test_gif_only_sends_nothing_when_gifs_are_off(self):
        self.chat.gifs_enabled = False

        self.assertIsNone(await send.send_with_gif(self.bot, self.chat, "hi", Mood.CS2_WIN, text_fallback=False))

        self.bot.send_message.assert_not_awaited()
        self.bot.send_animation.assert_not_awaited()

    async def test_gif_only_swallows_a_failed_animation(self):
        self.bot.send_animation.side_effect = TelegramError("boom")

        with self.assertLogs("ongabot.gifs.send", level="WARNING"):
            self.assertIsNone(await send.send_with_gif(self.bot, self.chat, "hi", Mood.CS2_WIN, text_fallback=False))

        self.bot.send_message.assert_not_awaited()
