import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

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
        chat.events = {date(2020, 1, 1): event1, date(2020, 1, 2): event2}
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
        chat.events = {date(2020, 1, 1): event1, date(2020, 1, 2): event2}
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
        chat.events = {date(2020, 1, 1): event}
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
        application.bot = AsyncMock()
        application.bot_data.schedule_all_event_jobs.side_effect = Exception("corrupt data")
        application.job_queue = MagicMock()

        # Should not raise
        await post_init(application)

        application.job_queue.run_once.assert_called_once()
        application.job_queue.run_daily.assert_called_once()


class PostInitMetadataWiringTest(unittest.IsolatedAsyncioTestCase):
    async def test_post_init_registers_bot_metadata(self):
        application = MagicMock()
        application.bot_data.schedule_all_event_jobs.return_value = None
        application.job_queue = MagicMock()
        application.bot = AsyncMock()

        await post_init(application)

        application.bot.set_my_commands.assert_called_once()
        application.bot.set_my_description.assert_called_once()
        application.bot.set_my_short_description.assert_called_once()

    async def test_post_init_registers_bot_metadata_when_job_queue_unavailable(self):
        application = MagicMock()
        application.bot_data.schedule_all_event_jobs.return_value = None
        application.job_queue = None
        application.bot = AsyncMock()

        await post_init(application)

        application.bot.set_my_commands.assert_called_once()
        application.bot.set_my_description.assert_called_once()
        application.bot.set_my_short_description.assert_called_once()


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


class AnnounceNewVersionTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_message_to_all_authorized_chats(self):
        bot = AsyncMock()
        bot_data = MagicMock()
        bot_data.authorized_chats = {101, 202}

        await ongabot._announce_new_version(bot, bot_data, "1.1.0", "1.2.0")

        self.assertEqual(bot.send_message.call_count, 2)
        sent_chat_ids = {call.kwargs["chat_id"] for call in bot.send_message.call_args_list}
        self.assertEqual(sent_chat_ids, {101, 202})

    async def test_continues_when_one_chat_raises_telegram_error(self):
        from telegram.error import TelegramError

        bot = AsyncMock()
        bot.send_message.side_effect = [TelegramError("forbidden"), None]
        bot_data = MagicMock()
        bot_data.authorized_chats = {101, 202}

        await ongabot._announce_new_version(bot, bot_data, "1.1.0", "1.2.0")

        self.assertEqual(bot.send_message.call_count, 2)

    async def test_message_contains_new_version(self):
        bot = AsyncMock()
        bot_data = MagicMock()
        bot_data.authorized_chats = {101}

        await ongabot._announce_new_version(bot, bot_data, "1.1.0", "1.2.0")

        text = bot.send_message.call_args.kwargs["text"]
        self.assertIn("1.2.0", text)

    async def test_no_messages_sent_when_no_authorized_chats(self):
        bot = AsyncMock()
        bot_data = MagicMock()
        bot_data.authorized_chats = set()

        await ongabot._announce_new_version(bot, bot_data, "1.1.0", "1.2.0")

        bot.send_message.assert_not_called()


class PostInitVersionTrackingTest(unittest.IsolatedAsyncioTestCase):
    def _make_application(self, stored_version):
        application = MagicMock()
        application.bot = AsyncMock()
        application.bot_data.last_known_version = stored_version
        application.bot_data.authorized_chats = {101}
        application.bot_data.schedule_all_event_jobs.return_value = None
        application.job_queue = MagicMock()
        return application

    async def test_announces_when_version_changed(self):
        application = self._make_application(stored_version="1.1.0")
        with patch.object(ongabot, "CURRENT_VERSION", "1.2.0"):
            await post_init(application)
        application.bot.send_message.assert_called_once()

    async def test_no_announcement_when_version_unchanged(self):
        application = self._make_application(stored_version="1.2.0")
        with patch.object(ongabot, "CURRENT_VERSION", "1.2.0"):
            await post_init(application)
        application.bot.send_message.assert_not_called()

    async def test_no_announcement_on_first_run_stores_version(self):
        application = self._make_application(stored_version=None)
        with patch.object(ongabot, "CURRENT_VERSION", "1.2.0"):
            await post_init(application)
        application.bot.send_message.assert_not_called()
        self.assertEqual(application.bot_data.last_known_version, "1.2.0")

    async def test_updates_stored_version_after_announcement(self):
        application = self._make_application(stored_version="1.1.0")
        with patch.object(ongabot, "CURRENT_VERSION", "1.2.0"):
            await post_init(application)
        self.assertEqual(application.bot_data.last_known_version, "1.2.0")


if __name__ == "__main__":
    unittest.main()
