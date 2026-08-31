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


def _make_event_mock(poll_id: str, event_date: date, num_slots: int = 5):
    """Build an event mock with poll_id, event_date and num_slots set explicitly.

    num_slots must be a real int: the played streak compares option ids against it.
    """
    e = MagicMock()
    e.poll_id = poll_id
    e.event_date = event_date
    e.cancelled = False
    e.num_slots = num_slots
    return e


def _make_context(user_data, event, chat_events=None):
    """Build a minimal context mock for streak-related callback tests.

    chat_events: Dict[date, event_mock] — matches the new date-keyed structure.
    """
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
        event.user_played_streaks = {}
        return event

    async def test_streak_stored_on_event_after_vote(self):
        user_data = UserData()
        event = self._make_event()

        prev_event = _make_event_mock("prev", date(2026, 1, 1))
        cur_event = _make_event_mock("poll1", date(2026, 1, 8))

        chat_events = {date(2026, 1, 1): prev_event, date(2026, 1, 8): cur_event}
        context = _make_context(user_data, event, chat_events)

        # Pre-seed a previous vote so streak should be 2
        user_data.set_poll_answer("prev", (0,))

        update = self._make_update("poll1", user_id=42)
        await callback(update, context)

        self.assertEqual(event.user_streaks[42], 2)

    async def test_streak_not_updated_on_retraction(self):
        user_data = UserData()
        event = self._make_event()
        cur_event = _make_event_mock("poll1", date(2026, 1, 8))
        context = _make_context(user_data, event, {date(2026, 1, 8): cur_event})

        update = self._make_update("poll1", user_id=42, option_ids=())
        await callback(update, context)

        self.assertNotIn(42, event.user_streaks)

    async def test_first_event_vote_gives_streak_one(self):
        user_data = UserData()
        event = self._make_event()
        cur_event = _make_event_mock("poll1", date(2026, 1, 8))
        context = _make_context(user_data, event, {date(2026, 1, 8): cur_event})

        update = self._make_update("poll1", user_id=7)
        await callback(update, context)

        self.assertEqual(event.user_streaks[7], 1)

    async def test_status_message_updated_after_streak_stored(self):
        """update_status_message is called after user_streaks is populated."""
        user_data = UserData()
        event = self._make_event()
        cur_event = _make_event_mock("poll1", date(2026, 1, 8))
        context = _make_context(user_data, event, {date(2026, 1, 8): cur_event})

        streaks_at_call_time = {}

        async def capture_streaks(bot):
            streaks_at_call_time.update(event.user_streaks)

        event.update_status_message = capture_streaks

        update = self._make_update("poll1", user_id=5)
        await callback(update, context)

        self.assertIn(5, streaks_at_call_time)

    async def test_streak_unaffected_by_cancelled_event_in_chat(self):
        # User voted in p_prev and p_cur; p_cancelled sits between them but is cancelled.
        # Cancelled events are excluded from poll_id_to_date, so streak should be 2, not 0.
        user_data = UserData()
        user_data.set_poll_answer("p_prev", (0,))

        event = self._make_event()

        prev_event = _make_event_mock("p_prev", date(2026, 1, 1))
        prev_event.cancelled = False

        cancelled_event = _make_event_mock("p_cancelled", date(2026, 1, 8))
        cancelled_event.cancelled = True

        cur_event = _make_event_mock("poll1", date(2026, 1, 15))
        cur_event.cancelled = False

        chat_events = {
            date(2026, 1, 1): prev_event,
            date(2026, 1, 8): cancelled_event,
            date(2026, 1, 15): cur_event,
        }
        context = _make_context(user_data, event, chat_events)

        update = self._make_update("poll1", user_id=42)
        await callback(update, context)

        self.assertEqual(event.user_streaks[42], 2)


class EventPollAnswerPlayedStreakTest(unittest.IsolatedAsyncioTestCase):
    """The played streak is stored alongside the response streak, counting slot picks only."""

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
        event.user_played_streaks = {}
        return event

    async def test_played_streak_stored_on_event_after_slot_vote(self):
        user_data = UserData()
        user_data.set_poll_answer("prev", (0,))
        event = self._make_event()

        chat_events = {
            date(2026, 1, 1): _make_event_mock("prev", date(2026, 1, 1)),
            date(2026, 1, 8): _make_event_mock("poll1", date(2026, 1, 8)),
        }
        context = _make_context(user_data, event, chat_events)

        await callback(self._make_update("poll1", user_id=42), context)

        self.assertEqual(event.user_played_streaks[42], 2)

    async def test_no_op_vote_gives_played_streak_zero_but_keeps_response_streak(self):
        user_data = UserData()
        user_data.set_poll_answer("prev", (0,))
        event = self._make_event()

        chat_events = {
            date(2026, 1, 1): _make_event_mock("prev", date(2026, 1, 1)),
            date(2026, 1, 8): _make_event_mock("poll1", date(2026, 1, 8)),
        }
        context = _make_context(user_data, event, chat_events)

        # 5 slots means option id 5 is No-op: a response, but not a slot pick
        await callback(self._make_update("poll1", user_id=42, option_ids=(5,)), context)

        self.assertEqual(event.user_played_streaks[42], 0)
        self.assertEqual(event.user_streaks[42], 2)

    async def test_played_streak_not_updated_on_retraction(self):
        user_data = UserData()
        event = self._make_event()
        context = _make_context(user_data, event, {date(2026, 1, 8): _make_event_mock("poll1", date(2026, 1, 8))})

        await callback(self._make_update("poll1", user_id=42, option_ids=()), context)

        self.assertNotIn(42, event.user_played_streaks)

    async def test_played_streak_respects_per_event_num_slots(self):
        # prev had 3 slots, so the user's option 3 there was No-op, breaking the played streak.
        user_data = UserData()
        user_data.set_poll_answer("prev", (3,))
        event = self._make_event()

        chat_events = {
            date(2026, 1, 1): _make_event_mock("prev", date(2026, 1, 1), num_slots=3),
            date(2026, 1, 8): _make_event_mock("poll1", date(2026, 1, 8), num_slots=5),
        }
        context = _make_context(user_data, event, chat_events)

        await callback(self._make_update("poll1", user_id=42, option_ids=(3,)), context)

        self.assertEqual(event.user_played_streaks[42], 1)
        self.assertEqual(event.user_streaks[42], 2)

    async def test_status_message_updated_after_played_streak_stored(self):
        user_data = UserData()
        event = self._make_event()
        context = _make_context(user_data, event, {date(2026, 1, 8): _make_event_mock("poll1", date(2026, 1, 8))})

        played_at_call_time = {}

        async def capture_played_streaks(bot):
            played_at_call_time.update(event.user_played_streaks)

        event.update_status_message = capture_played_streaks

        await callback(self._make_update("poll1", user_id=5), context)

        self.assertIn(5, played_at_call_time)


if __name__ == "__main__":
    unittest.main()
