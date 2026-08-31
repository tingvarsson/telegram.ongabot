import unittest
from datetime import date, datetime

from telegram import User

from ongabot.cs2.format import ATTRIBUTION, format_session
from ongabot.cs2.session import Cs2Match, Cs2Session, MemberLine

USERS = {
    11: User(id=11, first_name="Thomas", is_bot=False),
    22: User(id=22, first_name="Kalle", is_bot=False),
}


def _member(user_id, name, kills, deaths, kd_ratio, mvps=1, team=2):
    return MemberLine(
        user_id=user_id,
        steam64_id=f"7656119800000000{user_id}",
        name=name,
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=kd_ratio,
        mvps=mvps,
        team_number=team,
    )


def _match(match_id="2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b", map_name="de_mirage", score=(13, 7), members=None):
    return Cs2Match(
        id=match_id,
        map_name=map_name,
        finished_at=datetime(2026, 9, 2, 21, 0),
        score=score,
        members=tuple(
            members if members is not None else [_member(11, "tommy", 23, 15, 1.53), _member(22, "kalle", 9, 7, 1.29)]
        ),
    )


def _session(matches=None):
    return Cs2Session(date(2026, 9, 2), list(matches if matches is not None else [_match()]))


class FormatSessionTest(unittest.TestCase):
    def test_shows_map_and_score(self):
        text = format_session(_session(), USERS)

        self.assertIn("de\\_mirage", text, "underscores in map names must be escaped for MarkdownV2")
        self.assertIn("13\\-7", text)

    def test_shows_each_members_leetify_stats(self):
        text = format_session(_session(), USERS)

        self.assertIn("23", text)
        self.assertIn("1.53", text)

    def test_labels_members_by_telegram_display_name_not_ingame_name(self):
        """Names must match every other table the bot renders, per utils.statistics.display_names."""
        text = format_session(_session(), USERS)

        self.assertIn("Thomas", text)
        self.assertIn("Kalle", text)
        self.assertNotIn("tommy", text)

    def test_includes_required_leetify_attribution(self):
        self.assertIn(ATTRIBUTION, format_session(_session(), USERS))

    def test_links_each_match_back_to_leetify(self):
        text = format_session(_session(), USERS)

        self.assertIn("https://leetify.com/app/match-details/2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b", text)

    def test_marks_a_win_and_a_loss_differently(self):
        won = format_session(_session([_match(score=(13, 7))]), USERS)
        lost = format_session(_session([_match(score=(7, 13))]), USERS)

        self.assertNotEqual(won, lost)

    def test_renders_every_match_of_the_session(self):
        text = format_session(
            _session([_match(match_id="a", map_name="de_mirage"), _match(match_id="b", map_name="de_nuke")]),
            USERS,
        )

        self.assertIn("de\\_mirage", text)
        self.assertIn("de\\_nuke", text)

    def test_says_so_when_nothing_was_played(self):
        text = format_session(_session([]), USERS)

        self.assertTrue(text)
        self.assertNotIn("```", text, "an empty session has no table to show")

    def test_falls_back_to_the_ingame_name_for_an_unknown_user(self):
        """A member can be linked but never have answered a poll, so have no Telegram User."""
        text = format_session(_session(), {11: USERS[11]})

        self.assertIn("Thomas", text)
        self.assertIn("kalle", text)

    def test_leaves_underscores_in_names_literal_inside_the_code_block(self):
        """MarkdownV2 escapes only ` and \\ inside pre entities - escaping _ would show a backslash."""
        users = {11: User(id=11, first_name="a_b", is_bot=False), 22: USERS[22]}

        text = format_session(_session(), users)

        self.assertIn("a_b", text)
        self.assertNotIn("a\\_b", text)

    def test_escapes_backticks_in_names_so_they_cannot_break_out_of_the_code_block(self):
        users = {11: User(id=11, first_name="a`b", is_bot=False), 22: USERS[22]}

        text = format_session(_session(), users)

        self.assertIn("a\\`b", text)


if __name__ == "__main__":
    unittest.main()
