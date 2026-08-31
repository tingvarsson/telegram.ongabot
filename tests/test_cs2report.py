import unittest
from datetime import date
from unittest.mock import MagicMock

from telegram import User

from ongabot.cs2.leetify import MatchDetail, MatchSummary, PlayerStats
from ongabot.cs2.report import event_results, latest_reportable_event

THOMAS = User(id=11, first_name="Thomas", is_bot=False)
KALLE = User(id=22, first_name="Kalle", is_bot=False)

SCOUT = "76561198000000011"
MATE = "76561198000000022"


class FakeClient:
    def __init__(self, histories=None, details=None):
        self.histories = histories or {}
        self.details = details or {}

    async def get_match_history(self, steam64_id):
        return self.histories.get(steam64_id)

    async def get_match(self, game_id):
        return self.details.get(game_id)


def _event(event_date, users, completed=True, cancelled=False, cs2_reported=False):
    event = MagicMock()
    event.event_date = event_date
    event.poll_answers = {user: MagicMock() for user in users}
    event.completed = completed
    event.cancelled = cancelled
    event.cs2_reported = cs2_reported
    return event


def _chat(events):
    chat = MagicMock()
    chat.events = {event.event_date: event for event in events}
    return chat


def _user_data(links):
    return {user_id: MagicMock(steam64_id=steam) for user_id, steam in links.items()}


def _played_match():
    return MatchDetail(
        id="m1",
        finished_at="2026-09-02T19:00:00.000Z",
        data_source="matchmaking_competitive",
        map_name="de_mirage",
        team_scores={2: 13, 3: 7},
        players=(
            PlayerStats(SCOUT, "tommy", 20, 10, 2.0, 3, 2),
            PlayerStats(MATE, "kalle", 12, 14, 0.86, 1, 2),
        ),
    )


class EventResultsTest(unittest.IsolatedAsyncioTestCase):
    async def test_renders_a_session_and_reports_who_played(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS, KALLE])])
        client = FakeClient(
            histories={SCOUT: [MatchSummary("m1", "2026-09-02T19:00:00.000Z", "matchmaking_competitive", "de_mirage")]},
            details={"m1": _played_match()},
        )

        session, text = await event_results(
            client, chat, chat.events[date(2026, 9, 2)], _user_data({11: SCOUT, 22: MATE})
        )

        self.assertEqual(session.played_user_ids, {11, 22})
        self.assertIn("de\\_mirage", text)
        self.assertIn("tommy", text, "CS2 views label everyone by their in-game name")

    async def test_returns_no_text_when_leetify_is_unreachable(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS])])

        session, text = await event_results(FakeClient(), chat, chat.events[date(2026, 9, 2)], _user_data({11: SCOUT}))

        self.assertIsNone(session)
        self.assertIsNone(text)

    async def test_renders_an_empty_session_when_nobody_played(self):
        chat = _chat([_event(date(2026, 9, 2), [THOMAS])])
        client = FakeClient(histories={SCOUT: []})

        session, text = await event_results(client, chat, chat.events[date(2026, 9, 2)], _user_data({11: SCOUT}))

        self.assertEqual(session.matches, [])
        self.assertIn("No ONGA matches", text)


class LatestReportableEventTest(unittest.TestCase):
    def test_picks_the_most_recent_completed_event(self):
        old = _event(date(2026, 8, 26), [THOMAS])
        recent = _event(date(2026, 9, 2), [THOMAS])

        self.assertIs(latest_reportable_event(_chat([old, recent])), recent)

    def test_ignores_events_that_have_not_completed(self):
        completed = _event(date(2026, 8, 26), [THOMAS])
        upcoming = _event(date(2026, 9, 9), [THOMAS], completed=False)

        self.assertIs(latest_reportable_event(_chat([completed, upcoming])), completed)

    def test_ignores_cancelled_events(self):
        completed = _event(date(2026, 8, 26), [THOMAS])
        cancelled = _event(date(2026, 9, 2), [THOMAS], cancelled=True)

        self.assertIs(latest_reportable_event(_chat([completed, cancelled])), completed)

    def test_returns_none_when_there_is_nothing_to_report(self):
        self.assertIsNone(latest_reportable_event(_chat([])))


if __name__ == "__main__":
    unittest.main()
