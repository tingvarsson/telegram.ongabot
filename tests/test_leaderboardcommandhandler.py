import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode

from ongabot.handler.leaderboardcommandhandler import callback


class LeaderboardCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _make(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_chat.id = 123

        context = MagicMock()
        chat = MagicMock()
        context.bot_data.get_chat.return_value = chat

        return update, context, chat

    async def test_looks_up_chat_for_effective_chat(self):
        update, context, _chat = self._make()

        with patch(
            "ongabot.handler.leaderboardcommandhandler.render_leaderboard_message",
            return_value="TEXT",
        ) as render:
            await callback(update, context)

        context.bot_data.get_chat.assert_called_once_with(123)
        render.assert_called_once_with(_chat)

    async def test_replies_with_rendered_text(self):
        update, context, _chat = self._make()

        with patch(
            "ongabot.handler.leaderboardcommandhandler.render_leaderboard_message",
            return_value="TEXT",
        ):
            await callback(update, context)

        update.message.reply_text.assert_awaited_once_with("TEXT", parse_mode=ParseMode.MARKDOWN_V2)


if __name__ == "__main__":
    unittest.main()
