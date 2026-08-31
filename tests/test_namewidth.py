"""Table name cells must line up in Telegram's monospace font.

len() counts code points, not display columns, so CJK (2 columns each), combining marks
(0 columns) and emoji (unpredictable) all break column alignment. In-game names come
straight from CS2 and are full of exactly that.
"""

import unittest

from ongabot.utils.statistics import NAME_WIDTH, display_width, fit_name, sanitize_name


class DisplayWidthTest(unittest.TestCase):
    def test_ascii_is_one_column_per_character(self):
        self.assertEqual(display_width("ffAiSEN"), 7)

    def test_cyrillic_is_one_column_per_character(self):
        self.assertEqual(display_width("Бошка"), 5)

    def test_cjk_is_two_columns_per_character(self):
        self.assertEqual(display_width("王小明"), 6)

    def test_korean_is_two_columns_per_character(self):
        self.assertEqual(display_width("한국인"), 6)

    def test_combining_marks_add_no_width(self):
        self.assertEqual(display_width("émil"), 4)

    def test_empty_string_is_zero(self):
        self.assertEqual(display_width(""), 0)


class SanitizeNameTest(unittest.TestCase):
    def test_plain_names_are_untouched(self):
        self.assertEqual(sanitize_name("ffAiSEN"), "ffAiSEN")

    def test_removes_emoji_whose_rendered_width_is_unpredictable(self):
        self.assertEqual(sanitize_name("❤️Zayd"), "Zayd")

    def test_removes_a_zero_width_joiner_sequence(self):
        self.assertEqual(sanitize_name("a👨‍👩‍👧b"), "ab")

    def test_removes_bidi_overrides(self):
        """U+202E reorders everything after it - a spoofing vector as well as a width bug."""
        self.assertEqual(sanitize_name("abc‮def"), "abcdef")

    def test_composes_accents_rather_than_dropping_them(self):
        self.assertEqual(sanitize_name("émil"), "émil")

    def test_keeps_cjk(self):
        self.assertEqual(sanitize_name("王小明"), "王小明")

    def test_collapses_whitespace(self):
        self.assertEqual(sanitize_name("a   b"), "a b")

    def test_newlines_cannot_break_out_of_a_table_row(self):
        self.assertEqual(sanitize_name("a\nb\rc"), "a b c")

    def test_an_all_emoji_name_reduces_to_nothing(self):
        self.assertEqual(sanitize_name("❤️"), "")


class FitNameTest(unittest.TestCase):
    def _width(self, name):
        return display_width(fit_name(name))

    def test_pads_short_names_to_the_column_width(self):
        self.assertEqual(self._width("Emil"), NAME_WIDTH)

    def test_an_emoji_name_occupies_the_same_width_as_a_plain_one(self):
        """The reported bug: the heart row was shifted relative to every other row."""
        self.assertEqual(self._width("❤️"), self._width("ffAiSEN"))

    def test_a_cjk_name_occupies_the_same_width_as_a_plain_one(self):
        self.assertEqual(self._width("王小明王小"), self._width("ffAiSEN"))

    def test_a_long_cjk_name_is_truncated_to_the_column_width(self):
        self.assertEqual(self._width("王小明王小明王小明"), NAME_WIDTH)

    def test_a_long_ascii_name_is_truncated_to_the_column_width(self):
        self.assertEqual(self._width("paprikafixxxxxxxx"), NAME_WIDTH)

    def test_a_truncated_name_is_marked_with_a_dot(self):
        self.assertTrue(fit_name("paprikafixxxxxxxx").rstrip().endswith("."))

    def test_an_emptied_name_falls_back_so_the_row_is_not_blank(self):
        self.assertEqual(fit_name("❤️", fallback="#8159").strip(), "#8159")

    def test_every_name_in_a_mixed_table_lines_up(self):
        names = ["Jimmy", "Emil", "❤️", "王小明", "paprikafixxxx", "émil", "Бошка говяжья"]

        widths = {display_width(fit_name(name, fallback="?")) for name in names}

        self.assertEqual(widths, {NAME_WIDTH}, "every cell must be exactly NAME_WIDTH columns")


if __name__ == "__main__":
    unittest.main()
