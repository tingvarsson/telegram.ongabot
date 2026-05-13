import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.eventpollanswerhandler import callback
from ongabot.userdata import UserData


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


def _make_context(user_data, event, chat_events=None):
    """Build a minimal context mock for streak-related callback tests."""
    context = MagicMock()
    context.user_data = user_data
    context.bot.send_message = AsyncMock()

    event.update_status_message = AsyncMock()
    context.bot_data.get_event.return_value = event

    chat = MagicMock()
    chat.events = chat_events or {}
    context.bot_data.get_chat.return_value = chat

    return context


class EventPollAnswerStreakTest(unittest.IsolatedAsyncioTestCase):
    def _make_update(self, poll_id, user_id, option_ids=(0,)):
        update = MagicMock()
        update.poll_answer.poll_id = poll_id
        update.poll_answer.option_ids = option_ids
        update.poll_answer.user.id = user_id
        update.poll_answer.user.name = "Alice"
        return update

    def _make_event(self, chat_id=1):
        event = MagicMock()
        event.chat_id = chat_id
        event.user_streaks = {}
        return event

    async def test_streak_stored_on_event_after_vote(self):
        user_data = UserData()
        event = self._make_event()

        prev_event = MagicMock()
        prev_event.event_date = date(2026, 1, 1)
        cur_event = MagicMock()
        cur_event.event_date = date(2026, 1, 8)

        chat_events = {"prev": prev_event, "poll1": cur_event}
        context = _make_context(user_data, event, chat_events)

        # Pre-seed a previous vote so streak should be 2
        user_data.set_poll_answer("prev", (0,))

        update = self._make_update("poll1", user_id=42)
        await callback(update, context)

        self.assertEqual(event.user_streaks[42], 2)

    async def test_streak_not_updated_on_retraction(self):
        user_data = UserData()
        event = self._make_event()
        cur_event = MagicMock()
        cur_event.event_date = date(2026, 1, 8)
        context = _make_context(user_data, event, {"poll1": cur_event})

        update = self._make_update("poll1", user_id=42, option_ids=())
        await callback(update, context)

        self.assertNotIn(42, event.user_streaks)

    async def test_first_event_vote_gives_streak_one(self):
        user_data = UserData()
        event = self._make_event()
        cur_event = MagicMock()
        cur_event.event_date = date(2026, 1, 8)
        context = _make_context(user_data, event, {"poll1": cur_event})

        update = self._make_update("poll1", user_id=7)
        await callback(update, context)

        self.assertEqual(event.user_streaks[7], 1)

    async def test_status_message_updated_after_streak_stored(self):
        """update_status_message is called after user_streaks is populated."""
        user_data = UserData()
        event = self._make_event()
        cur_event = MagicMock()
        cur_event.event_date = date(2026, 1, 8)
        context = _make_context(user_data, event, {"poll1": cur_event})

        streaks_at_call_time = {}

        async def capture_streaks(bot):
            streaks_at_call_time.update(event.user_streaks)

        event.update_status_message = capture_streaks

        update = self._make_update("poll1", user_id=5)
        await callback(update, context)

        self.assertIn(5, streaks_at_call_time)


if __name__ == "__main__":
    unittest.main()
