import unittest
from datetime import date
from unittest.mock import MagicMock

from telegram import User

from ongabot.cs2.session import chat_members, steam_links

THOMAS = User(id=11, first_name="Thomas", is_bot=False)
KALLE = User(id=22, first_name="Kalle", is_bot=False)
LISA = User(id=33, first_name="Lisa", is_bot=False)


def _event(event_date, users):
    event = MagicMock()
    event.event_date = event_date
    event.poll_answers = {user: MagicMock() for user in users}
    return event


def _chat(events):
    chat = MagicMock()
    chat.events = {event.event_date: event for event in events}
    return chat


def _user_data(steam64_id):
    user_data = MagicMock()
    user_data.steam64_id = steam64_id
    return user_data


class ChatMembersTest(unittest.TestCase):
    def test_collects_everyone_who_ever_answered_a_poll(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS, KALLE]), _event(date(2026, 8, 26), [LISA])])

        self.assertEqual(set(chat_members(chat)), {11, 22, 33})

    def test_prefers_the_most_recent_user_object(self):
        """Display names change; the newest poll answer holds the current one."""
        old = User(id=11, first_name="Tom", is_bot=False)
        chat = _chat([_event(date(2026, 8, 26), [old]), _event(date(2026, 9, 2), [THOMAS])])

        self.assertEqual(chat_members(chat)[11].first_name, "Thomas")

    def test_is_empty_for_a_chat_with_no_events(self):
        self.assertEqual(chat_members(_chat([])), {})


class SteamLinksTest(unittest.TestCase):
    def test_returns_only_members_who_linked_a_steam_account(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS, KALLE, LISA])])
        user_data = {11: _user_data("76561198000000011"), 22: _user_data(None)}

        self.assertEqual(steam_links(chat, user_data), {11: "76561198000000011"})

    def test_ignores_a_linked_user_who_is_not_in_this_chat(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS])])
        user_data = {11: _user_data("76561198000000011"), 99: _user_data("76561198000000099")}

        self.assertEqual(steam_links(chat, user_data), {11: "76561198000000011"})

    def test_does_not_create_user_data_entries_for_unlinked_members(self):
        """application.user_data must be read with .get - touching it would persist empty entries."""
        chat = _chat([_event(date(2026, 9, 2), [THOMAS, KALLE])])
        user_data = {}

        self.assertEqual(steam_links(chat, user_data), {})
        self.assertEqual(user_data, {})


if __name__ == "__main__":
    unittest.main()
