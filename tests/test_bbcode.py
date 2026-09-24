import json
import re
import unittest
from pathlib import Path
from typing import List

from ongabot.cs2.bbcode import BULLET, NESTED_BULLET, render_bbcode_to_lines

FIXTURE = Path(__file__).parent / "fixtures" / "steam_news_cs2.json"


def _tags_balanced(line: str) -> bool:
    stack: List[str] = []
    for match in re.finditer(r"<(/?)(\w+)[^>]*>", line):
        closing, name = match.group(1), match.group(2)
        if closing:
            if not stack or stack.pop() != name:
                return False
        else:
            stack.append(name)
    return not stack


class InlineTagTest(unittest.TestCase):
    def test_bold(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[b]bold[/b]"), ["<b>bold</b>"])

    def test_italic(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[i]italic[/i]"), ["<i>italic</i>"])

    def test_underline(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[u]underline[/u]"), ["<u>underline</u>"])

    def test_code(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[code]cmd --flag[/code]"), ["<code>cmd --flag</code>"])

    def test_noparse_behaves_like_code(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[noparse][b]not bold[/b][/noparse]"), ["<code>[b]not bold[/b]</code>"])

    def test_url_with_attribute(self) -> None:
        self.assertEqual(
            render_bbcode_to_lines("[url=https://example.com]the docs[/url]"),
            ['<a href="https://example.com">the docs</a>'],
        )

    def test_url_with_quoted_attribute(self) -> None:
        # Valve's current patch notes quote the attribute: [url="https://..."].
        self.assertEqual(
            render_bbcode_to_lines('[url="https://example.com/x"]Update Notes[/url]'),
            ['<a href="https://example.com/x">Update Notes</a>'],
        )

    def test_bare_url(self) -> None:
        self.assertEqual(
            render_bbcode_to_lines("[url]https://example.com[/url]"),
            ['<a href="https://example.com">https://example.com</a>'],
        )

    def test_image_is_dropped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[img]https://example.com/x.png[/img]"), [])

    def test_image_with_attributes_is_dropped(self) -> None:
        self.assertEqual(render_bbcode_to_lines('[p]A [img src="{STEAM_CLAN_IMAGE}/x.png"][/img] B[/p]'), ["A B"])

    def test_video_with_attributes_is_dropped(self) -> None:
        contents = (
            '[video webm="https://x/a.webm" mp4="https://x/a.mp4" poster="https://x/a.png" autoplay="true"][/video]'
        )
        self.assertEqual(render_bbcode_to_lines(f"[p]Before[/p]{contents}[p]After[/p]"), ["Before", "After"])

    def test_image_dropped_but_surrounding_text_kept(self) -> None:
        self.assertEqual(render_bbcode_to_lines("See: [img]https://x/y.png[/img] above"), ["See: above"])


class ParagraphTest(unittest.TestCase):
    def test_each_paragraph_is_a_line(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[p]One[/p][p]Two[/p]"), ["One", "Two"])

    def test_empty_paragraphs_are_dropped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[p]One[/p][p][/p][p]Two[/p]"), ["One", "Two"])

    def test_newlines_also_break_lines(self) -> None:
        # Older posts use plain newlines instead of [p].
        self.assertEqual(render_bbcode_to_lines("Para one\nPara two"), ["Para one", "Para two"])

    def test_blank_and_whitespace_only_lines_are_dropped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("First\n\n    \nSecond"), ["First", "Second"])

    def test_whitespace_runs_collapse(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[p]a   b[/p]"), ["a b"])


class ListTest(unittest.TestCase):
    def test_closed_bullets(self) -> None:
        contents = "[list][*][p]First[/p][/*][*][p]Second[/p][/*][/list]"
        self.assertEqual(render_bbcode_to_lines(contents), [f"{BULLET} First", f"{BULLET} Second"])

    def test_unclosed_newline_separated_bullets(self) -> None:
        contents = "[list]\n[*]First\n[*]Second\n[/list]"
        self.assertEqual(render_bbcode_to_lines(contents), [f"{BULLET} First", f"{BULLET} Second"])

    def test_olist_renders_like_list(self) -> None:
        contents = "[olist][*]One[/*][*]Two[/*][/olist]"
        self.assertEqual(render_bbcode_to_lines(contents), [f"{BULLET} One", f"{BULLET} Two"])

    def test_nested_list_uses_nested_marker(self) -> None:
        contents = "[list][*][p]Parent[/p][list][*][p]Child[/p][/*][/list][/*][*][p]Sibling[/p][/*][/list]"
        self.assertEqual(
            render_bbcode_to_lines(contents),
            [f"{BULLET} Parent", f"  {NESTED_BULLET} Child", f"{BULLET} Sibling"],
        )

    def test_bullet_with_inline_markup(self) -> None:
        contents = "[list][*][p][b]Fixed[/b]: a bug[/p][/*][/list]"
        self.assertEqual(render_bbcode_to_lines(contents), [f"{BULLET} <b>Fixed</b>: a bug"])


class HeadingTest(unittest.TestCase):
    def test_escaped_bracket_paragraph_is_a_section_heading(self) -> None:
        # Valve marks sections as a paragraph of literal "[ NAME ]", escaped as "\[ NAME ]".
        self.assertEqual(render_bbcode_to_lines(r"[p]\[ GAMEPLAY ][/p]"), ["<i>GAMEPLAY</i>"])

    def test_h_tags_are_headings(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[h1]Big[/h1]"), ["<i>Big</i>"])
        self.assertEqual(render_bbcode_to_lines("[h2]Mid[/h2]"), ["<i>Mid</i>"])
        self.assertEqual(render_bbcode_to_lines("[h3]Small[/h3]"), ["<i>Small</i>"])

    def test_a_blank_line_separates_sections_after_the_first(self) -> None:
        contents = r"[p]\[ MAPS ][/p][list][*][p]x[/p][/*][/list][p][/p][p]\[ AUDIO ][/p][list][*][p]y[/p][/*][/list]"
        self.assertEqual(
            render_bbcode_to_lines(contents),
            ["<i>MAPS</i>", f"{BULLET} x", "", "<i>AUDIO</i>", f"{BULLET} y"],
        )

    def test_escaped_brackets_elsewhere_stay_literal_and_are_not_tags(self) -> None:
        self.assertEqual(render_bbcode_to_lines(r"[p]Use \[b] for bold[/p]"), ["Use [b] for bold"])

    def test_a_paragraph_that_starts_bracketed_and_ends_in_a_tag_is_not_a_heading(self) -> None:
        contents = r"[p]\[Inferno] Fixed a boost spot, see [url=https://x]details[/url][/p]"
        self.assertEqual(
            render_bbcode_to_lines(contents),
            ['[Inferno] Fixed a boost spot, see <a href="https://x">details</a>'],
        )

    def test_a_bullet_with_no_text_does_not_leak_its_marker(self) -> None:
        contents = r"[list][*][img]a.png[/img][/*][/list][p]\[ MAPS ][/p]"
        self.assertEqual(render_bbcode_to_lines(contents), ["<i>MAPS</i>"])


class EscapingTest(unittest.TestCase):
    def test_literal_angle_brackets_are_escaped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("5 < 10"), ["5 &lt; 10"])

    def test_literal_ampersand_is_escaped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("this & that"), ["this &amp; that"])

    def test_escaping_never_opens_a_bogus_tag(self) -> None:
        rendered = render_bbcode_to_lines("</b> is not a real close tag")
        self.assertNotIn("</b>", rendered[0])
        self.assertIn("&lt;/b&gt;", rendered[0])


class UnknownAndMalformedTagTest(unittest.TestCase):
    def test_unknown_tag_is_stripped_but_text_kept(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[spoiler]secret[/spoiler]"), ["secret"])

    def test_unknown_tag_with_attribute_is_stripped(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[color=red]warning[/color]"), ["warning"])

    def test_a_line_of_only_unknown_tags_leaves_no_blank_line(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[p]One[/p][hr][/hr][p]Two[/p]"), ["One", "Two"])

    def test_unclosed_tag_does_not_raise_and_keeps_text(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[b]unclosed bold"), ["unclosed bold"])

    def test_deeply_nested_markup_does_not_raise(self) -> None:
        for line in render_bbcode_to_lines("[b][i][u]triple[/u][/i][/b]"):
            self.assertTrue(_tags_balanced(line))

    def test_stray_close_tags_do_not_underflow_list_depth(self) -> None:
        self.assertEqual(render_bbcode_to_lines("[/list][/list][list][*]x[/*][/list]"), [f"{BULLET} x"])


class RealPayloadTest(unittest.TestCase):
    """Every body in the captured GetNewsForApp payload renders cleanly."""

    @classmethod
    def setUpClass(cls) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.items = payload["appnews"]["newsitems"]

    def test_every_item_renders_to_balanced_lines_with_no_markup_left(self) -> None:
        for item in self.items:
            lines = render_bbcode_to_lines(item["contents"])
            self.assertTrue(lines, item["gid"])
            for line in lines:
                self.assertTrue(_tags_balanced(line), f"{item['gid']}: {line!r}")
                for marker in ("[p]", "[/p]", "[list]", "[*]", "[/*]", "[url", "[img", "[video", "\\["):
                    self.assertNotIn(marker, line, f"{item['gid']}: {line!r}")

    def test_only_telegram_supported_tags_are_emitted(self) -> None:
        supported = {"b", "i", "u", "code", "a"}
        for item in self.items:
            for line in render_bbcode_to_lines(item["contents"]):
                for name in re.findall(r"</?(\w+)", line):
                    self.assertIn(name, supported, f"{item['gid']}: {line!r}")

    def test_a_real_patch_has_headings_and_bullets(self) -> None:
        patch = next(i for i in self.items if i["gid"] == "1844751498219795")
        lines = render_bbcode_to_lines(patch["contents"])
        self.assertEqual(lines[0], "<i>RUSH</i>")
        self.assertTrue(lines[1].startswith(f"{BULLET} Increased the maximum countdown"))
        self.assertIn("<i>CROSSHAIR</i>", lines)
        self.assertTrue(any(line.startswith(f"  {NESTED_BULLET} ") for line in lines))


if __name__ == "__main__":
    unittest.main()
