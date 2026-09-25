import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ChatType, ParseMode

from ongabot.handler.statisticscommandhandler import callback, send_statistics

MODULE = "ongabot.handler.statisticscommandhandler"


class StatisticsCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
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
            "ongabot.handler.statisticscommandhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ) as render:
            await callback(update, context)

        context.bot_data.get_chat.assert_called_once_with(123)
        render.assert_called_once_with(_chat, in_private_chat=False)

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


class StatisticsPrivateChatTest(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_a_group_pick_when_none_resolved(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        with (
            patch(f"{MODULE}.resolve_group", AsyncMock(return_value=None)) as resolve,
            patch(f"{MODULE}.render_statistics_message") as render,
        ):
            await callback(update, MagicMock())

        self.assertEqual(resolve.await_args.args[2], "statistics")
        render.assert_not_called()

    async def test_table_sent_to_a_private_chat_carries_the_group_on_its_buttons(self):
        message = MagicMock()
        message.chat.type = ChatType.PRIVATE
        message.reply_text = AsyncMock()
        chat = MagicMock()

        with patch(f"{MODULE}.render_statistics_message", return_value=("TEXT", "KEYBOARD")) as render:
            await send_statistics(message, chat)

        render.assert_called_once_with(chat, in_private_chat=True)


if __name__ == "__main__":
    unittest.main()
