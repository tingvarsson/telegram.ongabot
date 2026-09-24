"""Convert Steam's BBCode patch-note markup into Telegram HTML lines.

Not a general BBCode engine. It covers what CS2 posts on Steam actually contain (checked
against a captured GetNewsForApp payload, tests/fixtures/steam_news_cs2.json):

* Current patch notes are one long line of block tags: [p]...[/p] paragraphs, and
  [list][*][p]...[/p][/*][/list] bullets, lists nesting inside bullets.
* Sections are headed by a paragraph of literal brackets, escaped as "\\[ GAMEPLAY ]".
* Older posts separate paragraphs with plain newlines and leave [*] unclosed.
* Inline: [url=...] (attribute sometimes quoted), [url], [img], and in principle
  [b]/[i]/[u]/[code]/[noparse] and [h1]-[h3].

Anything else - an unknown tag, or a malformed/unclosed one - degrades to its escaped inner
text rather than raising or dropping content, so a Valve markup change never breaks the sweep.

Output is one HTML string per displayed line, each tag-balanced on its own: the contract
utils.htmlblocks.pack_sections needs to split a long body between lines safely.
"""

import html
import logging
import re
from typing import List, Optional

_logger = logging.getLogger(__name__)

BULLET = "•"
NESTED_BULLET = "◦"

# "\[" and "\]" are BBCode escapes for literal brackets. They are swapped for private-use
# characters before any parsing, so an escaped "[b]" can never be read as a tag, and swapped
# back to real brackets on the way out.
_ESC_OPEN = ""
_ESC_CLOSE = ""

# Tags that end the line being built. A plain newline does too, for older posts.
_BLOCK_RE = re.compile(r"\[(/?)(p|\*|list|olist|h[1-3])\]|\n", re.IGNORECASE)

# A paragraph that is nothing but "[ NAME ]" (escaped open bracket; Valve leaves the close
# bracket unescaped) is a section heading.
_BRACKET_HEADING_RE = re.compile(f"^{_ESC_OPEN}\\s*(.+?)\\s*[\\]{_ESC_CLOSE}]$")

# Not feasible to show inside a Telegram blockquote, and the image rarely matters to the
# patch-note text - dropped before whitespace is collapsed, so no double space is left behind.
_IMG_RE = re.compile(r"\[img\].*?\[/img\]", re.IGNORECASE | re.DOTALL)

# One pass over a line's inline markup. [code]/[noparse] come first in the alternation so
# markup inside them stays literal text, as in utils.changelogformat: Telegram forbids nesting
# entities inside <code>.
_INLINE_RE = re.compile(
    r"\[(?:code|noparse)\](?P<code>.*?)\[/(?:code|noparse)\]"
    r"|\[url=(?P<url_attr>[^\]]+)\](?P<url_text>.*?)\[/url\]"
    r"|\[url\](?P<bare_url>[^\[]+)\[/url\]"
    r"|\[b\](?P<bold>.*?)\[/b\]"
    r"|\[i\](?P<italic>.*?)\[/i\]"
    r"|\[u\](?P<underline>.*?)\[/u\]",
    re.IGNORECASE | re.DOTALL,
)

# Whatever "[tag]", "[/tag]" or "[tag=attr]" is left after the pass above: a tag this module
# does not know, or a known one _INLINE_RE could not pair (e.g. unclosed). Stripped rather
# than escaped, so a malformed post reads as its text rather than as raw markup.
_UNKNOWN_TAG_RE = re.compile(r"\[/?[a-zA-Z][a-zA-Z0-9_]*(?:=[^\]]*)?\]")


def _escape(text: str) -> str:
    """Escape text content for Telegram HTML - only '<', '>' and '&' need it."""
    return html.escape(text, quote=False)


def _render_plain(text: str) -> str:
    """Escape a run of plain text, first stripping any unrecognised or unpaired [tag]."""
    stripped, count = _UNKNOWN_TAG_RE.subn("", text)
    if count:
        _logger.debug("Stripped %d unrecognised BBCode tag(s) from patch-note text", count)
    return _escape(stripped)


