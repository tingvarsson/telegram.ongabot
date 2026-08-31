import unittest
from datetime import date, datetime

from telegram import User

from ongabot.cs2.format import ATTRIBUTION, MAX_MESSAGE_CHARS, format_session
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine

USERS = {
    11: User(id=11, first_name="Thomas", is_bot=False),
    22: User(id=22, first_name="Kalle", is_bot=False),
}

EVENT_DATE = date(2026, 9, 2)


def _member(user_id, name, kills, deaths, kd_ratio, mvps=1, team=2):
    return PlayerLine(
        user_id=user_id,
        steam64_id=f"7656119800000000{user_id}",
        name=name,
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=kd_ratio,
        mvps=mvps,
        team_number=team,
    )


def _stranger(name, kills=10, deaths=10, team=3):
    return PlayerLine(
        user_id=None,
        steam64_id=f"765611989{abs(hash(name)) % 100000000:08d}",
        name=name,
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=round(kills / deaths, 2) if deaths else 0.0,
        mvps=0,
        team_number=team,
    )


def _match(
    match_id="2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b",
    map_name="de_mirage",
    score=(13, 7),
    players=None,
    finished_at=datetime(2026, 9, 2, 21, 2),
):
    if players is None:
        players = [
            _member(11, "tommy", 23, 15, 1.53, 2),
            _member(22, "kalle", 9, 7, 1.29, 1),
            _stranger("teammate1", team=2),
            _stranger("enemy1"),
            _stranger("enemy2"),
        ]
    return Cs2Match(
        id=match_id,
        map_name=map_name,
        finished_at=finished_at,
        score=score,
        our_team=2,
        players=tuple(players),
    )


def _session(matches=None):
    return Cs2Session(EVENT_DATE, list(matches if matches is not None else [_match()]))


class HeaderAndSummaryTest(unittest.TestCase):
    def test_header_carries_the_event_date(self):
        text = format_session(_session(), USERS)

        self.assertIn("2026\\-09\\-02", text.split("\n")[0])

    def test_summary_counts_wins_and_losses(self):
        text = format_session(
            _session([_match(match_id="a", score=(13, 7)), _match(match_id="b", score=(7, 13))]),
            USERS,
        )

        self.assertIn("1W", text)
        self.assertIn("1L", text)

    def test_summary_reports_draws(self):
        self.assertIn("1D", format_session(_session([_match(score=(12, 12))]), USERS))

    def test_summary_flags_overtime_matches(self):
        self.assertIn("OT", format_session(_session([_match(score=(19, 16))]), USERS))

    def test_summary_omits_overtime_when_there_was_none(self):
        self.assertNotIn("OT", format_session(_session([_match(score=(13, 7))]), USERS))


class SessionPlayerSummaryTest(unittest.TestCase):
    def test_combines_each_members_stats_across_matches(self):
        session = _session(
            [
                _match(match_id="a", players=[_member(11, "tommy", 20, 10, 2.0), _member(22, "kalle", 5, 10, 0.5)]),
                _match(match_id="b", players=[_member(11, "tommy", 10, 10, 1.0), _member(22, "kalle", 5, 10, 0.5)]),
            ]
        )

        text = format_session(session, USERS)
        row = next(line for line in text.splitlines() if line.startswith("Thomas"))

        self.assertIn("30", row, "kills should be summed across both matches")
        self.assertIn("20", row, "deaths should be summed across both matches")
        self.assertIn("1.50", row, "combined K/D is 30/20")

    def test_counts_matches_played_per_member(self):
        session = _session(
            [
                _match(match_id="a", players=[_member(11, "tommy", 20, 10, 2.0), _member(22, "kalle", 5, 10, 0.5)]),
                _match(match_id="b", players=[_member(11, "tommy", 10, 10, 1.0)]),
            ]
        )

        text = format_session(session, USERS)
        thomas = next(line for line in text.splitlines() if line.startswith("Thomas"))
        kalle = next(line for line in text.splitlines() if line.startswith("Kalle"))

        self.assertRegex(thomas, r"Thomas\s+2\s")
        self.assertRegex(kalle, r"Kalle\s+1\s")

    def test_summary_covers_members_only_not_the_whole_lobby(self):
        text = format_session(_session(), USERS)
        summary = text.split("*de\\_mirage")[0]

        self.assertIn("Thomas", summary)
        self.assertNotIn("enemy1", summary)
        self.assertNotIn("teammate1", summary)

    def test_zero_deaths_does_not_divide_by_zero(self):
        session = _session([_match(players=[_member(11, "tommy", 5, 0, 0.0), _member(22, "kalle", 1, 1, 1.0)])])

        self.assertIn("-", format_session(session, USERS))


