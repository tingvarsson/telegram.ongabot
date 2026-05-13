import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from telegram.error import TelegramError

from ongabot import ongabot


class CompletePastEventsCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_event_processed_when_first_update_status_raises(self):
        event1 = MagicMock()
        event1.completed = False
        event1.event_date = date(2020, 1, 1)
        event1.poll_id = "poll1"
        event1.update_status_message = AsyncMock(side_effect=TelegramError("timeout"))

        event2 = MagicMock()
        event2.completed = False
        event2.event_date = date(2020, 1, 2)
        event2.poll_id = "poll2"
        event2.update_status_message = AsyncMock()

        chat = MagicMock()
        chat.events = {"poll1": event1, "poll2": event2}
        chat.remove_pinned_poll = AsyncMock()

        context = MagicMock()
        context.bot_data.chats = {"chat1": chat}

        await ongabot.complete_past_events_callback(context)

        event1.mark_complete.assert_called_once()
        event2.mark_complete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
