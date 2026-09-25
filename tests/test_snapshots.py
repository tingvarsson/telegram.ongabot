"""The text of every bot message, pinned in tests/snapshots/ so a change to one is a PR diff.

Each snapshot is the *visible* text a chat shows, with markup already applied, so the diff reads
like the message and not like escaped MarkdownV2. Whether the markup itself is valid is
test_message_markup's job. After an intended change, run `make snapshots` to rewrite the files,
then review the diff like any other code change.

The width test guards the other thing that only ever showed up on a phone: a code-block table
wider than a phone screen wraps every row and becomes unreadable.
"""

import difflib
import os
import re
import time
import unittest
from pathlib import Path
from typing import Callable, Dict, List, Tuple
from unittest.mock import patch

from ongabot.cs2.format import format_session
from ongabot.cs2.patchnotesformat import render_patch_notes_html
from ongabot.utils import helper
from ongabot.utils.changelogformat import CHANGELOG_HEADING, render_changelog_html
from ongabot.utils.points import render_event_recap_message, render_leaderboard_message
from ongabot.utils.statistics import display_width, render_statistics_message
from tests import message_fixtures
from tests.telegram_markup import check_html, check_markdown_v2, check_plain_text

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_SNAPSHOTS") == "1"
MESSAGE_SEPARATOR = "\n\n---- next message ----\n\n"

# Some renders show dates in the server's local time on purpose (a patch note shows the date the
# group saw it), so the snapshots pin one zone. Otherwise a UTC CI runner renders the day before.
SNAPSHOT_TZ = "Europe/Stockholm"

# Monospace columns a code-block line may take before it wraps on a phone in portrait: the
# widest tables confirmed to fit (a CS2 match scoreboard, the event recap). 35 is known to wrap.
PHONE_CODE_COLUMNS = 29

# Code blocks allowed past the phone width, keyed by (render name, block index). Each is pinned
# at its width today, so it cannot get any wider unnoticed.
WIDE_CODE_BLOCKS: Dict[Tuple[str, int], int] = {
    # /statistics is the one deliberate exception: a wide tap-to-sort table read sideways.
    ("statistics", 0): 67,
    ("statistics", 1): 67,
    # The CS2 session summary wraps on a phone; pinned until it is narrowed.
    ("cs2_results", 0): 35,
    ("cs2_results_live", 0): 35,
}

# Fixed, so the snapshot changes when the renderer does and not when CHANGELOG.md grows.
SAMPLE_CHANGELOG = """## [1.4.0] - 2026-09-20

### Added

- `/cs2patches on` posts CS2 patch notes in the chat as Valve releases them.

### Fixed

- `/statistics` no longer wraps on narrow phones.

## [1.3.0] - 2026-09-01

### Changed

- **Banger Points** recap after every event, see [the rules](https://example.com/rules).
"""

_CODE_BLOCK_RE = re.compile(r"```\n?(.*?)```", re.DOTALL)
_MARKDOWN_ESCAPE_RE = re.compile(r"\\(.)")

# name -> (checker that returns the visible text, renderer returning the raw messages)
Render = Tuple[Callable[[str], str], Callable[[], List[str]]]


def _poll_status(completed: bool) -> List[str]:
    event = message_fixtures.latest_event(message_fixtures.chat())
    event.completed = completed
    return [event._create_status_message_text(chat_member_count=9)]


def _event_recap() -> List[str]:
    chat = message_fixtures.chat()
    return [render_event_recap_message(chat, message_fixtures.latest_event(chat))]


def _help() -> List[str]:
    # The help text ends with the version, which every release bumps.
    with patch.object(helper, "__version__", "1.2.3"):
        return [helper.create_help_text()]


