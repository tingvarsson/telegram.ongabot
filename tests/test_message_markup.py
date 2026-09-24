"""Every message builder emits markup Telegram accepts, whatever users call themselves.

Names, poll options and patch-note text are the untrusted parts of a message: a stray '_',
'<' or '&' in any of them used to surface only live, as "Can't parse entities". Each test here
renders a builder with that input at its worst and runs the result through the checker in
tests.telegram_markup.
"""

import json
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import User

from ongabot import ongabot
from ongabot.chat import Chat
from ongabot.cs2.format import format_session
from ongabot.cs2.patchnotesformat import render_patch_notes_html
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine
from ongabot.cs2.steamnews import SteamNewsItem
from ongabot.event import Event
from ongabot.eventdata import EventData
from ongabot.utils import helper
from ongabot.utils.changelogformat import CHANGELOG_HEADING, render_changelog_html
from ongabot.utils.points import render_event_recap_message, render_leaderboard_message
from ongabot.utils.statistics import MAYBE_TEXT, NO_OP_TEXT, SORT_COLUMNS, render_statistics_message
from tests.telegram_markup import check_html, check_markdown_v2, check_plain_text

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

# Every character MarkdownV2 reserves, every one HTML needs escaped, a backslash, and text
# that is wider in UTF-16 than it looks.
NASTY = '_*[]()~`>#+-=|{}.!\\ <b>&amp; "q" \U0001f389'
SLOTS = ["18.30", "19.10", "19.50"]
FIRST_EVENT = date(2026, 9, 2)


def _users() -> List[User]:
    return [
        User(id=1, first_name=NASTY, is_bot=False),
        User(id=2, first_name="Anna", last_name="<i>*_", is_bot=False),
        User(id=3, first_name="Émile ß", is_bot=False),
    ]


def _event(event_date: date, users: List[User], picks: List[tuple]) -> Event:
    """A completed event whose poll offers SLOTS plus the two joke options."""
    texts = SLOTS + [NO_OP_TEXT, MAYBE_TEXT]
    poll = MagicMock()
    poll.id = f"poll-{event_date}"
    poll.total_voter_count = len(users)
    poll.options = [MagicMock(text=text, voter_count=sum(i in pick for pick in picks)) for i, text in enumerate(texts)]
    event = Event(chat_id=42, poll=poll, data=EventData(event_date, time(18, 30), len(SLOTS)))
    for user, pick in zip(users, picks):
        answer = MagicMock()
        answer.option_ids = pick
        event.poll_answers[user] = answer
    event.first_answer = users[0]
    event.user_played_streaks = {user.id: 3 for user in users}
    event.completed = True
    return event


def _chat() -> Chat:
    """Three weeks of events with every kind of answer: slots, No-op, Maybe Baby, retracted."""
    users = _users()
    chat = Chat(42)
    weekly_picks = [
        [(0, 1), (0,), (3,)],
        [(0, 1, 2), (4,), (1,)],
        [(2,), (0, 2), ()],
    ]
    for week, picks in enumerate(weekly_picks):
        event = _event(FIRST_EVENT + timedelta(weeks=week), users, picks)
        chat.events[event.event_date] = event
    return chat


class HtmlBuildersTest(unittest.TestCase):
    def test_whole_real_changelog_renders_valid_html(self):
        raw = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        messages = render_changelog_html(raw, headline=CHANGELOG_HEADING)
        self.assertGreater(len(messages), 1, "the full changelog should need several messages")
        for message in messages:
            check_html(message)

    def test_changelog_with_hostile_text_renders_valid_html(self):
        raw = f"## [1.2.3] - 2026-09-24\n\n### Added\n\n- `/cs2` {NASTY} **{NASTY}** [x]({NASTY})\n"
        for message in render_changelog_html(raw, headline=CHANGELOG_HEADING):
            check_html(message)

    def test_real_patch_notes_render_valid_html(self):
        payload = json.loads((FIXTURES / "steam_news_cs2.json").read_text(encoding="utf-8"))
        items = [
            SteamNewsItem(
                gid=str(raw["gid"]),
                title=raw["title"],
                url=raw["url"],
                contents=raw.get("contents") or "",
                date=int(raw["date"]),
                tags=tuple(raw.get("tags") or []),
            )
            for raw in payload["appnews"]["newsitems"]
        ]
        for message in render_patch_notes_html(items):
            check_html(message)

    def test_hostile_patch_note_renders_valid_html(self):
        item = SteamNewsItem(
            gid="1",
            title=NASTY,
            url=f"https://store.steampowered.com/news/?q={NASTY}",
            contents=f"[p]{NASTY}[/p][list][*]{NASTY}[/list][url={NASTY}]{NASTY}[/url]",
            date=1_790_000_000,
            tags=("patchnotes",),
        )
        for message in render_patch_notes_html([item]):
            check_html(message)


class VersionAnnouncementTest(unittest.IsolatedAsyncioTestCase):
    async def test_announcement_of_the_whole_changelog_is_valid_html(self):
        bot = AsyncMock()
        bot_data = MagicMock(authorized_chats={42})
        delta = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        with patch("ongabot.ongabot.get_changelog_delta", return_value=delta):
            await ongabot._announce_new_version(bot, bot_data, "0.1.0", "9.9.9<&>")

        self.assertGreater(bot.send_message.call_count, 1)
        for call in bot.send_message.call_args_list:
            check_html(call.kwargs["text"])


class MarkdownV2BuildersTest(unittest.TestCase):
    def setUp(self):
        self.chat = _chat()
        self.latest = max(self.chat.events.values(), key=lambda event: event.event_date)

    def test_poll_status_message(self):
        for completed in (False, True):
            with self.subTest(completed=completed):
                self.latest.completed = completed
                check_markdown_v2(self.latest._create_status_message_text(chat_member_count=9))

    def test_statistics_for_every_sort(self):
        for column in SORT_COLUMNS:
            with self.subTest(sort_by=column.key):
                text, _ = render_statistics_message(self.chat, sort_by=column.key)
                check_markdown_v2(text)

    def test_leaderboard(self):
        check_markdown_v2(render_leaderboard_message(self.chat))

    def test_event_recap(self):
        for event in self.chat.events.values():
            with self.subTest(event_date=event.event_date):
                check_markdown_v2(render_event_recap_message(self.chat, event))

    def test_cs2_results(self):
        def player(index, user_id, name, team):
            return PlayerLine(
                user_id=user_id,
                steam64_id=f"7656119800000{index:04d}",
                name=name,
                total_kills=21,
                total_deaths=14,
                kd_ratio=1.5,
                mvps=3,
                team_number=team,
                total_assists=5,
                adr=88.4,
                multi5k=1,
                total_damage=1326,
                rounds_count=15,
            )

        players = (player(1, 1, NASTY, 2), player(2, 2, "<i>*_", 2), player(3, None, NASTY, 3), player(4, None, "`", 3))
        match = Cs2Match(
            id="2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b",
            map_name=f"de_{NASTY}",
            finished_at=datetime(2026, 9, 2, 21, 2),
            score=(13, 7),
            our_team=2,
            players=players,
        )
        for live in (False, True):
            with self.subTest(live=live):
                check_markdown_v2(format_session(Cs2Session(FIRST_EVENT, [match, match]), live=live))


class PlainTextBuildersTest(unittest.TestCase):
    def test_help_text_fits_one_message(self):
        check_plain_text(helper.create_help_text())


if __name__ == "__main__":
    unittest.main()
