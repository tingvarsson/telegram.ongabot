"""Migration and storage of the CS2 fields added to UserData and Event.

Only ONGAbot's own derived facts are persisted - never a Leetify scoreboard, per their
Developer Guidelines. See ongabot/cs2/leetify.py.
"""

import unittest
from unittest.mock import MagicMock

from ongabot.event import Event
from ongabot.userdata import UserData


def _legacy_user_state():
    """UserData state dict from before Steam linking existed."""
    return {"poll_answer": {}, "user": None}


def _legacy_event_state():
    """Event state dict from before the CS2 fields existed."""
    poll = MagicMock()
    poll.id = "poll-1"
    poll.question = "Event: ONGA\nWhen: 2026-09-02 18:30"
    return {
        "chat_id": 1,
        "poll": poll,
        "poll_id": "poll-1",
        "poll_answers": {},
        "first_answer": None,
        "status_message_id": 0,
        "completed": False,
        "cancelled": False,
        "user_streaks": {},
        "user_played_streaks": {},
    }


class UserDataSteamLinkTest(unittest.TestCase):
    def test_new_userdata_has_no_steam_link(self):
        self.assertIsNone(UserData().steam64_id)

    def test_persisted_userdata_without_the_field_migrates_to_unlinked(self):
        user_data = UserData.__new__(UserData)
        user_data.__setstate__(_legacy_user_state())

        self.assertIsNone(user_data.steam64_id)

    def test_keeps_an_existing_link_through_unpickling(self):
        user_data = UserData.__new__(UserData)
        user_data.__setstate__(_legacy_user_state() | {"steam64_id": "76561198034202275"})

        self.assertEqual(user_data.steam64_id, "76561198034202275")

    def test_link_and_unlink_round_trip(self):
        user_data = UserData()

        user_data.set_steam64_id("76561198034202275")
        self.assertEqual(user_data.steam64_id, "76561198034202275")

        user_data.set_steam64_id(None)
        self.assertIsNone(user_data.steam64_id)


class EventCs2FieldsTest(unittest.TestCase):
    def test_persisted_event_without_the_fields_migrates_to_unreported(self):
        event = Event.__new__(Event)
        event.__setstate__(_legacy_event_state())

        self.assertEqual(event.cs2_played, {})
        self.assertFalse(event.cs2_reported)

    def test_keeps_existing_cs2_facts_through_unpickling(self):
        event = Event.__new__(Event)
        event.__setstate__(_legacy_event_state() | {"cs2_played": {11: True}, "cs2_reported": True})

        self.assertEqual(event.cs2_played, {11: True})
        self.assertTrue(event.cs2_reported)

    def test_recording_a_session_marks_who_played_and_stops_repeat_reports(self):
        event = Event.__new__(Event)
        event.__setstate__(_legacy_event_state())

        event.record_cs2_session({11, 22})

        self.assertEqual(event.cs2_played, {11: True, 22: True})
        self.assertTrue(event.cs2_reported)


if __name__ == "__main__":
    unittest.main()