def _render_inline(text: str) -> str:
    """Convert one line's inline BBCode to Telegram HTML, escaping everything else."""
    out: List[str] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        start = match.start()
        out.append(_render_plain(text[pos:start]))
        pos = match.end()

        if match.group("code") is not None:
            out.append(f"<code>{_escape(match.group('code'))}</code>")
        elif match.group("url_attr") is not None:
            url = html.escape(match.group("url_attr").strip().strip("\"'"), quote=True)
            out.append(f'<a href="{url}">{_render_inline(match.group("url_text"))}</a>')
        elif match.group("bare_url") is not None:
            url = match.group("bare_url").strip()
            out.append(f'<a href="{html.escape(url, quote=True)}">{_escape(url)}</a>')
        elif match.group("bold") is not None:
            out.append(f"<b>{_render_inline(match.group('bold'))}</b>")
        elif match.group("italic") is not None:
            out.append(f"<i>{_render_inline(match.group('italic'))}</i>")
        else:
            out.append(f"<u>{_render_inline(match.group('underline'))}</u>")

    out.append(_render_plain(text[pos:]))
    return "".join(out)


def _unescape_brackets(text: str) -> str:
    return text.replace(_ESC_OPEN, "[").replace(_ESC_CLOSE, "]")


class _LineBuilder:
    """Accumulates the text between block tags and emits it as rendered lines."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.list_depth = 0
        self.in_heading = False
        self._buffer = ""
        self._bullet_prefix: Optional[str] = None  # set by [*], consumed by its first line

    def add(self, text: str) -> None:
        """Append raw text (inline markup included) to the line being built."""
        self._buffer += text

    def start_bullet(self) -> None:
        """Mark the next emitted line as a bullet at the current list depth."""
        depth = max(self.list_depth, 1)
        self._bullet_prefix = f"{BULLET} " if depth == 1 else f"{'  ' * (depth - 1)}{NESTED_BULLET} "

    def flush(self) -> None:
        """Emit the buffered text as one line, if there is any."""
        raw = " ".join(_IMG_RE.sub("", self._buffer).split())
        self._buffer = ""
        if not raw:
            return  # nothing to show; a pending bullet prefix waits for its text

        heading: Optional[str] = None
        if self._bullet_prefix is None:
            match = _BRACKET_HEADING_RE.match(raw)
            heading = match.group(1) if match else (raw if self.in_heading else None)

        if heading is not None:
            rendered = _unescape_brackets(_render_inline(heading))
            if rendered:
                # A blank line before every section after the first, as changelogformat
                # separates "Added" from "Fixed", so sections read as separate groups.
                if self.lines and self.lines[-1]:
                    self.lines.append("")
                self.lines.append(f"<i>{rendered}</i>")
            return

        rendered = _unescape_brackets(_render_inline(raw))
        if not rendered:
            return
        if self._bullet_prefix is not None:
            rendered = self._bullet_prefix + rendered
            self._bullet_prefix = None
        self.lines.append(rendered)


def render_bbcode_to_lines(contents: str) -> List[str]:
    """Convert one Steam news item's BBCode body into tag-balanced HTML lines.

    Paragraphs and bullets each become a line; [list] nesting picks the bullet marker.
    Section headings - "[ NAME ]" paragraphs and [h1]-[h3] - become italic lines, the same
    treatment utils.changelogformat gives a "###" subsection. Blank lines are dropped.
    """
    text = contents.replace("\r\n", "\n").replace("\\[", _ESC_OPEN).replace("\\]", _ESC_CLOSE)
    builder = _LineBuilder()
    pos = 0
    for match in _BLOCK_RE.finditer(text):
        start = match.start()
        builder.add(text[pos:start])
        pos = match.end()
        builder.flush()
        if match.group(0) == "\n":
            continue

        closing, name = bool(match.group(1)), match.group(2).lower()
        if name in ("list", "olist"):
            # Clamped: a stray [/list] in a malformed post must not push later lists negative.
            builder.list_depth = max(builder.list_depth - 1, 0) if closing else builder.list_depth + 1
        elif name == "*":
            if not closing:
                builder.start_bullet()
        elif name != "p":
            builder.in_heading = not closing

    builder.add(text[pos:])
    builder.flush()
    return builder.lines
