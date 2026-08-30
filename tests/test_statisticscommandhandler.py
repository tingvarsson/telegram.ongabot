import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode

from ongabot.handler.statisticscommandhandler import callback


class StatisticsCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _make(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_chat.id = 123

        context = MagicMock()
        chat = MagicMock()
        context.bot_data.get_chat.return_value = chat
        context.bot.get_chat_member_count = AsyncMock(return_value=42)

        return update, context, chat

    async def test_looks_up_chat_and_member_count_for_effective_chat(self):
        update, context, _chat = self._make()

        with (
            patch("ongabot.handler.statisticscommandhandler.compute_statistics", return_value="RESULT") as compute,
            patch("ongabot.handler.statisticscommandhandler.format_statistics", return_value="TEXT"),
        ):
            await callback(update, context)

        context.bot_data.get_chat.assert_called_once_with(123)
        context.bot.get_chat_member_count.assert_awaited_once_with(123)
        compute.assert_called_once_with(_chat, 42)

    async def test_replies_with_formatted_statistics(self):
        update, context, _chat = self._make()

        with (
            patch("ongabot.handler.statisticscommandhandler.compute_statistics", return_value="RESULT") as compute,
            patch("ongabot.handler.statisticscommandhandler.format_statistics", return_value="TEXT") as format_stats,
        ):
            await callback(update, context)

        format_stats.assert_called_once_with(compute.return_value)
        update.message.reply_text.assert_awaited_once_with("TEXT", parse_mode=ParseMode.MARKDOWN_V2)


if __name__ == "__main__":
    unittest.main()
