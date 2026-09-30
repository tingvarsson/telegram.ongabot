import unittest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot import eventcreator
from ongabot.chat import Chat
from ongabot.eventdata import EventData
from ongabot.eventjob import EventJob


class CreateEventSendPollFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_early_when_send_poll_raises(self):
        context = MagicMock()
        context.bot.send_poll = AsyncMock(side_effect=TelegramError("network error"))
        chat = MagicMock()
        chat.get_event_by_date.return_value = None
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        await eventcreator.create_event(context, 123, event_data)

        context.bot.send_poll.assert_called_once()
        chat.add_event.assert_not_called()


class CreateEventSendStatusFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_still_added_when_send_status_message_raises(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock()
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        chat = MagicMock()
        chat.get_event_by_date.return_value = None
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock(side_effect=TelegramError("forbidden"))
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_called_once_with(mock_event, force=False)


class CreateEventPinFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_added_but_not_pinned_when_pin_raises(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock(side_effect=TelegramError("forbidden"))
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        chat = MagicMock()
        chat.get_event_by_date.return_value = None
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock()
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_called_once_with(mock_event, force=False)
        chat.set_pinned_poll.assert_not_called()


class CreateEventHappyPathTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_added_and_pinned_on_success(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock()
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        chat = MagicMock()
        chat.get_event_by_date.return_value = None
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock()
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data)

        chat.add_event.assert_called_once_with(mock_event, force=False)
        poll_message.pin.assert_called_once_with(disable_notification=True)
        chat.set_pinned_poll.assert_called_once()


class CreateEventActiveConflictTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_when_active_event_exists_for_date(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        active_event = MagicMock()
        active_event.completed = False
        chat = MagicMock()
        chat.get_event_by_date.return_value = active_event
        context.bot_data.get_chat.return_value = chat
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)

        await eventcreator.create_event(context, 123, event_data)

        context.bot.send_poll.assert_not_called()
        context.bot.send_message.assert_called_once()
        msg = context.bot.send_message.call_args[0][1]
        self.assertIn("/cancelevent", msg)


class CreateEventCancelledConflictTest(unittest.IsolatedAsyncioTestCase):
    def _make_cancelled_event(self, event_date):
        cancelled = MagicMock()
        cancelled.event_date = event_date
        cancelled.completed = True
        cancelled.poll_id = "old_poll"
        return cancelled

    async def test_rejects_cancelled_event_without_force(self):
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)
        chat = MagicMock()
        chat.get_event_by_date.return_value = self._make_cancelled_event(event_data.event_date)
        context.bot_data.get_chat.return_value = chat

        await eventcreator.create_event(context, 123, event_data)

        context.bot.send_poll.assert_not_called()
        msg = context.bot.send_message.call_args[0][1]
        self.assertIn("force=true", msg)

    async def test_replaces_cancelled_event_with_force(self):
        poll_message = MagicMock()
        poll_message.pin = AsyncMock()
        context = MagicMock()
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        event_data = EventData(date(2026, 6, 3), time(18, 30), 5)
        chat = MagicMock()
        chat.get_event_by_date.return_value = self._make_cancelled_event(event_data.event_date)
        chat.add_event.return_value = True
        context.bot_data.get_chat.return_value = chat

        with patch("ongabot.eventcreator.Event") as MockEvent:
            mock_event = MagicMock()
            mock_event.send_status_message = AsyncMock()
            MockEvent.return_value = mock_event

            await eventcreator.create_event(context, 123, event_data, force=True)

        context.bot.send_poll.assert_called_once()
        chat.add_event.assert_called_once_with(mock_event, force=True)


class CreateEventCallbackTest(unittest.IsolatedAsyncioTestCase):
    """The weekly job's callback: the poll for the chat's coming event day, from its local today."""

    async def test_creates_the_poll_for_the_coming_event_day_and_records_the_run(self):
        sunday = date(2026, 10, 4)
        chat = Chat(123)
        chat.set_event_job(EventJob(123))
        context = MagicMock()
        context.job.chat_id = 123
        context.bot_data.get_chat.return_value = chat

        with patch.object(Chat, "today", return_value=sunday):
            with patch("ongabot.eventcreator.create_event", AsyncMock()) as create:
                await eventcreator.create_event_callback(context)

        self.assertEqual(create.await_args.args[2].event_date, date(2026, 10, 7))
        self.assertEqual(chat.event_job.last_triggered_on, sunday)

    async def test_nothing_without_a_schedule(self):
        context = MagicMock()
        context.job.chat_id = 123
        context.bot_data.get_chat.return_value = Chat(123)

        with patch("ongabot.eventcreator.create_event", AsyncMock()) as create:
            await eventcreator.create_event_callback(context)

        create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
