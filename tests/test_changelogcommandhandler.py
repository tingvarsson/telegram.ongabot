import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode
from telegram.error import BadRequest

from ongabot.handler.changelogcommandhandler import callback

ENTRY = "## [1.2.0] - 2026-05-24\n\n### Fixed\n\n- Big fix\n"


class ChangelogCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _make(self, args):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = args
        return update, context

    async def test_default_count_is_one(self):
        update, context = self._make([])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY) as gc:
            await callback(update, context)
        self.assertEqual(gc.call_args.args[1], 1)
        update.message.reply_text.assert_awaited_once()

    async def test_explicit_count_passed_through(self):
        update, context = self._make(["3"])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY) as gc:
            await callback(update, context)
        self.assertEqual(gc.call_args.args[1], 3)

    async def test_entry_is_sent_as_html(self):
        update, context = self._make([])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY):
            await callback(update, context)
        self.assertEqual(update.message.reply_text.await_args.kwargs["parse_mode"], ParseMode.HTML)

    async def test_entry_body_is_collapsed_into_a_blockquote(self):
        update, context = self._make([])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY):
            await callback(update, context)
        self.assertIn("<blockquote", update.message.reply_text.await_args.args[0])

    async def test_link_previews_are_disabled(self):
        """The changelog is full of GitHub links; a preview per message is the noise we remove."""
        update, context = self._make([])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY):
            await callback(update, context)
        self.assertTrue(update.message.reply_text.await_args.kwargs["link_preview_options"].is_disabled)

    async def test_an_entry_too_long_for_one_message_is_sent_in_parts(self):
        """Telegram rejects an over-long message outright, which used to fail the whole reply."""
        update, context = self._make(["3"])
        bullets = "\n".join(f"- Bullet number {n}" for n in range(40))
        entry = "\n".join(f"## [1.{n}.0] - 2026-01-01\n\n### Added\n\n{bullets}\n" for n in range(6))
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=entry):
            await callback(update, context)
        self.assertGreater(update.message.reply_text.await_count, 1)

    async def test_a_rejected_html_message_falls_back_to_plain_text(self):
        """A malformed entity must not leave the user with no reply at all."""
        update, context = self._make([])
        update.message.reply_text = AsyncMock(side_effect=[BadRequest("can't parse entities"), None])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY):
            await callback(update, context)
        self.assertEqual(update.message.reply_text.await_count, 2)
        self.assertIsNone(update.message.reply_text.await_args.kwargs.get("parse_mode"))

    async def test_the_plain_text_fallback_still_carries_the_content(self):
        update, context = self._make([])
        update.message.reply_text = AsyncMock(side_effect=[BadRequest("can't parse entities"), None])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value=ENTRY):
            await callback(update, context)
        self.assertIn("Big fix", update.message.reply_text.await_args.args[0])
        self.assertNotIn("<blockquote", update.message.reply_text.await_args.args[0])

    async def test_invalid_count_replies_usage_and_skips_lookup(self):
        update, context = self._make(["abc"])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog") as gc:
            await callback(update, context)
        gc.assert_not_called()
        update.message.reply_text.assert_awaited_once()

    async def test_zero_count_replies_usage(self):
        update, context = self._make(["0"])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog") as gc:
            await callback(update, context)
        gc.assert_not_called()
        update.message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
