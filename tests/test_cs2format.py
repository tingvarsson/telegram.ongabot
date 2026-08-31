import unittest
from datetime import date, datetime

from ongabot.cs2.format import ATTRIBUTION, MAX_MESSAGE_CHARS, format_session
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine
from ongabot.utils.statistics import display_width

EVENT_DATE = date(2026, 9, 2)


def _member(user_id, name, kills, deaths, kd_ratio, mvps=1, team=2, assists=4, adr=82.5, aces=0, rounds=15):
    return PlayerLine(
        user_id=user_id,
        steam64_id=f"7656119800000000{user_id}",
        name=name,
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=kd_ratio,
        mvps=mvps,
        team_number=team,
        total_assists=assists,
        adr=adr,
        multi5k=aces,
        total_damage=int(adr * rounds),
        rounds_count=rounds,
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
        total_assists=2,
        adr=61.0,
        multi5k=0,
        total_damage=915,
        rounds_count=15,
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


def _scoreboard(text, index=1):
    """The lines inside the index-th fenced code block (0 is the session table)."""
    return [line for line in text.split("```")[1 + index * 2].splitlines() if line.strip()]


def _session(matches=None):
    return Cs2Session(EVENT_DATE, list(matches if matches is not None else [_match()]))


class HeaderAndSummaryTest(unittest.TestCase):
    def test_header_carries_the_event_date(self):
        text = format_session(_session())

        self.assertIn("2026\\-09\\-02", text.split("\n")[0])

    def test_summary_counts_wins_and_losses(self):
        text = format_session(_session([_match(match_id="a", score=(13, 7)), _match(match_id="b", score=(7, 13))]))

        self.assertIn("1W", text)
        self.assertIn("1L", text)

    def test_summary_reports_draws(self):
        self.assertIn("1D", format_session(_session([_match(score=(12, 12))])))

    def test_summary_flags_overtime_matches(self):
        self.assertIn("OT", format_session(_session([_match(score=(19, 16))])))

    def test_summary_omits_overtime_when_there_was_none(self):
        self.assertNotIn("OT", format_session(_session([_match(score=(13, 7))])))


class SessionPlayerSummaryTest(unittest.TestCase):
    def test_combines_each_members_stats_across_matches(self):
        session = _session(
            [
                _match(match_id="a", players=[_member(11, "tommy", 20, 10, 2.0), _member(22, "kalle", 5, 10, 0.5)]),
                _match(match_id="b", players=[_member(11, "tommy", 10, 10, 1.0), _member(22, "kalle", 5, 10, 0.5)]),
            ]
        )

        text = format_session(session)
        row = next(line for line in text.splitlines() if line.startswith("tommy"))

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

        text = format_session(session)
        tommy = next(line for line in text.splitlines() if line.startswith("tommy"))
        kalle = next(line for line in text.splitlines() if line.startswith("kalle"))

        self.assertRegex(tommy, r"tommy\s+2\s")
        self.assertRegex(kalle, r"kalle\s+1\s")

    def test_summary_covers_members_only_not_the_whole_lobby(self):
        text = format_session(_session())
        summary = text.split("*de\\_mirage")[0]

        self.assertIn("tommy", summary)
        self.assertNotIn("enemy1", summary)
        self.assertNotIn("teammate1", summary)

    def test_zero_deaths_does_not_divide_by_zero(self):
        session = _session([_match(players=[_member(11, "tommy", 5, 0, 0.0), _member(22, "kalle", 1, 1, 1.0)])])

        self.assertIn("-", format_session(session))


class MatchScoreboardTest(unittest.TestCase):
    def test_lists_every_player_in_the_lobby(self):
        text = format_session(_session())

        for name in ("tommy", "kalle", "teammate1", "enemy1", "enemy2"):
            self.assertIn(name, text)

    def test_our_side_is_listed_before_the_opposition(self):
        text = format_session(_session())
        block = text.split("*de\\_mirage")[1]

        self.assertLess(block.index("teammate1"), block.index("enemy1"), "our team must come first")

    def test_no_row_is_marked_since_bold_is_impossible_inside_a_code_block(self):
        """Telegram forbids nesting bold in pre/code, so members are not singled out.

        The session table above the boards is what says who is in the chat.
        """
        rows = _scoreboard(format_session(_session()))

        self.assertTrue(all(not row.startswith(("*", "+", ">")) for row in rows), rows)

    def test_strangers_are_shown_by_their_ingame_name(self):
        self.assertIn("enemy1", format_session(_session()))

    def test_heading_shows_the_match_end_time(self):
        self.assertIn("21:02", format_session(_session()))

    def test_heading_omits_the_time_when_it_could_not_be_parsed(self):
        text = format_session(_session([_match(finished_at=None)]))

        self.assertIn("de\\_mirage", text)
        self.assertNotIn("ended", text)

    def test_shows_map_score_and_outcome(self):
        text = format_session(_session())

        self.assertIn("de\\_mirage", text)
        self.assertIn("13\\-7", text)

    def test_links_each_match_back_to_leetify(self):
        self.assertIn(
            "https://leetify.com/app/match-details/2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b",
            format_session(_session()),
        )

    def test_includes_required_leetify_attribution(self):
        self.assertIn(ATTRIBUTION, format_session(_session()))

    def test_says_so_when_nothing_was_played(self):
        text = format_session(_session([]))

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
        text = format_session(self._long_session(12))

        self.assertLessEqual(len(text), MAX_MESSAGE_CHARS)

    def test_a_trimmed_session_says_how_many_matches_were_dropped(self):
        text = format_session(self._long_session(12))

        self.assertIn("not shown", text)

    def test_a_trimmed_session_keeps_the_summary_and_attribution(self):
        text = format_session(self._long_session(12))

        self.assertIn("CS2 results", text)
        self.assertIn(ATTRIBUTION, text)
        self.assertIn("12 matches", text, "the summary must still count every match played")

    def test_a_short_session_is_not_trimmed(self):
        self.assertNotIn("not shown", format_session(self._long_session(2)))


class MarkdownEscapingTest(unittest.TestCase):
    def test_leaves_underscores_literal_inside_the_code_block(self):
        """MarkdownV2 escapes only ` and \\ inside pre entities."""
        session = _session([_match(players=[_member(11, "a_b", 1, 1, 1.0), _stranger("plain")])])

        text = format_session(session)

        self.assertIn("a_b", text)
        self.assertNotIn("a\\_b", text)

    def test_escapes_backticks_in_a_stranger_name(self):
        """Non-member names come straight from Leetify and are outside our control."""
        session = _session([_match(players=[_member(11, "tommy", 1, 1, 1.0), _stranger("ab`c")])])

        self.assertIn("ab\\`c", format_session(session))

    def test_escapes_backslashes_in_a_stranger_name(self):
        session = _session([_match(players=[_member(11, "tommy", 1, 1, 1.0), _stranger("ab\\c")])])

        self.assertIn("ab\\\\c", format_session(session))


class StatColumnsTest(unittest.TestCase):
    """The per-match board carries K, A, D, K/D, ADR and aces."""

    def _row(self, name="tommy", **kw):
        session = _session([_match(players=[_member(11, name, 23, 15, 1.53, **kw), _stranger("plain")])])
        block = format_session(session).split("*de\\_mirage")[1]
        return next(line for line in block.splitlines() if name in line)

    def test_shows_assists(self):
        self.assertRegex(self._row(assists=7), r"\s7\s")

    def test_shows_adr_rounded_to_whole_damage(self):
        self.assertRegex(self._row(adr=88.4), r"\s88\s*$|\s88\s")

    def test_shows_aces(self):
        self.assertRegex(self._row(aces=2), r"\s2\s*$")

    def test_shows_kd_ratio_as_leetify_reports_it(self):
        self.assertIn("1.53", self._row())

    def test_header_names_every_column(self):
        header = _scoreboard(format_session(_session()))[0]

        for column in ("Name", "K", "A", "D", "K/D", "ADR", "5k"):
            self.assertIn(column, header)

    def test_every_scoreboard_row_is_the_same_width(self):
        rows = [r for r in _scoreboard(format_session(_session())) if r.strip() != "--"]

        self.assertEqual(len({display_width(r) for r in rows}), 1, rows)


class SessionAdrTest(unittest.TestCase):
    def test_session_adr_is_damage_over_rounds_not_an_average_of_averages(self):
        """A 30-round match and a 3-round one must not weigh the same."""
        session = _session(
            [
                _match(match_id="a", players=[_member(11, "tommy", 1, 1, 1.0, adr=100.0, rounds=30), _stranger("x")]),
                _match(match_id="b", players=[_member(11, "tommy", 1, 1, 1.0, adr=10.0, rounds=3), _stranger("y")]),
            ]
        )

        text = format_session(session)
        row = next(line for line in text.splitlines() if line.startswith("tommy"))

        # (100*30 + 10*3) / 33 = 91.8, not the naive (100+10)/2 = 55.
        self.assertIn("92", row)
        self.assertNotIn("55", row)

    def test_session_table_sums_assists_and_aces(self):
        session = _session(
            [
                _match(match_id="a", players=[_member(11, "tommy", 1, 1, 1.0, assists=3, aces=1), _stranger("x")]),
                _match(match_id="b", players=[_member(11, "tommy", 1, 1, 1.0, assists=4, aces=1), _stranger("y")]),
            ]
        )

        row = next(line for line in format_session(session).splitlines() if line.startswith("tommy"))

        self.assertRegex(row, r"\s7\s", "assists 3 + 4")
        self.assertRegex(row, r"\s2\s*$", "aces 1 + 1")


if __name__ == "__main__":
    unittest.main()
