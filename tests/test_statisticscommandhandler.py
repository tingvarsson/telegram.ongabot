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

        with patch(
            "ongabot.handler.statisticscommandhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ) as render:
            await callback(update, context)

        context.bot_data.get_chat.assert_called_once_with(123)
        context.bot.get_chat_member_count.assert_awaited_once_with(123)
        render.assert_called_once_with(_chat, 42)

    async def test_replies_with_rendered_text_and_keyboard(self):
        update, context, _chat = self._make()

        with patch(
            "ongabot.handler.statisticscommandhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ):
            await callback(update, context)

        update.message.reply_text.assert_awaited_once_with(
            "TEXT", parse_mode=ParseMode.MARKDOWN_V2, reply_markup="KEYBOARD"
        )


if __name__ == "__main__":
    unittest.main()
