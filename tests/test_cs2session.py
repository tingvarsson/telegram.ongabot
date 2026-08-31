import os
import time
import unittest
from datetime import date

from ongabot.cs2.leetify import MatchDetail, MatchSummary, PlayerStats
from ongabot.cs2.session import DEFAULT_MIN_MEMBERS, build_session, local_date, min_members

SCOUT = "76561198000000001"
MATE = "76561198000000002"
SECOND_SCOUT = "76561198000000003"
STRANGER = "76561198999999999"

LINKS = {11: SCOUT, 22: MATE, 33: SECOND_SCOUT}


def _summary(match_id, finished_at, data_source="matchmaking_competitive", map_name="de_mirage"):
    return MatchSummary(id=match_id, finished_at=finished_at, data_source=data_source, map_name=map_name)


def _player(steam64_id, kills=10, deaths=10, team=2):
    return PlayerStats(
        steam64_id=steam64_id,
        name=f"player-{steam64_id[-1]}",
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=round(kills / deaths, 2) if deaths else 0.0,
        mvps=1,
        initial_team_number=team,
    )


def _detail(match_id, steam_ids, finished_at="2026-09-02T19:00:00.000Z", map_name="de_mirage"):
    return MatchDetail(
        id=match_id,
        finished_at=finished_at,
        data_source="matchmaking_competitive",
        map_name=map_name,
        team_scores={2: 13, 3: 7},
        players=tuple(_player(sid) for sid in steam_ids),
    )


class FakeClient:
    """A real stand-in, not a mock: it records calls and returns canned API shapes.

    histories maps steam64 -> list of MatchSummary, or None to mean "Leetify has no data".
    """

    def __init__(self, histories, details):
        self.histories = histories
        self.details = details
        self.history_calls = []
        self.detail_calls = []

    async def get_match_history(self, steam64_id):
        self.history_calls.append(steam64_id)
        return self.histories.get(steam64_id)

    async def get_match(self, game_id):
        self.detail_calls.append(game_id)
        return self.details.get(game_id)


class LocalDateTest(unittest.TestCase):
    """finished_at is UTC; the event date is a local calendar date."""

    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Stockholm"
        time.tzset()

    def tearDown(self):
        if self._old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    def test_late_evening_utc_match_belongs_to_the_local_next_day(self):
        # 22:30Z in September is 00:30 the next morning in Stockholm (CEST, UTC+2).
        self.assertEqual(local_date("2026-09-02T22:30:00.000Z"), date(2026, 9, 3))

    def test_evening_match_stays_on_the_same_local_day(self):
        self.assertEqual(local_date("2026-09-02T19:02:30.000Z"), date(2026, 9, 2))

    def test_returns_none_for_unparseable_timestamp(self):
        self.assertIsNone(local_date("not-a-timestamp"))


class BuildSessionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()

    def tearDown(self):
        if self._old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    async def test_finds_a_match_two_linked_members_played(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": _detail("m1", [SCOUT, MATE, STRANGER])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(len(session.matches), 1)
        self.assertEqual(session.matches[0].map_name, "de_mirage")
        self.assertEqual({m.user_id for m in session.matches[0].members}, {11, 22})

    async def test_excludes_matches_from_other_days(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-01T19:00:00.000Z")]},
            details={"m1": _detail("m1", [SCOUT, MATE])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(session.matches, [])
        self.assertEqual(client.detail_calls, [], "must not fetch details for matches on other days")

    async def test_excludes_non_qualifying_game_modes(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z", data_source="faceit")]},
            details={"m1": _detail("m1", [SCOUT, MATE])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(session.matches, [])

    async def test_includes_premier_matches(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z", data_source="matchmaking")]},
            details={"m1": _detail("m1", [SCOUT, MATE])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(len(session.matches), 1)

    async def test_drops_matches_below_the_member_threshold(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": _detail("m1", [SCOUT, STRANGER])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(min_members(), 2)
        self.assertEqual(session.matches, [], "one linked member is a solo game, not an ONGA game")

    async def test_fetches_a_shared_match_only_once(self):
        shared = _summary("m1", "2026-09-02T19:00:00.000Z")
        client = FakeClient(
            histories={SCOUT: [shared], SECOND_SCOUT: [shared]},
            details={"m1": _detail("m1", [SCOUT, SECOND_SCOUT])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(len(session.matches), 1)
        self.assertEqual(client.detail_calls, ["m1"])

    async def test_one_scout_reveals_members_who_have_no_leetify_account(self):
        """The whole partial-enrolment design: MATE never appears in a history, only a lobby."""
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")], MATE: None},
            details={"m1": _detail("m1", [SCOUT, MATE])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual({m.user_id for m in session.matches[0].members}, {11, 22})

    async def test_returns_none_when_leetify_is_unreachable_for_everyone(self):
        client = FakeClient(histories={}, details={})

        self.assertIsNone(
            await build_session(client, date(2026, 9, 2), LINKS),
            "an all-failed sweep must be retryable, not reported as 'nobody played'",
        )

    async def test_returns_empty_session_when_reachable_but_nothing_was_played(self):
        client = FakeClient(histories={SCOUT: []}, details={})

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertIsNotNone(session)
        self.assertEqual(session.matches, [])

    async def test_played_user_ids_lists_every_member_seen_in_any_match(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T18:00:00.000Z"), _summary("m2", "2026-09-02T20:00:00.000Z")]},
            details={
                "m1": _detail("m1", [SCOUT, MATE]),
                "m2": _detail("m2", [SCOUT, SECOND_SCOUT]),
            },
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(session.played_user_ids, {11, 22, 33})

    async def test_orders_matches_by_when_they_finished(self):
        client = FakeClient(
            histories={
                SCOUT: [_summary("late", "2026-09-02T21:00:00.000Z"), _summary("early", "2026-09-02T18:00:00.000Z")]
            },
            details={
                "late": _detail("late", [SCOUT, MATE], finished_at="2026-09-02T21:00:00.000Z"),
                "early": _detail("early", [SCOUT, MATE], finished_at="2026-09-02T18:00:00.000Z"),
            },
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual([m.id for m in session.matches], ["early", "late"])

    async def test_skips_a_match_whose_detail_cannot_be_fetched(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(session.matches, [])

    async def test_reports_the_score_from_the_members_side(self):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": _detail("m1", [SCOUT, MATE])},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        # _detail puts every player on team 2, which won 13-7.
        self.assertEqual(session.matches[0].score, (13, 7))
        self.assertTrue(session.matches[0].won)


class SplitTeamScoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()

    def tearDown(self):
        if self._old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    async def test_reports_highest_first_when_members_queued_onto_opposite_teams(self):
        """With members on both sides there is no 'our side' to take the score from."""
        detail = MatchDetail(
            id="m1",
            finished_at="2026-09-02T19:00:00.000Z",
            data_source="matchmaking_competitive",
            map_name="de_mirage",
            team_scores={2: 7, 3: 13},
            players=(_player(SCOUT, team=2), _player(MATE, team=3)),
        )
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": detail},
        )

        session = await build_session(client, date(2026, 9, 2), LINKS)

        self.assertEqual(session.matches[0].score, (13, 7))

    async def test_returns_an_empty_session_when_nobody_has_linked_an_account(self):
        client = FakeClient(histories={}, details={})

        session = await build_session(client, date(2026, 9, 2), {})

        self.assertEqual(session.matches, [])
        self.assertEqual(client.history_calls, [], "no links means no Leetify calls at all")


class MinMembersConfigTest(unittest.TestCase):
    """CS2_MIN_MEMBERS lets a single-user test setup see results; production keeps 2."""

    def setUp(self):
        self._old = os.environ.pop("CS2_MIN_MEMBERS", None)

    def tearDown(self):
        os.environ.pop("CS2_MIN_MEMBERS", None)
        if self._old is not None:
            os.environ["CS2_MIN_MEMBERS"] = self._old

    def test_defaults_to_two(self):
        self.assertEqual(min_members(), DEFAULT_MIN_MEMBERS)
        self.assertEqual(DEFAULT_MIN_MEMBERS, 2)

    def test_env_var_overrides_the_default(self):
        os.environ["CS2_MIN_MEMBERS"] = "1"
        self.assertEqual(min_members(), 1)

    def test_falls_back_to_the_default_for_a_non_numeric_value(self):
        os.environ["CS2_MIN_MEMBERS"] = "lots"
        self.assertEqual(min_members(), DEFAULT_MIN_MEMBERS)

    def test_falls_back_to_the_default_for_a_value_below_one(self):
        os.environ["CS2_MIN_MEMBERS"] = "0"
        self.assertEqual(min_members(), DEFAULT_MIN_MEMBERS)


class SingleLinkedMemberTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        self._old_min = os.environ.pop("CS2_MIN_MEMBERS", None)

    def tearDown(self):
        os.environ.pop("CS2_MIN_MEMBERS", None)
        if self._old_min is not None:
            os.environ["CS2_MIN_MEMBERS"] = self._old_min
        if self._old_tz is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    def _client(self):
        return FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": _detail("m1", [SCOUT, STRANGER])},
        )

    async def test_a_solo_game_is_hidden_by_default(self):
        session = await build_session(self._client(), date(2026, 9, 2), {11: SCOUT})

        self.assertEqual(session.matches, [])

    async def test_a_solo_game_shows_up_when_the_threshold_is_lowered_to_one(self):
        os.environ["CS2_MIN_MEMBERS"] = "1"

        session = await build_session(self._client(), date(2026, 9, 2), {11: SCOUT})

        self.assertEqual(len(session.matches), 1)
        self.assertEqual(session.played_user_ids, {11})


if __name__ == "__main__":
    unittest.main()
