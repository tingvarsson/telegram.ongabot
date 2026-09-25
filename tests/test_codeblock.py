import unittest

from ongabot.utils.codeblock import (
    LARGE_FONT_COLUMNS,
    PAD_CHAR,
    SMALL_FONT_MIN_ROWS,
    pad_for_phone,
    visible_width,
)


def _row(width: int) -> str:
    return "x" * width


class PadForPhoneTest(unittest.TestCase):
    def test_a_table_that_fits_the_large_font_is_left_alone(self):
        lines = [_row(LARGE_FONT_COLUMNS)] * 3
        self.assertEqual(pad_for_phone(lines), lines)

    def test_a_short_wide_table_is_topped_up_to_the_small_font_row_count(self):
        lines = [_row(34)] * 4

        padded = pad_for_phone(lines)

        self.assertEqual(padded[:4], lines)
        self.assertEqual(padded[4:], [PAD_CHAR * 34] * (SMALL_FONT_MIN_ROWS - 4))

    def test_padding_rows_are_as_wide_as_the_widest_row(self):
        padded = pad_for_phone([_row(30), _row(31)])
        self.assertEqual({visible_width(line) for line in padded[2:]}, {31})

    def test_short_rows_do_not_count_towards_the_row_count(self):
        # A "--" team divider is too short for Telegram to count it.
        lines = [_row(29)] * 5 + ["--"] + [_row(29)] * 1

        padded = pad_for_phone(lines)

        self.assertEqual(len(padded) - len(lines), 1)

    def test_a_table_with_enough_wide_rows_is_left_alone(self):
        lines = [_row(34)] * SMALL_FONT_MIN_ROWS
        self.assertEqual(pad_for_phone(lines), lines)

    def test_escaped_rows_are_measured_without_their_backslashes(self):
        # 28 visible columns, 30 characters: fits the large font, so no padding.
        lines = ["\\`" + "x" * 26 + "\\\\"] * 3
        self.assertEqual(pad_for_phone(lines, escaped=True), lines)
        self.assertNotEqual(pad_for_phone(lines), lines)

    def test_an_empty_table_is_left_alone(self):
        self.assertEqual(pad_for_phone([]), [])


class VisibleWidthTest(unittest.TestCase):
    def test_padding_counts_one_column_per_character(self):
        self.assertEqual(visible_width(PAD_CHAR * 34), 34)


if __name__ == "__main__":
    unittest.main()
