import unittest
from datetime import date, time
from unittest.mock import MagicMock

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
    def test_recovers_date_and_time_from_valid_poll_question(self):
        state = _make_old_state("Event: TOGA (with ONGA)\nWhen: 2026-06-04 18:30")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date(2026, 6, 4))
        self.assertEqual(event.data.start_time, time(18, 30))

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

    def test_falls_back_to_date_min_when_time_malformed(self):
        state = _make_old_state("Event: ONGA\nWhen: 2026-06-03 99:99")
        event = Event.__new__(Event)
        event.__setstate__(state)

        self.assertEqual(event.data.event_date, date.min)

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


if __name__ == "__main__":
    unittest.main()
