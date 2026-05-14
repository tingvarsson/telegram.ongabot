import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.canceleventcommandhandler import callback


class CancelEventSuccessMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_message_includes_event_date(self):
        target_date = date(2026, 6, 4)
        event = MagicMock()
        event.event_date = target_date
        event.poll_id = "p1"
        event.completed = False

        chat = MagicMock()
        chat.active_events = [event]
        chat.remove_pinned_poll = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 1
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = []
        context.bot_data.get_chat.return_value = chat
        context.bot.send_message = AsyncMock()

        await callback(update, context)

        context.bot.send_message.assert_called_once()
        msg = context.bot.send_message.call_args[0][1]
        self.assertIn(str(target_date), msg)
        self.assertIn("cancelled", msg.lower())


if __name__ == "__main__":
    unittest.main()