class MatchScoreboardTest(unittest.TestCase):
    def test_lists_every_player_in_the_lobby(self):
        text = format_session(_session(), USERS)

        for name in ("Thomas", "Kalle", "teammate1", "enemy1", "enemy2"):
            self.assertIn(name, text)

    def test_our_side_is_listed_before_the_opposition(self):
        text = format_session(_session(), USERS)
        block = text.split("*de\\_mirage")[1]

        self.assertLess(block.index("teammate1"), block.index("enemy1"), "our team must come first")

    def test_members_are_marked_and_strangers_are_not(self):
        # Scoped to the match block: the session summary lists members without a marker.
        block = format_session(_session(), USERS).split("*de\\_mirage")[1]
        thomas = next(line for line in block.splitlines() if "Thomas" in line)
        enemy = next(line for line in block.splitlines() if "enemy1" in line)

        self.assertTrue(thomas.startswith("*"), thomas)
        self.assertFalse(enemy.startswith("*"), enemy)

    def test_strangers_are_shown_by_their_ingame_name(self):
        self.assertIn("enemy1", format_session(_session(), USERS))

    def test_members_are_shown_by_their_telegram_display_name(self):
        text = format_session(_session(), USERS)

        self.assertIn("Thomas", text)
        self.assertNotIn("tommy", text)

    def test_heading_shows_the_match_end_time(self):
        self.assertIn("21:02", format_session(_session(), USERS))

    def test_heading_omits_the_time_when_it_could_not_be_parsed(self):
        text = format_session(_session([_match(finished_at=None)]), USERS)

        self.assertIn("de\\_mirage", text)
        self.assertNotIn("ended", text)

    def test_shows_map_score_and_outcome(self):
        text = format_session(_session(), USERS)

        self.assertIn("de\\_mirage", text)
        self.assertIn("13\\-7", text)

    def test_links_each_match_back_to_leetify(self):
        self.assertIn(
            "https://leetify.com/app/match-details/2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b",
            format_session(_session(), USERS),
        )

    def test_includes_required_leetify_attribution(self):
        self.assertIn(ATTRIBUTION, format_session(_session(), USERS))

    def test_says_so_when_nothing_was_played(self):
        text = format_session(_session([]), USERS)

        self.assertTrue(text)
        self.assertNotIn("```", text)


class MessageLengthTest(unittest.TestCase):
    """Ten players per match makes Telegram's 4096-character limit reachable."""

    def _long_session(self, count):
        players = [_member(11, "tommy", 23, 15, 1.53), _member(22, "kalle", 9, 7, 1.29)]
        players += [_stranger(f"teammate{i}", team=2) for i in range(3)]
        players += [_stranger(f"opponent{i}", team=3) for i in range(5)]
        return Cs2Session(
            EVENT_DATE,
            [
                _match(match_id=f"match-{i:04d}", players=players, finished_at=datetime(2026, 9, 2, 12 + i % 10, 0))
                for i in range(count)
            ],
        )

    def test_a_long_session_still_fits_in_one_telegram_message(self):
        text = format_session(self._long_session(12), USERS)

        self.assertLessEqual(len(text), MAX_MESSAGE_CHARS)

    def test_a_trimmed_session_says_how_many_matches_were_dropped(self):
        text = format_session(self._long_session(12), USERS)

        self.assertIn("not shown", text)

    def test_a_trimmed_session_keeps_the_summary_and_attribution(self):
        text = format_session(self._long_session(12), USERS)

        self.assertIn("CS2 results", text)
        self.assertIn(ATTRIBUTION, text)
        self.assertIn("12 matches", text, "the summary must still count every match played")

    def test_a_short_session_is_not_trimmed(self):
        self.assertNotIn("not shown", format_session(self._long_session(2), USERS))


class MarkdownEscapingTest(unittest.TestCase):
    def test_leaves_underscores_literal_inside_the_code_block(self):
        """MarkdownV2 escapes only ` and \\ inside pre entities."""
        users = {11: User(id=11, first_name="a_b", is_bot=False), 22: USERS[22]}

        text = format_session(_session(), users)

        self.assertIn("a_b", text)
        self.assertNotIn("a\\_b", text)

    def test_escapes_backticks_in_a_stranger_name(self):
        """Non-member names come straight from Leetify and are outside our control."""
        session = _session([_match(players=[_member(11, "tommy", 1, 1, 1.0), _stranger("ab`c")])])

        self.assertIn("ab\\`c", format_session(session, USERS))

    def test_escapes_backslashes_in_a_stranger_name(self):
        session = _session([_match(players=[_member(11, "tommy", 1, 1, 1.0), _stranger("ab\\c")])])

        self.assertIn("ab\\\\c", format_session(session, USERS))


if __name__ == "__main__":
    unittest.main()
