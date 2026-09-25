"""Keeping code-block tables readable on a phone held upright.

Telegram's Android app draws a code block in a large font until the block has enough full-width
rows, then switches to a smaller one. Measured live with a dev bot (2026-09-25): in portrait the
large font fits 28 columns and the small one 34, and the switch happens at 7 rows wider than 28
columns - short rows, like a "--" team divider, don't count. So a table 29-34 columns wide with
fewer than 7 such rows wraps every row.

pad_for_phone tops a table like that up to 7 wide rows with rows of U+2800 (BRAILLE PATTERN
BLANK) as wide as the table: invisible, and not whitespace, so no client trims the row away.
Tried live and rejected: no-break spaces broke the code block in the desktop client, rows of
dots looked noisy, and short or empty rows don't trigger the switch at all.
"""

import re
from typing import List

from .statistics import display_width

LARGE_FONT_COLUMNS = 28
SMALL_FONT_COLUMNS = 34
SMALL_FONT_MIN_ROWS = 7
PAD_CHAR = "\u2800"  # BRAILLE PATTERN BLANK

_MARKDOWN_ESCAPE_RE = re.compile(r"\\(.)")


def visible_width(line: str, escaped: bool = False) -> int:
    """Monospace columns a table row takes; escaped rows are measured without their backslashes.

    PAD_CHAR counts one column: display_width would take it for an emoji (it is a Unicode
    symbol), but the padding rows fit at the table's own width in the live test.
    """
    text = _MARKDOWN_ESCAPE_RE.sub(r"\1", line) if escaped else line
    return display_width(text.replace(PAD_CHAR, " "))


def pad_for_phone(lines: List[str], escaped: bool = False) -> List[str]:
    """Return lines, plus invisible full-width rows if the table needs them to fit a phone.

    Nothing is added to a table that fits the large font, or already has enough wide rows.
    escaped says the rows are already MarkdownV2-escaped (their backslashes take no column).
    """
    widths = [visible_width(line, escaped) for line in lines]
    widest = max(widths, default=0)
    if widest <= LARGE_FONT_COLUMNS:
        return lines
    wide_rows = sum(width > LARGE_FONT_COLUMNS for width in widths)
    missing = max(0, SMALL_FONT_MIN_ROWS - wide_rows)
    return lines + [PAD_CHAR * widest] * missing
