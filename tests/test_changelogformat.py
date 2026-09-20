import re
import unittest
from pathlib import Path
from typing import List

from ongabot.utils.changelog import MAX_MESSAGE_CHARS
from ongabot.utils.changelogformat import (
    BULLET,
    CHANGELOG_HEADING,
    EXPANDABLE_MIN_LINES,
    NESTED_BULLET,
    render_changelog_html,
)

ONE_SECTION = """\
## [1.2.0] - 2026-05-24

### Fixed

- Big fix
"""


class RenderStructureTest(unittest.TestCase):
    """The version header stays visible; the body is what collapses."""

    def test_version_and_date_render_as_a_header_line_outside_the_blockquote(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        head = message.split("<blockquote")[0]
        self.assertIn("<b>v1.2.0</b>", head)
        self.assertIn("<i>2026-05-24</i>", head)

    def test_subsection_heading_is_rendered_inside_the_blockquote(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        body = message.split(">", 1)[1]
        self.assertIn("<i>Fixed</i>", body)
        self.assertNotIn("###", message)

    def test_bullet_marker_replaces_the_markdown_dash(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertIn("• Big fix", message)
        self.assertNotIn("- Big fix", message)

    def test_body_is_wrapped_in_a_blockquote(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertEqual(message.count("<blockquote"), 1)
        self.assertEqual(message.count("</blockquote>"), 1)

    def test_a_version_header_with_no_date_still_renders(self) -> None:
        (message,) = render_changelog_html("## [Unreleased]\n\n### Added\n\n- Thing\n")
        self.assertIn("<b>Unreleased</b>", message)
        self.assertNotIn("<i></i>", message)


class HierarchyTest(unittest.TestCase):
    """Three distinct weights, so a release and a section label never read as one blob."""

    def test_a_numeric_version_is_prefixed_with_v(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertIn("<b>v1.2.0</b>", message)

    def test_unreleased_is_not_prefixed_with_v(self) -> None:
        (message,) = render_changelog_html("## [Unreleased]\n\n### Added\n\n- Thing\n")
        self.assertIn("<b>Unreleased</b>", message)
        self.assertNotIn("vUnreleased", message)

    def test_section_labels_are_italic_not_bold(self) -> None:
        # Bold on both the version and the section made "Unreleased / Changed" one blob.
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertIn("<i>Fixed</i>", message)
        self.assertNotIn("<b>Fixed</b>", message)

    def test_the_version_stays_bold(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertIn("<b>v1.2.0</b>", message)
        self.assertNotIn("<i>v1.2.0</i>", message)


class HeadlineTest(unittest.TestCase):
    """An optional heading leads the first message and is not repeated on the rest."""

    def test_the_headline_leads_the_first_message(self) -> None:
        messages = render_changelog_html(ONE_SECTION, headline=CHANGELOG_HEADING)
        self.assertTrue(messages[0].startswith(CHANGELOG_HEADING))

    def test_the_headline_is_not_repeated_on_later_messages(self) -> None:
        raw = "\n".join(_section(f"1.{n}.0", 40) for n in range(6))
        messages = render_changelog_html(raw, headline=CHANGELOG_HEADING)
        self.assertGreater(len(messages), 1)
        for message in messages[1:]:
            self.assertNotIn(CHANGELOG_HEADING, message)

    def test_the_headline_never_pushes_a_message_over_the_limit(self) -> None:
        raw = "\n".join(_section(f"1.{n}.0", 40) for n in range(6))
        for message in render_changelog_html(raw, headline=CHANGELOG_HEADING):
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)

    def test_no_headline_is_added_when_none_is_asked_for(self) -> None:
        (message,) = render_changelog_html(ONE_SECTION)
        self.assertFalse(message.startswith(CHANGELOG_HEADING))

    def test_a_headline_with_no_content_is_still_sent(self) -> None:
        self.assertEqual(render_changelog_html("", headline=CHANGELOG_HEADING), [CHANGELOG_HEADING])


class InlineFormattingTest(unittest.TestCase):
    """Markdown emphasis becomes real entities; everything else is escaped text."""

    def _render_bullet(self, bullet: str) -> str:
        return render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n- {bullet}\n")[0]

    def test_double_asterisks_become_bold(self) -> None:
        self.assertIn("<b>CS2 match results.</b> It works", self._render_bullet("**CS2 match results.** It works"))

    def test_backticks_become_code(self) -> None:
        self.assertIn("<code>/changelog</code>", self._render_bullet("`/changelog` is nicer"))

    def test_angle_brackets_in_body_text_are_escaped(self) -> None:
        # The real 1.7.0 entry documents `/linksteam <steam64|profile URL>`; unescaped, the
        # "<steam64|profile URL>" would be read as a tag and Telegram would reject the message.
        rendered = self._render_bullet("`/linksteam <steam64|profile URL>` and `/unlinksteam`")
        self.assertIn("&lt;steam64|profile URL&gt;", rendered)
        self.assertNotIn("<steam64", rendered)

    def test_apostrophes_are_left_alone_in_body_text(self) -> None:
        # Telegram only requires <, > and & to be escaped. Escaping "'" as "&#x27;" is six
        # characters where one will do, and the changelog is full of them.
        rendered = self._render_bullet("the event's start time")
        self.assertIn("the event's start time", rendered)
        self.assertNotIn("&#x27;", rendered)

    def test_double_quotes_are_left_alone_in_body_text(self) -> None:
        rendered = self._render_bullet('posts a "CS2 results" message')
        self.assertIn('a "CS2 results" message', rendered)

    def test_ampersand_in_body_text_is_escaped(self) -> None:
        self.assertIn("this &amp; that", self._render_bullet("this & that"))

    def test_asterisks_are_not_left_in_the_output(self) -> None:
        self.assertNotIn("*", self._render_bullet("**bold** and plain"))

    def test_backticks_are_not_left_in_the_output(self) -> None:
        self.assertNotIn("`", self._render_bullet("`code` and plain"))

    def test_bold_inside_a_code_span_is_not_treated_as_markup(self) -> None:
        # Telegram forbids nesting entities inside code, so the asterisks must survive as text.
        rendered = self._render_bullet("`make **all**` runs it")
        self.assertIn("<code>make **all**</code>", rendered)


class LinkTest(unittest.TestCase):
    """Links resolve to anchors; link-reference definitions never reach the chat."""

    def _render(self, body: str) -> str:
        return render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n{body}\n")[0]

    def test_inline_link_becomes_an_anchor(self) -> None:
        rendered = self._render("- See [the docs](https://example.com/docs).")
        self.assertIn('<a href="https://example.com/docs">the docs</a>', rendered)

    def test_reference_link_resolves_against_its_definition(self) -> None:
        rendered = self._render("- Data from the [Leetify API][leetify-api].\n\n[leetify-api]: https://example.com/api")
        self.assertIn('<a href="https://example.com/api">Leetify API</a>', rendered)

    def test_link_definition_lines_are_never_emitted(self) -> None:
        rendered = self._render("- Data from the [Leetify API][leetify-api].\n\n[leetify-api]: https://example.com/api")
        self.assertNotIn("leetify-api]:", rendered)

    def test_unresolved_reference_link_degrades_to_plain_text(self) -> None:
        rendered = self._render("- Data from the [Leetify API][missing-ref].")
        self.assertIn("Leetify API", rendered)
        self.assertNotIn("missing-ref", rendered)
        self.assertNotIn("<a ", rendered)

    def test_quotes_in_a_url_are_escaped(self) -> None:
        rendered = self._render('- See [it](https://example.com/?q="x").')
        self.assertNotIn('?q="x"', rendered)
        self.assertIn("&quot;", rendered)


class BulletWrappingTest(unittest.TestCase):
    """CHANGELOG.md hard-wraps at ~80 columns; Telegram should wrap to the device instead."""

    def _render(self, body: str) -> str:
        return render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n{body}\n")[0]

    def test_continuation_lines_are_joined_into_one_bullet(self) -> None:
        rendered = self._render("- A bullet that was hard-wrapped\n  across two source lines.")
        self.assertIn("• A bullet that was hard-wrapped across two source lines.", rendered)

    def test_a_wrapped_bullet_occupies_a_single_rendered_line(self) -> None:
        rendered = self._render("- One\n  two\n  three")
        self.assertEqual(len([line for line in rendered.splitlines() if line.startswith(BULLET)]), 1)

    def test_markup_split_across_a_wrap_is_still_parsed(self) -> None:
        # The source wraps between "**Banger" and "Points**", so bold only resolves after joining.
        rendered = self._render("- New **Banger\n  Points** command.")
        self.assertIn("<b>Banger Points</b>", rendered)

    def test_nested_bullets_render_indented_with_their_own_marker(self) -> None:
        rendered = self._render("- Outer\n  - Inner one\n  - Inner two")
        self.assertIn(f"  {NESTED_BULLET} Inner one", rendered)
        self.assertIn(f"  {NESTED_BULLET} Inner two", rendered)

    def test_a_nested_bullet_does_not_get_folded_into_its_parent(self) -> None:
        rendered = self._render("- Outer\n  - Inner")
        self.assertIn(f"{BULLET} Outer", rendered)
        self.assertNotIn("Outer - Inner", rendered)

    def test_separate_bullets_stay_separate(self) -> None:
        rendered = self._render("- First\n- Second")
        self.assertEqual(len([line for line in rendered.splitlines() if line.startswith(BULLET)]), 2)


def _section(version: str, bullets: int) -> str:
    body = "\n".join(f"- Bullet number {n}" for n in range(bullets))
    return f"## [{version}] - 2026-01-01\n\n### Added\n\n{body}\n"


class ExpandableTest(unittest.TestCase):
    """Only a body long enough to be worth hiding gets the expand affordance."""

    def test_a_long_body_is_expandable(self) -> None:
        (message,) = render_changelog_html(_section("1.0.0", EXPANDABLE_MIN_LINES + 2))
        self.assertIn("<blockquote expandable>", message)

    def test_a_short_body_is_a_plain_blockquote(self) -> None:
        (message,) = render_changelog_html(_section("1.0.0", 1))
        self.assertIn("<blockquote>", message)
        self.assertNotIn("expandable", message)


class MultipleSectionsTest(unittest.TestCase):
    """/changelog 3 and a multi-release upgrade both render several sections."""

    def test_each_version_gets_its_own_header_and_blockquote(self) -> None:
        raw = _section("1.2.0", 2) + "\n" + _section("1.1.0", 2)
        (message,) = render_changelog_html(raw)
        self.assertIn("<b>v1.2.0</b>", message)
        self.assertIn("<b>v1.1.0</b>", message)
        self.assertEqual(message.count("</blockquote>"), 2)

    def test_sections_keep_their_source_order(self) -> None:
        raw = _section("1.2.0", 2) + "\n" + _section("1.1.0", 2)
        (message,) = render_changelog_html(raw)
        self.assertLess(message.index("<b>v1.2.0</b>"), message.index("<b>v1.1.0</b>"))

    def test_a_bullet_never_leaks_into_the_next_section(self) -> None:
        raw = "## [1.2.0] - 2026-01-01\n\n### Added\n\n- Newer\n\n## [1.1.0] - 2026-01-01\n\n### Added\n\n- Older\n"
        (message,) = render_changelog_html(raw)
        newer_block = message.split("<b>v1.1.0</b>")[0]
        self.assertIn("Newer", newer_block)
        self.assertNotIn("Older", newer_block)

    def test_text_with_no_version_header_renders_nothing(self) -> None:
        self.assertEqual(render_changelog_html("just some prose\n"), [])


def _tags_balanced(message: str) -> bool:
    """Every tag the renderer opens is closed in the same message, innermost first."""
    stack: List[str] = []
    for match in re.finditer(r"<(/?)(\w+)[^>]*>", message):
        closing, name = match.group(1), match.group(2)
        if closing:
            if not stack or stack.pop() != name:
                return False
        else:
            stack.append(name)
    return not stack


class ChunkingTest(unittest.TestCase):
    """A long changelog is split across messages without ever cutting a tag in half."""

    def _long_raw(self) -> str:
        # Roughly 12k characters - three messages' worth.
        return "\n".join(_section(f"1.{n}.0", 40) for n in range(6))

    def test_a_long_changelog_becomes_several_messages(self) -> None:
        messages = render_changelog_html(self._long_raw())
        self.assertGreater(len(messages), 1)

    def test_every_message_fits_telegrams_limit(self) -> None:
        for message in render_changelog_html(self._long_raw()):
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)

    def test_every_message_has_balanced_tags(self) -> None:
        for message in render_changelog_html(self._long_raw()):
            self.assertTrue(_tags_balanced(message), f"unbalanced: {message[:200]}")

    def test_no_content_is_lost_across_the_split(self) -> None:
        messages = render_changelog_html(self._long_raw())
        joined = "\n".join(messages)
        for n in range(6):
            self.assertIn(f"<b>v1.{n}.0</b>", joined)
        self.assertEqual(joined.count("Bullet number 39"), 6)

    def test_a_single_oversized_section_is_split_rather_than_dropped(self) -> None:
        messages = render_changelog_html(_section("9.9.9", 300))
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)
            self.assertTrue(_tags_balanced(message))
        self.assertIn("Bullet number 299", "\n".join(messages))

    def test_a_single_line_longer_than_a_whole_message_is_still_sent(self) -> None:
        # No line break to split on: the line itself must be cut, not dropped.
        messages = render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n- {'x' * 9000}\n")
        for message in messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)
            self.assertTrue(_tags_balanced(message))
        self.assertGreater(sum(message.count("x") for message in messages), 8000)

    def test_an_oversized_line_full_of_markup_is_split_without_breaking_a_tag(self) -> None:
        # The hard case: the cut lands inside <code>...</code> spans and &lt; entities, which
        # must be closed and reopened rather than sliced in half.
        bullet = " ".join(f"`tag{n} <x> & y`" for n in range(600))
        messages = render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n- {bullet}\n")
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)
            self.assertTrue(_tags_balanced(message), f"unbalanced: {message[-200:]}")

    def test_splitting_an_oversized_line_never_cuts_an_entity(self) -> None:
        bullet = " ".join(f"a &  b <{n}>" for n in range(600))
        messages = render_changelog_html(f"## [1.0.0] - 2026-01-01\n\n### Added\n\n- {bullet}\n")
        for message in messages:
            # A cut entity would leave a bare "&" or a truncated "&lt" with no semicolon.
            for fragment in re.findall(r"&[^;<\s]*", message):
                self.assertIn(fragment + ";", message)

    def test_a_section_that_does_not_fit_starts_a_new_message(self) -> None:
        """Sweep the boundary where a following release no longer fits beside the one before."""
        seen_split_at_section_boundary = False
        for size in range(150, 260):
            messages = render_changelog_html(_section("2.0.0", size) + "\n" + _section("1.0.0", 3))
            for message in messages:
                self.assertLessEqual(len(message), MAX_MESSAGE_CHARS, f"size={size}")
                self.assertTrue(_tags_balanced(message), f"size={size}")
            self.assertIn("Bullet number 2", messages[-1])
            if len(messages) > 1 and messages[-1].startswith("<b>v1.0.0</b>"):
                seen_split_at_section_boundary = True
        self.assertTrue(seen_split_at_section_boundary, "never exercised the section-boundary split")

    def test_a_short_changelog_stays_one_message(self) -> None:
        self.assertEqual(len(render_changelog_html(_section("1.0.0", 3))), 1)


class RealChangelogTest(unittest.TestCase):
    """The repo's own CHANGELOG.md must render and fit - it is what production sends."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = (Path(__file__).parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.messages = render_changelog_html(cls.raw)

    def test_every_release_is_rendered(self) -> None:
        versions = re.findall(r"^## \[([^\]]+)\]", self.raw, re.MULTILINE)
        joined = "\n".join(self.messages)
        for version in versions:
            prefix = "v" if version[0].isdigit() else ""
            self.assertIn(f"<b>{prefix}{version}</b>", joined)

    def test_every_message_fits_telegrams_limit(self) -> None:
        for message in self.messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)

    def test_every_message_has_balanced_tags(self) -> None:
        for message in self.messages:
            self.assertTrue(_tags_balanced(message))

    def test_no_markdown_markers_survive(self) -> None:
        # Code spans are excluded: an entry may quote "`###`" on purpose, and rendering that
        # as <code>###</code> is correct rather than a marker that survived.
        outside_code = re.sub(r"<code>.*?</code>", "", "\n".join(self.messages), flags=re.DOTALL)
        self.assertNotIn("###", outside_code)
        self.assertNotIn("**", outside_code)
        self.assertNotIn("`", outside_code)
        self.assertNotIn("](", outside_code)

    def test_only_supported_tags_are_emitted(self) -> None:
        # Telegram rejects a message containing any tag it does not know.
        supported = {"b", "i", "u", "s", "code", "pre", "a", "blockquote"}
        for message in self.messages:
            for name in re.findall(r"</?(\w+)", message):
                self.assertIn(name, supported)

    def test_the_file_preamble_is_not_included(self) -> None:
        self.assertNotIn("All notable changes", "\n".join(self.messages))

    def test_the_trailing_link_definition_block_is_not_included(self) -> None:
        self.assertNotIn("compare/v", "\n".join(self.messages))


if __name__ == "__main__":
    unittest.main()
