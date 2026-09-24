import re
import unittest
from typing import List
from unittest.mock import AsyncMock, MagicMock

from telegram.constants import ParseMode
from telegram.error import BadRequest

from ongabot.utils.changelog import MAX_MESSAGE_CHARS
from ongabot.utils.htmlblocks import (
    EXPANDABLE_MIN_LINES,
    open_blockquote_tag,
    pack_sections,
    send_html_with_fallback,
    to_plain_text,
)


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


class ToPlainTextTest(unittest.TestCase):
    def test_strips_tags(self) -> None:
        self.assertEqual(to_plain_text("<b>bold</b> plain"), "bold plain")

    def test_unescapes_entities(self) -> None:
        self.assertEqual(to_plain_text("a &amp; b &lt;c&gt;"), "a & b <c>")


class OpenBlockquoteTagTest(unittest.TestCase):
    def test_short_body_is_a_plain_blockquote(self) -> None:
        self.assertEqual(open_blockquote_tag(["one"]), "<blockquote>")

    def test_long_body_is_expandable(self) -> None:
        body = ["line"] * EXPANDABLE_MIN_LINES
        self.assertEqual(open_blockquote_tag(body), "<blockquote expandable>")

    def test_threshold_is_configurable(self) -> None:
        self.assertEqual(open_blockquote_tag(["one", "two"], min_lines=2), "<blockquote expandable>")


class PackSectionsTest(unittest.TestCase):
    def test_single_small_section_is_one_message(self) -> None:
        (message,) = pack_sections([("<b>H1</b>", ["line one"])])
        self.assertEqual(message, "<b>H1</b>\n<blockquote>line one</blockquote>")

    def test_two_small_sections_share_one_message(self) -> None:
        messages = pack_sections([("<b>H1</b>", ["a"]), ("<b>H2</b>", ["b"])])
        self.assertEqual(len(messages), 1)
        self.assertIn("<b>H1</b>", messages[0])
        self.assertIn("<b>H2</b>", messages[0])

    def test_two_sections_that_do_not_fit_together_get_a_message_each(self) -> None:
        # Each section alone fits comfortably under limit=200; the pair together does not.
        body = ["x" * 80]
        messages = pack_sections([("<b>H1</b>", body), ("<b>H2</b>", body)], limit=200)
        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[0].startswith("<b>H1</b>"))
        self.assertTrue(messages[1].startswith("<b>H2</b>"))

    def test_an_oversized_section_is_split_without_losing_content(self) -> None:
        body = [f"bullet {n}" for n in range(300)]
        messages = pack_sections([("<b>H1</b>", body)], limit=200)
        self.assertGreater(len(messages), 1)
        joined = "\n".join(messages)
        for n in range(300):
            self.assertIn(f"bullet {n}", joined)
        for message in messages:
            self.assertLessEqual(len(message), 200)
            self.assertTrue(_tags_balanced(message), f"unbalanced: {message[:80]!r}")

    def test_a_single_line_longer_than_the_limit_is_hard_split_without_cutting_a_tag(self) -> None:
        line = "<code>" + "y" * 500 + "</code>"
        messages = pack_sections([("<b>H1</b>", [line])], limit=100)
        self.assertGreater(len(messages), 1)
        for message in messages:
            self.assertLessEqual(len(message), 100)
            self.assertTrue(_tags_balanced(message), f"unbalanced: {message!r}")
        self.assertEqual("".join(messages).count("y"), 500)

    def test_respects_max_message_chars_default(self) -> None:
        body = [f"bullet {n}" for n in range(2000)]
        messages = pack_sections([("<b>H1</b>", body)])
        for message in messages:
            self.assertLessEqual(len(message), MAX_MESSAGE_CHARS)


class SendHtmlWithFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_as_html_on_success(self) -> None:
        bot = AsyncMock()
        await send_html_with_fallback(bot, 123, "<b>hi</b>")
        bot.send_message.assert_awaited_once()
        _args, kwargs = bot.send_message.call_args
        self.assertEqual(kwargs["chat_id"], 123)
        self.assertEqual(kwargs["text"], "<b>hi</b>")
        self.assertEqual(kwargs["parse_mode"], ParseMode.HTML)

    async def test_falls_back_to_plain_text_on_bad_request(self) -> None:
        bot = MagicMock()
        bot.send_message = AsyncMock(side_effect=[BadRequest("bad entity"), None])
        await send_html_with_fallback(bot, 123, "<b>hi</b>")
        self.assertEqual(bot.send_message.await_count, 2)
        second_kwargs = bot.send_message.call_args_list[1].kwargs
        self.assertEqual(second_kwargs["text"], "hi")
        self.assertNotIn("parse_mode", second_kwargs)


if __name__ == "__main__":
    unittest.main()
