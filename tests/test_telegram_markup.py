"""The markup checker itself: it must accept what Telegram accepts and reject what it rejects,
or the message-builder tests that lean on it prove nothing."""

import unittest

from telegram.helpers import escape_markdown

from tests.telegram_markup import (
    MARKDOWN_V2_RESERVED,
    MAX_MESSAGE_CHARS,
    MarkupError,
    check_html,
    check_markdown_v2,
    check_plain_text,
)


class CheckHtmlTest(unittest.TestCase):
    def test_accepts_supported_tags_and_returns_visible_text(self):
        text = '<b>Bold</b> <a href="https://x.test/?a=1&amp;b=2">link</a> &lt;3 &#8212;'
        self.assertEqual(check_html(text), "Bold link <3 —")

    def test_accepts_nested_formatting_and_expandable_blockquote(self):
        check_html("<b><u>Changelog</u></b>\n<blockquote expandable><i>a</i>\n<code>b</code></blockquote>")

    def test_accepts_code_inside_pre(self):
        check_html('<pre><code class="language-python">x = 1</code></pre>')

    def test_rejects_unescaped_specials(self):
        for text in ("a < b", "a > b", "fish & chips"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_html(text)

    def test_rejects_unsupported_tag_and_entity(self):
        for text in ("<div>x</div>", "<br>", "&nbsp;x"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_html(text)

    def test_rejects_unbalanced_and_crossed_tags(self):
        for text in ("<b>x", "x</b>", "<b><i>x</b></i>"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_html(text)

    def test_rejects_tags_inside_code_and_nested_blockquotes(self):
        for text in ("<code><b>x</b></code>", "<blockquote><blockquote>x</blockquote></blockquote>"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_html(text)

    def test_rejects_link_without_href(self):
        with self.assertRaises(MarkupError):
            check_html("<a>x</a>")

    def test_length_counts_visible_text_not_tags(self):
        check_html("<b>" + "x" * MAX_MESSAGE_CHARS + "</b>")
        with self.assertRaises(MarkupError):
            check_html("<b>" + "x" * (MAX_MESSAGE_CHARS + 1) + "</b>")

    def test_length_counts_utf16_units(self):
        # An emoji outside the BMP is two UTF-16 code units, which is what Telegram counts.
        with self.assertRaises(MarkupError):
            check_html("\U0001f389" * (MAX_MESSAGE_CHARS // 2 + 1))

    def test_rejects_empty_message(self):
        with self.assertRaises(MarkupError):
            check_html("<b> </b>")


class CheckMarkdownV2Test(unittest.TestCase):
    def test_accepts_escaped_reserved_characters(self):
        raw = "".join(sorted(MARKDOWN_V2_RESERVED)) + "\\"
        self.assertEqual(check_markdown_v2(escape_markdown(raw, version=2)), raw)

    def test_rejects_each_unescaped_reserved_character(self):
        for char in sorted(MARKDOWN_V2_RESERVED - set("_*~`[")):
            with self.subTest(char=char), self.assertRaises(MarkupError):
                check_markdown_v2(f"a {char} b")

    def test_accepts_entities_and_returns_visible_text(self):
        text = "*bold* _it_ __under__ ~strike~ ||spoiler|| [Alice](tg://user?id=42) `x\\`y`"
        self.assertEqual(check_markdown_v2(text), "bold it under strike spoiler Alice x`y")

    def test_accepts_nested_entities(self):
        check_markdown_v2("*__Event complete\\!__*")

    def test_accepts_pre_block_with_unescaped_reserved_characters(self):
        check_markdown_v2("```\nK-D  1.5 | (x)\n```")

    def test_accepts_link_url_with_escaped_paren(self):
        check_markdown_v2("[x](https://x.test/a_\\(b\\))")

    def test_accepts_blockquote_marker_at_line_start(self):
        check_markdown_v2(">quoted\n>more")

    def test_rejects_unclosed_or_crossed_entities(self):
        for text in ("*bold", "_it", "*a _b* c_", "`code", "```\npre", "[text", "[text]"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_markdown_v2(text)

    def test_rejects_bare_backtick_inside_pre(self):
        with self.assertRaises(MarkupError):
            check_markdown_v2("```\na ` b\n```")

    def test_rejects_backslash_escaping_nothing(self):
        for text in ("trailing \\", "\\\U0001f389"):
            with self.subTest(text=text), self.assertRaises(MarkupError):
                check_markdown_v2(text)

    def test_rejects_unterminated_link_url(self):
        with self.assertRaises(MarkupError):
            check_markdown_v2("[x](https://x.test")

    def test_rejects_over_long_message(self):
        with self.assertRaises(MarkupError):
            check_markdown_v2("x" * (MAX_MESSAGE_CHARS + 1))


class CheckPlainTextTest(unittest.TestCase):
    def test_only_length_matters(self):
        self.assertEqual(check_plain_text("<b> & *"), "<b> & *")
        with self.assertRaises(MarkupError):
            check_plain_text("x" * (MAX_MESSAGE_CHARS + 1))


if __name__ == "__main__":
    unittest.main()
