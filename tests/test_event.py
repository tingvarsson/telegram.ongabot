import unittest
from datetime import date, time
from unittest.mock import MagicMock

from telegram import User

from ongabot.event import Event
from ongabot.eventdata import EventData


def _make_old_state(poll_question: str, poll_id: str = "test_poll_id") -> dict:
    """Minimal pre-EventData state dict for testing Event.__setstate__."""
    poll = MagicMock()
    poll.id = poll_id
    poll.question = poll_question
    return {
        "chat_id": 1,
        "poll": poll,
        "poll_id": poll_id,
        "poll_answers": {},
        "first_answer": None,
        "status_message_id": 0,
        "completed": False,
        "cancelled": False,
        "user_streaks": {},
        # 'data' intentionally absent to trigger migration path
    }


class EventSetStateParsesDateTest(unittest.TestCase):
    def test_recovers_date_from_valid_poll_question(self):
        state = _make_old_state("Event: TOGA (with ONGA)\nWhen: 2026-06-04 18:30")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date(2026, 6, 4))

    def test_falls_back_to_date_min_when_no_when_line(self):
        state = _make_old_state("Some unexpected format without When line")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date.min)

    def test_falls_back_to_date_min_when_date_malformed(self):
        state = _make_old_state("Event: ONGA\nWhen: not-a-date 18:30")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date.min)

    def test_recovers_date_even_when_time_is_malformed(self):
        state = _make_old_state("Event: ONGA\nWhen: 2026-06-03 99:99")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date(2026, 6, 3))

    def test_existing_data_is_not_overwritten(self):
        existing_data = EventData(date(2025, 1, 1), time(20, 0), 3)
        poll = MagicMock()
        poll.id = "p1"
        poll.question = "Event: ONGA\nWhen: 2026-06-03 18:30"
        state = {
            "chat_id": 1,
            "poll": poll,
            "poll_id": "p1",
            "poll_answers": {},
            "first_answer": None,
            "status_message_id": 0,
            "completed": False,
            "cancelled": False,
            "user_streaks": {},
            "data": existing_data,
        }
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertIs(event.data, existing_data)


class EventSetStateDefaultsTest(unittest.TestCase):
    def test_completed_defaults_to_true_when_absent(self):
        poll = MagicMock()
        poll.id = "p1"
        poll.question = "Event: ONGA\nWhen: 2026-06-03 18:30"
        state = {
            "chat_id": 1,
            "poll": poll,
            "poll_id": "p1",
            "poll_answers": {},
            "first_answer": None,
            "status_message_id": 0,
            # 'completed', 'cancelled', 'user_streaks', 'data' all absent
        }
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertTrue(event.completed)
        self.assertFalse(event.cancelled)
        self.assertEqual(event.user_streaks, {})
        self.assertEqual(event.user_played_streaks, {})

    def test_user_played_streaks_defaults_to_empty_when_absent(self):
        # Events pickled before the played streak existed still carry user_streaks.
        state = _make_old_state("Event: ONGA\nWhen: 2026-06-03 18:30")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.user_played_streaks, {})

    def test_existing_user_played_streaks_is_not_overwritten(self):
        state = _make_old_state("Event: ONGA\nWhen: 2026-06-03 18:30")
        state["user_played_streaks"] = {42: 3}
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.user_played_streaks, {42: 3})


def _make_event_with_answer(user: User, option_ids) -> Event:
    """Build an event whose poll has one slot option, answered by a single user."""
    poll = MagicMock()
    poll.id = "p1"
    poll.total_voter_count = 1
    poll.options = [MagicMock(text="18.30", voter_count=1)]
    event = Event(chat_id=1, poll=poll, data=EventData(date(2026, 6, 3), time(18, 30), 1))
    answer = MagicMock()
    answer.option_ids = tuple(option_ids)
    event.poll_answers = {user: answer}
    return event


class EventStatusMessageStarTest(unittest.TestCase):
    """The star next to a voter is their played streak, not their response streak."""

    def setUp(self):
        self.user = User(id=42, first_name="Alice", is_bot=False)

    def test_star_shows_played_streak(self):
        event = _make_event_with_answer(self.user, [0])
        event.user_streaks = {42: 7}
        event.user_played_streaks = {42: 3}

        self.assertIn("★3", event._create_status_message_text(5))

    def test_no_star_when_only_response_streak(self):
        event = _make_event_with_answer(self.user, [0])
        event.user_streaks = {42: 7}
        event.user_played_streaks = {42: 1}

        self.assertNotIn("★", event._create_status_message_text(5))


if __name__ == "__main__":
    unittest.main()
