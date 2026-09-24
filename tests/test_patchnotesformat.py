import datetime
import json
import re
import unittest
from pathlib import Path
from typing import List

from ongabot.cs2.patchnotesformat import FULL_NOTES_LABEL, render_patch_notes_html
from ongabot.cs2.steamnews import SteamNewsItem
from ongabot.utils.changelog import MAX_MESSAGE_CHARS

FIXTURE = Path(__file__).parent / "fixtures" / "steam_news_cs2.json"

# 2026-09-24 12:00 local time, so the rendered date is stable whatever the machine's zone.
NOON = int(datetime.datetime(2026, 9, 24, 12, 0).timestamp())


def _item(gid: str = "1", title: str = "Counter-Strike 2 Update", contents: str = "[p]x[/p]", date: int = NOON):
    return SteamNewsItem(gid=gid, title=title, url=f"https://example.com/{gid}", contents=contents, date=date, tags=())


def _bullets(count: int) -> str:
    return "[list]" + "".join(f"[*][p]Change number {n}[/p][/*]" for n in range(count)) + "[/list]"


def _tags_balanced(message: str) -> bool:
    stack: List[str] = []
    for match in re.finditer(r"<(/?)(\w+)[^>]*>", message):
        closing, name = match.group(1), match.group(2)
        if closing:
            if not stack or stack.pop() != name:
                return False
        else:
            stack.append(name)
    return not stack


class StructureTest(unittest.TestCase):
    def test_title_and_date_are_the_visible_header(self) -> None:
        (message,) = render_patch_notes_html([_item()])
        head = message.split("<blockquote")[0]
        self.assertIn("<b>Counter-Strike 2 Update</b>", head)
        self.assertIn("<i>2026-09-24</i>", head)

    def test_body_is_inside_one_blockquote(self) -> None:
        (message,) = render_patch_notes_html([_item(contents="[p]Fixed a bug.[/p]")])
        self.assertIn("Fixed a bug.", message.split("<blockquote")[1])
        self.assertEqual(message.count("</blockquote>"), 1)

    def test_body_ends_with_a_link_to_the_full_notes(self) -> None:
        (message,) = render_patch_notes_html([_item(gid="42")])
        self.assertIn(f'<a href="https://example.com/42">{FULL_NOTES_LABEL}</a></blockquote>', message)

    def test_a_long_body_is_expandable(self) -> None:
        (message,) = render_patch_notes_html([_item(contents=_bullets(10))])
        self.assertIn("<blockquote expandable>", message)

    def test_a_short_body_is_a_plain_blockquote(self) -> None:
        (message,) = render_patch_notes_html([_item(contents="[p]One change.[/p]")])
        self.assertIn("<blockquote>", message)
        self.assertNotIn("expandable", message)

    def test_an_empty_body_still_gets_the_link(self) -> None:
        (message,) = render_patch_notes_html([_item(contents="")])
        self.assertIn(FULL_NOTES_LABEL, message)

    def test_title_is_escaped(self) -> None:
        (message,) = render_patch_notes_html([_item(title="A <b> & B")])
        self.assertIn("<b>A &lt;b&gt; &amp; B</b>", message)

    def test_nothing_to_render_is_no_messages(self) -> None:
        self.assertEqual(render_patch_notes_html([]), [])


class MultipleItemsTest(unittest.TestCase):
    def test_items_keep_the_order_given(self) -> None:
        older = _item(gid="1", title="Older", date=NOON - 86400)
        newer = _item(gid="2", title="Newer", date=NOON)
        (message,) = render_patch_notes_html([older, newer])
        self.assertLess(message.index("<b>Older</b>"), message.index("<b>Newer</b>"))

    def test_each_item_gets_its_own_blockquote(self) -> None:
        (message,) = render_patch_notes_html([_item(gid="1"), _item(gid="2")])
        self.assertEqual(message.count("</blockquote>"), 2)


class SplittingTest(unittest.TestCase):
    def test_an_oversized_patch_is_split_into_balanced_messages_within_the_limit(self) -> None:
        messages = render_patch_notes_html([_item(contents=_bullets(400))])
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)
            self.assertTrue(_tags_balanced(message))
        joined = "\n".join(messages)
        self.assertIn("Change number 399", joined)
        self.assertIn(FULL_NOTES_LABEL, messages[-1])

    def test_every_real_fixture_item_renders_within_the_limit(self) -> None:
        raw_items = json.loads(FIXTURE.read_text(encoding="utf-8"))["appnews"]["newsitems"]
        items = [
            SteamNewsItem(gid=r["gid"], title=r["title"], url=r["url"], contents=r["contents"], date=r["date"], tags=())
            for r in raw_items
        ]
        for message in render_patch_notes_html(items):
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)
            self.assertTrue(_tags_balanced(message))


if __name__ == "__main__":
    unittest.main()
