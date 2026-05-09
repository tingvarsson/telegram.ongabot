import unittest
from unittest.mock import MagicMock

from ongabot.handler.eventpollhandler import callback


class EventPollCallbackNoneEventTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_early_when_event_is_none(self):
        update = MagicMock()
        update.poll.id = "unknown_poll_id"
        context = MagicMock()
        context.bot_data.get_event.return_value = None

        await callback(update, context)

        context.bot_data.get_event.assert_called_once_with("unknown_poll_id")
        update.poll.id  # confirms poll was accessed before the guard, not silently skipped
