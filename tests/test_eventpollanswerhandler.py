import unittest
from unittest.mock import MagicMock

from ongabot.handler.eventpollanswerhandler import callback


class EventPollAnswerCallbackNoneEventTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_early_when_event_is_none(self):
        update = MagicMock()
        update.poll_answer.poll_id = "unknown_poll_id"
        update.poll_answer.user = MagicMock()
        context = MagicMock()
        context.bot_data.get_event.return_value = None

        await callback(update, context)

        context.bot_data.get_event.assert_called_once_with("unknown_poll_id")
        context.bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
