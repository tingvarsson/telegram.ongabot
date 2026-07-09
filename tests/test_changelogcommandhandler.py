import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.handler.changelogcommandhandler import callback


class ChangelogCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _make(self, args):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = args
        return update, context

    async def test_default_count_is_one(self):
        update, context = self._make([])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value="ENTRY") as gc:
            await callback(update, context)
        self.assertEqual(gc.call_args.args[1], 1)
        update.message.reply_text.assert_awaited_once_with("ENTRY")

    async def test_explicit_count_passed_through(self):
        update, context = self._make(["3"])
        with patch("ongabot.handler.changelogcommandhandler.get_changelog", return_value="E") as gc:
            await callback(update, context)
        self.assertEqual(gc.call_args.args[1], 3)

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
