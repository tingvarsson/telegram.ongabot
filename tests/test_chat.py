import unittest
from datetime import date
from unittest.mock import MagicMock

from ongabot.chat import Chat


def _make_event(poll_id: str, event_date: date, completed: bool = False, cancelled: bool = False):
    event = MagicMock()
    event.poll_id = poll_id
    event.event_date = event_date
    event.completed = completed
    event.cancelled = cancelled
    return event


class ChatAddEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_add_new_event_succeeds(self):
        event = _make_event("p1", date(2026, 6, 4))
        result = self.chat.add_event(event)
        self.assertTrue(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], event)
        self.assertEqual(self.chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_add_rejects_active_slot_returns_false(self):
        active = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(active)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event)
        self.assertFalse(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], active)

    def test_add_cancelled_slot_without_force_returns_none(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        self.chat.add_event(cancelled)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event, force=False)
        self.assertIsNone(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], cancelled)

    def test_add_cancelled_slot_with_force_replaces_old(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        self.chat.add_event(cancelled)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event, force=True)
        self.assertTrue(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], new_event)
        self.assertNotIn("p1", self.chat._poll_id_index)
        self.assertEqual(self.chat._poll_id_index["p2"], date(2026, 6, 4))


class ChatRemoveEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_remove_event_clears_both_structures(self):
        event = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(event)
        self.chat.remove_event("p1")
        self.assertNotIn(date(2026, 6, 4), self.chat.events)
        self.assertNotIn("p1", self.chat._poll_id_index)

    def test_remove_unknown_poll_id_does_not_raise(self):
        self.chat.remove_event("nonexistent")


class ChatGetEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)
        self.event = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(self.event)

    def test_get_event_by_poll_id_returns_event(self):
        self.assertIs(self.chat.get_event_by_poll_id("p1"), self.event)

    def test_get_event_by_poll_id_returns_none_for_unknown(self):
        self.assertIsNone(self.chat.get_event_by_poll_id("unknown"))

    def test_get_event_by_date_returns_event(self):
        self.assertIs(self.chat.get_event_by_date(date(2026, 6, 4)), self.event)

    def test_get_event_by_date_returns_none_for_unknown(self):
        self.assertIsNone(self.chat.get_event_by_date(date(2026, 1, 1)))


class ChatActiveEventsTest(unittest.TestCase):
    def test_active_events_excludes_completed(self):
        chat = Chat(chat_id=1)
        active = _make_event("p1", date(2026, 6, 4), completed=False)
        completed = _make_event("p2", date(2026, 6, 11), completed=True)
        chat.add_event(active)
        chat.add_event(completed)
        self.assertEqual(chat.active_events, [active])


class ChatSetStateMigrationTest(unittest.TestCase):
    def test_migrates_str_keyed_events_to_date_keyed(self):
        event = _make_event("p1", date(2026, 6, 4))
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertIs(chat.events[date(2026, 6, 4)], event)
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_migrates_collision_keeps_active_over_cancelled(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        active = _make_event("p2", date(2026, 6, 4), completed=False)
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": cancelled, "p2": active},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIs(chat.events[date(2026, 6, 4)], active)
        self.assertNotIn("p1", chat._poll_id_index)
        self.assertIn("p2", chat._poll_id_index)

    def test_rebuilds_poll_id_index_when_missing(self):
        event = _make_event("p1", date(2026, 6, 4))
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date(2026, 6, 4): event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))


if __name__ == "__main__":
    unittest.main()
