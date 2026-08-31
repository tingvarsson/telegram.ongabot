"""Table name cells must line up in Telegram's monospace font.

len() counts code points, not display columns, so CJK (2 columns each), combining marks
(0 columns) and emoji (unpredictable) all break column alignment. In-game names come
straight from CS2 and are full of exactly that.
"""

import unittest

from ongabot.utils.statistics import NAME_WIDTH, display_width, emoji_name, fit_name, sanitize_name


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

    def test_a_skin_tone_modifier_is_not_left_orphaned(self):
        """Modifiers are category Sk, not So, so stripping only So left a bare tone swatch."""
        self.assertEqual(sanitize_name("👍🏽"), "")

    def test_a_modified_emoji_name_keeps_its_base_emoji(self):
        self.assertIn("👍", fit_name("👍🏽"))


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

    def test_an_all_emoji_name_keeps_its_emoji(self):
        """Emoji-only names are the one case where an emoji is kept and assumed 2 columns."""
        self.assertIn("❤", fit_name("❤️", fallback="#8159"))

    def test_a_name_with_nothing_renderable_falls_back(self):
        self.assertEqual(fit_name("\u200d\u202e", fallback="#8159").strip(), "#8159")

    def test_every_name_in_a_mixed_table_lines_up(self):
        names = ["Jimmy", "Emil", "❤️", "王小明", "paprikafixxxx", "émil", "Бошка говяжья"]

        widths = {display_width(fit_name(name, fallback="?")) for name in names}

        self.assertEqual(widths, {NAME_WIDTH}, "every cell must be exactly NAME_WIDTH columns")


class EmojiOnlyNameTest(unittest.TestCase):
    """A name that is nothing but emoji keeps them, counted as two columns each.

    Mixed names still drop their emoji (see SanitizeNameTest) - that keeps those rows exactly
    aligned. Only a name that would otherwise vanish entirely is worth the width guess.
    """

    def test_an_emoji_counts_as_two_columns(self):
        self.assertEqual(display_width("❤️"), 2)

    def test_a_zwj_sequence_is_one_glyph_of_two_columns(self):
        self.assertEqual(display_width("👨‍👩‍👧"), 2)

    def test_a_flag_is_one_glyph_of_two_columns(self):
        self.assertEqual(display_width("🇸🇪"), 2)

    def test_a_skin_tone_modifier_does_not_add_width(self):
        self.assertEqual(display_width("👍🏽"), 2)

    def test_emoji_name_keeps_emoji_but_drops_bidi_overrides(self):
        self.assertEqual(emoji_name("❤️\u202e"), "❤️")

    def test_emoji_name_is_empty_when_there_is_nothing_to_render(self):
        self.assertEqual(emoji_name("\u200d\u202e"), "")

    def test_an_emoji_only_cell_is_the_same_width_as_a_plain_one(self):
        self.assertEqual(display_width(fit_name("❤️")), display_width(fit_name("ffAiSEN")))

    def test_a_long_emoji_name_is_truncated_to_the_column_width(self):
        self.assertEqual(display_width(fit_name("❤️❤️❤️❤️❤️❤️❤️❤️")), NAME_WIDTH)

    def test_truncation_never_splits_a_zwj_sequence(self):
        cell = fit_name("👨‍👩‍👧👨‍👩‍👧👨‍👩‍👧👨‍👩‍👧👨‍👩‍👧👨‍👩‍👧")

        self.assertEqual(display_width(cell), NAME_WIDTH)
        self.assertFalse(cell.rstrip().endswith("\u200d"), "a trailing ZWJ means a cluster was cut")

    def test_a_mixed_name_still_drops_its_emoji(self):
        self.assertEqual(fit_name("❤️Zayd").strip(), "Zayd")


if __name__ == "__main__":
    unittest.main()
