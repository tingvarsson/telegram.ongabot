import unittest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot import eventcreator
from ongabot.eventdata import EventData


class CreateEventSendPollFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_early_when_send_poll_raises(self):
        context = MagicMock()
        context.bot.send_poll = AsyncMock(side_effect=TelegramError("network error"))
        chat = MagicMock()
        chat.active_events = []
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_not_called()


class CreateEventSendStatusFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_still_added_when_send_status_message_raises(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock()
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        chat = MagicMock()
        chat.active_events = []
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock(side_effect=TelegramError("forbidden"))
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_called_once_with(mock_event)


class CreateEventPinFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_added_but_not_pinned_when_pin_raises(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock(side_effect=TelegramError("forbidden"))
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        chat = MagicMock()
        chat.active_events = []
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock()
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_called_once_with(mock_event)
        chat.set_pinned_poll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
