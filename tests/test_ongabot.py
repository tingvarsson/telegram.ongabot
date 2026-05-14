import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from telegram.error import TelegramError

from ongabot import ongabot
from ongabot.ongabot import post_init, setup_bot_metadata


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
        # Both events should be unpinned regardless of the status message failure
        self.assertEqual(chat.remove_pinned_poll.call_count, 2)

    async def test_second_event_processed_when_first_remove_pinned_poll_raises(self):
        event1 = MagicMock()
        event1.completed = False
        event1.event_date = date(2020, 1, 1)
        event1.poll_id = "poll1"
        event1.update_status_message = AsyncMock()

        event2 = MagicMock()
        event2.completed = False
        event2.event_date = date(2020, 1, 2)
        event2.poll_id = "poll2"
        event2.update_status_message = AsyncMock()

        chat = MagicMock()
        chat.events = {"poll1": event1, "poll2": event2}
        chat.remove_pinned_poll = AsyncMock(side_effect=[TelegramError("forbidden"), None])

        context = MagicMock()
        context.bot_data.chats = {"chat1": chat}

        await ongabot.complete_past_events_callback(context)

        event1.mark_complete.assert_called_once()
        event2.mark_complete.assert_called_once()


class CompletePastEventsHappyPathTest(unittest.IsolatedAsyncioTestCase):
    async def test_events_completed_and_unpinned_on_success(self):
        event = MagicMock()
        event.completed = False
        event.event_date = date(2020, 1, 1)
        event.poll_id = "poll1"
        event.update_status_message = AsyncMock()

        chat = MagicMock()
        chat.events = {"poll1": event}
        chat.remove_pinned_poll = AsyncMock()

        context = MagicMock()
        context.bot_data.chats = {"chat1": chat}

        await ongabot.complete_past_events_callback(context)

        event.mark_complete.assert_called_once()
        event.update_status_message.assert_called_once_with(context.bot)
        chat.remove_pinned_poll.assert_called_once_with("poll1")


class PostInitSchedulingFailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_no_exception_propagates_when_schedule_all_event_jobs_raises(self):
        application = MagicMock()
        application.bot_data.schedule_all_event_jobs.side_effect = Exception("corrupt data")
        application.job_queue = MagicMock()

        # Should not raise
        await post_init(application)

        application.job_queue.run_once.assert_called_once()
        application.job_queue.run_daily.assert_called_once()


class SetupBotMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_calls_all_three_api_methods_on_success(self):
        bot = AsyncMock()
        await setup_bot_metadata(bot)
        bot.set_my_commands.assert_called_once()
        bot.set_my_description.assert_called_once()
        bot.set_my_short_description.assert_called_once()

    async def test_continues_when_set_my_commands_raises(self):
        bot = AsyncMock()
        bot.set_my_commands.side_effect = TelegramError("network error")
        await setup_bot_metadata(bot)  # must not raise
        bot.set_my_description.assert_called_once()
        bot.set_my_short_description.assert_called_once()

    async def test_continues_when_set_my_description_raises(self):
        bot = AsyncMock()
        bot.set_my_description.side_effect = TelegramError("network error")
        await setup_bot_metadata(bot)  # must not raise
        bot.set_my_commands.assert_called_once()
        bot.set_my_short_description.assert_called_once()

    async def test_continues_when_set_my_short_description_raises(self):
        bot = AsyncMock()
        bot.set_my_short_description.side_effect = TelegramError("network error")
        await setup_bot_metadata(bot)  # must not raise
        bot.set_my_commands.assert_called_once()
        bot.set_my_description.assert_called_once()


if __name__ == "__main__":
    unittest.main()
