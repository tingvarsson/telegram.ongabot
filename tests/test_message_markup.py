"""Every message builder emits markup Telegram accepts, whatever users call themselves.

Names, poll options and patch-note text are the untrusted parts of a message: a stray '_',
'<' or '&' in any of them used to surface only live, as "Can't parse entities". Each test here
renders a builder with that input at its worst and runs the result through the checker in
tests.telegram_markup.
"""

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot import ongabot
from ongabot.cs2.format import format_session
from ongabot.cs2.patchnotesformat import render_patch_notes_html
from ongabot.cs2.steamnews import SteamNewsItem
from ongabot.utils import helper
from ongabot.utils.changelogformat import CHANGELOG_HEADING, render_changelog_html
from ongabot.utils.points import render_event_recap_message, render_leaderboard_message
from ongabot.utils.statistics import SORT_COLUMNS, render_statistics_message
from tests import message_fixtures
from tests.message_fixtures import NASTY
from tests.telegram_markup import check_html, check_markdown_v2, check_plain_text

REPO_ROOT = Path(__file__).parent.parent


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
        items = message_fixtures.steam_patch_notes()
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
        self.chat = message_fixtures.chat()
        self.latest = message_fixtures.latest_event(self.chat)

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
        for live in (False, True):
            with self.subTest(live=live):
                check_markdown_v2(format_session(message_fixtures.cs2_session(), live=live))

    def test_cs2_results_with_hostile_map_name(self):
        session = message_fixtures.cs2_session()
        hostile = replace(session, matches=[replace(match, map_name=f"de_{NASTY}") for match in session.matches])
        check_markdown_v2(format_session(hostile))


class PlainTextBuildersTest(unittest.TestCase):
    def test_help_text_fits_one_message(self):
        check_plain_text(helper.create_help_text())


if __name__ == "__main__":
    unittest.main()
