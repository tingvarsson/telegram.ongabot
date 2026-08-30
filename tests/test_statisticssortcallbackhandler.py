import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode
from telegram.error import BadRequest

from ongabot.handler.statisticssortcallbackhandler import callback


class StatisticsSortCallbackHandlerTest(unittest.IsolatedAsyncioTestCase):
    def _make(self, data="stats_sort:streak"):
        update = MagicMock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.data = data
        update.effective_chat.id = 123

        context = MagicMock()
        chat = MagicMock()
        context.bot_data.get_chat.return_value = chat
        context.bot.get_chat_member_count = AsyncMock(return_value=42)

        return update, context, chat

    async def test_answers_the_callback_query(self):
        update, context, _chat = self._make()

        with patch(
            "ongabot.handler.statisticssortcallbackhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ):
            await callback(update, context)

        update.callback_query.answer.assert_awaited_once_with()

    async def test_parses_sort_by_from_callback_data_and_renders(self):
        update, context, chat = self._make(data="stats_sort:streak")

        with patch(
            "ongabot.handler.statisticssortcallbackhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ) as render:
            await callback(update, context)

        context.bot_data.get_chat.assert_called_once_with(123)
        context.bot.get_chat_member_count.assert_awaited_once_with(123)
        render.assert_called_once_with(chat, 42, sort_by="streak")

    async def test_edits_message_with_rendered_text_and_keyboard(self):
        update, context, _chat = self._make()

        with patch(
            "ongabot.handler.statisticssortcallbackhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ):
            await callback(update, context)

        update.callback_query.edit_message_text.assert_awaited_once_with(
            "TEXT", parse_mode=ParseMode.MARKDOWN_V2, reply_markup="KEYBOARD"
        )

    async def test_swallows_message_not_modified_bad_request(self):
        update, context, _chat = self._make()
        update.callback_query.edit_message_text.side_effect = BadRequest(
            "Message is not modified: specified new message content and reply markup are exactly the same"
        )

        with patch(
            "ongabot.handler.statisticssortcallbackhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ):
            await callback(update, context)  # should not raise

    async def test_reraises_other_bad_request_errors(self):
        update, context, _chat = self._make()
        update.callback_query.edit_message_text.side_effect = BadRequest("Chat not found")

        with patch(
            "ongabot.handler.statisticssortcallbackhandler.render_statistics_message",
            return_value=("TEXT", "KEYBOARD"),
        ):
            with self.assertRaises(BadRequest):
                await callback(update, context)

    async def test_missing_callback_query_data_is_a_noop(self):
        update, context, _chat = self._make()
        update.callback_query.data = None

        with patch("ongabot.handler.statisticssortcallbackhandler.render_statistics_message") as render:
            await callback(update, context)

        render.assert_not_called()

    async def test_missing_effective_chat_is_a_noop(self):
        update, context, _chat = self._make()
        update.effective_chat = None

        with patch("ongabot.handler.statisticssortcallbackhandler.render_statistics_message") as render:
            await callback(update, context)

        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