RENDERS: Dict[str, Render] = {
    "poll_status_open": (check_markdown_v2, lambda: _poll_status(completed=False)),
    "poll_status_complete": (check_markdown_v2, lambda: _poll_status(completed=True)),
    "statistics": (check_markdown_v2, lambda: [render_statistics_message(message_fixtures.chat())[0]]),
    "leaderboard": (check_markdown_v2, lambda: [render_leaderboard_message(message_fixtures.chat())]),
    "event_recap": (check_markdown_v2, _event_recap),
    "cs2_results": (check_markdown_v2, lambda: [format_session(message_fixtures.cs2_session())]),
    "cs2_results_live": (check_markdown_v2, lambda: [format_session(message_fixtures.cs2_session(), live=True)]),
    "changelog": (check_html, lambda: render_changelog_html(SAMPLE_CHANGELOG, headline=CHANGELOG_HEADING)),
    "patch_note": (check_html, lambda: render_patch_notes_html(message_fixtures.steam_patch_notes()[:1])),
    "help": (check_plain_text, _help),
}


def visible_text(name: str) -> str:
    """What a chat shows for one render: every message's visible text, in order."""
    check, render = RENDERS[name]
    return MESSAGE_SEPARATOR.join(check(message) for message in render()) + "\n"


def code_blocks(markdown_v2: str) -> List[List[str]]:
    """The lines of each ``` block in a MarkdownV2 message, unescaped."""
    return [_MARKDOWN_ESCAPE_RE.sub(r"\1", block).splitlines() for block in _CODE_BLOCK_RE.findall(markdown_v2)]


_saved_tz = None


def setUpModule():  # pylint: disable=invalid-name  # unittest's hook name
    global _saved_tz  # pylint: disable=global-statement
    _saved_tz = os.environ.get("TZ")
    os.environ["TZ"] = SNAPSHOT_TZ
    time.tzset()


def tearDownModule():  # pylint: disable=invalid-name  # unittest's hook name
    if _saved_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = _saved_tz
    time.tzset()


class SnapshotTest(unittest.TestCase):
    maxDiff = None

    def test_every_message_matches_its_snapshot(self):
        for name in RENDERS:
            with self.subTest(message=name):
                self._check_snapshot(name, visible_text(name))

    def test_no_stale_snapshot_files(self):
        on_disk = {path.stem for path in SNAPSHOT_DIR.glob("*.txt")}
        self.assertEqual(on_disk - set(RENDERS), set(), "snapshot files no render produces - delete them")

    def _check_snapshot(self, name: str, actual: str) -> None:
        path = SNAPSHOT_DIR / f"{name}.txt"
        if UPDATE_SNAPSHOTS:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            path.write_text(actual, encoding="utf-8")
            return
        if not path.exists():
            self.fail(f"no snapshot {path.name} yet - run `make snapshots` and review it")
        expected = path.read_text(encoding="utf-8")
        if actual != expected:
            diff = difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"snapshots/{path.name}",
                tofile="rendered now",
            )
            self.fail(f"{name} changed - if intended, run `make snapshots`:\n{''.join(diff)}")


class PhoneWidthTest(unittest.TestCase):
    def test_code_blocks_fit_a_phone(self):
        for name, (check, render) in RENDERS.items():
            if check is not check_markdown_v2:
                continue
            blocks = [block for message in render() for block in code_blocks(message)]
            for index, block in enumerate(blocks):
                limit = WIDE_CODE_BLOCKS.get((name, index), PHONE_CODE_COLUMNS)
                widest = max(block, key=display_width)
                with self.subTest(message=name, block=index):
                    self.assertLessEqual(display_width(widest), limit, f"too wide for a phone: {widest!r}")

    def test_wide_exceptions_still_exist(self):
        # An exception whose table is gone or renumbered would silently gate the wrong block.
        for name, index in WIDE_CODE_BLOCKS:
            _, render = RENDERS[name]
            blocks = [block for message in render() for block in code_blocks(message)]
            self.assertLess(index, len(blocks), f"{name} has no code block {index}")

    def test_code_blocks_are_unescaped(self):
        text = "*t*\n```\nK\\-D  1\\.5\n```\nmid\n```\nx\\`y\n```"
        self.assertEqual(code_blocks(text), [["K-D  1.5"], ["x`y"]])


if __name__ == "__main__":
    unittest.main()
