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

    async def test_an_evenly_split_lobby_takes_the_first_members_side(self):
        """One member per side is a tie, broken by the first member - SCOUT, on team 2.

        Reporting highest-first instead would claim a win for a match half of them lost.
        """
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

        match = (await build_session(client, date(2026, 9, 2), LINKS)).matches[0]

        self.assertEqual(match.our_team, 2)
        self.assertEqual(match.score, (7, 13))
        self.assertEqual(match.outcome, "L")

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


def _detail_10(match_id, member_steams, scores=(13, 7), our_team=2, finished="2026-09-02T19:00:00.000Z"):
    """A realistic 10-player lobby: members on our_team, strangers filling both sides."""
    players = []
    for i, sid in enumerate(member_steams):
        players.append(_player(sid, kills=20 - i, deaths=10, team=our_team))
    other_team = 3 if our_team == 2 else 2
    for i in range(5 - len(member_steams)):
        players.append(_player(f"7656119870000000{i}", kills=5 + i, deaths=12, team=our_team))
    for i in range(5):
        players.append(_player(f"7656119880000000{i}", kills=8 + i, deaths=11, team=other_team))
    return MatchDetail(
        id=match_id,
        finished_at=finished,
        data_source="matchmaking_competitive",
        map_name="de_mirage",
        team_scores={our_team: scores[0], other_team: scores[1]},
        players=tuple(players),
    )


class AllPlayersTest(unittest.IsolatedAsyncioTestCase):
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

    async def _build(self, detail, links=None):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": detail},
        )
        return await build_session(client, date(2026, 9, 2), links if links is not None else LINKS)

    async def test_carries_every_player_in_the_lobby(self):
        session = await self._build(_detail_10("m1", [SCOUT, MATE]))

        self.assertEqual(len(session.matches[0].players), 10)

    async def test_members_are_flagged_and_non_members_are_not(self):
        match = (await self._build(_detail_10("m1", [SCOUT, MATE]))).matches[0]

        members = [p for p in match.players if p.is_member]
        self.assertEqual({p.user_id for p in members}, {11, 22})
        self.assertTrue(all(p.user_id is None for p in match.players if not p.is_member))

    async def test_members_property_still_returns_only_linked_players(self):
        match = (await self._build(_detail_10("m1", [SCOUT, MATE]))).matches[0]

        self.assertEqual(len(match.members), 2)

    async def test_played_user_ids_still_counts_only_members(self):
        """Drives Event.cs2_played - strangers must never leak into it."""
        session = await self._build(_detail_10("m1", [SCOUT, MATE]))

        self.assertEqual(session.played_user_ids, {11, 22})

    async def test_threshold_still_counts_members_not_lobby_size(self):
        """A full 10-player lobby with one linked member is still a solo game."""
        session = await self._build(_detail_10("m1", [SCOUT]), links={11: SCOUT})

        self.assertEqual(session.matches, [])


class MatchOutcomeTest(unittest.IsolatedAsyncioTestCase):
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

    async def _match(self, scores, our_team=2):
        client = FakeClient(
            histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]},
            details={"m1": _detail_10("m1", [SCOUT, MATE], scores=scores, our_team=our_team)},
        )
        session = await build_session(client, date(2026, 9, 2), LINKS)
        return session.matches[0]

    async def test_win(self):
        match = await self._match((13, 7))
        self.assertEqual(match.outcome, "W")
        self.assertEqual(match.score, (13, 7))

    async def test_loss(self):
        match = await self._match((7, 13))
        self.assertEqual(match.outcome, "L")

    async def test_draw(self):
        """CS2 competitive has no overtime, so 12-12 is a real result."""
        match = await self._match((12, 12))
        self.assertEqual(match.outcome, "D")

    async def test_score_is_from_our_side_even_when_we_are_team_three(self):
        match = await self._match((13, 5), our_team=3)
        self.assertEqual(match.score, (13, 5))
        self.assertEqual(match.outcome, "W")

    async def test_regulation_win_is_not_overtime(self):
        self.assertFalse((await self._match((13, 7))).overtime)

    async def test_a_score_above_thirteen_is_overtime(self):
        """MR12: 13 ends regulation, so anything higher can only come from OT."""
        self.assertTrue((await self._match((19, 16))).overtime)

    async def test_a_draw_is_not_overtime(self):
        self.assertFalse((await self._match((12, 12))).overtime)


class SplitTeamPerspectiveTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_our_side_is_where_most_members_started(self):
        """Two members on team 2, one on team 3 -> team 2 is 'us', which won 13-7."""
        detail = MatchDetail(
            id="m1",
            finished_at="2026-09-02T19:00:00.000Z",
            data_source="matchmaking_competitive",
            map_name="de_mirage",
            team_scores={2: 13, 3: 7},
            players=(
                _player(SCOUT, team=2),
                _player(MATE, team=2),
                _player(SECOND_SCOUT, team=3),
            ),
        )
        client = FakeClient(histories={SCOUT: [_summary("m1", "2026-09-02T19:00:00.000Z")]}, details={"m1": detail})

        match = (await build_session(client, date(2026, 9, 2), LINKS)).matches[0]

        self.assertEqual(match.our_team, 2)
        self.assertEqual(match.score, (13, 7))
        self.assertEqual(match.outcome, "W")


if __name__ == "__main__":
    unittest.main()
