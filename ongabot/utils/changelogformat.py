"""Render CHANGELOG.md sections into the Telegram HTML ONGAbot posts.

Keeps utils.changelog as the pure source-slicing module; this one is purely presentation.
The "header + expandable blockquote + split without cutting a tag in half" mechanics are
generic, not changelog-specific, and live in utils.htmlblocks - this module builds on that
rather than duplicating it.
"""

import html
import logging
import re
from typing import Dict, List, Tuple

from utils.changelog import MAX_MESSAGE_CHARS
from utils.htmlblocks import pack_sections

_logger = logging.getLogger(__name__)

# "## [1.2.0] - 2026-05-24" or "## [Unreleased]"
_VERSION_HEADER_RE = re.compile(r"^## \[([^\]]+)\](?:\s*-\s*(\S+))?\s*$")

# "### Added"
_SUBSECTION_RE = re.compile(r"^###\s+(.*\S)\s*$")

# "- text", capturing indent so nested bullets can be told apart.
_BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")

# "[leetify-api]: https://..." - a link-reference definition. These appear both mid-file
# (right after the section that uses them) and as the trailing block of the whole file.
_LINK_DEF_RE = re.compile(r"^\[([^\]]+)\]:\s+(\S+)\s*$")

# One pass over a line's inline markup. Code spans come first in the alternation so that
# markup inside them is left as literal text: Telegram forbids nesting entities in code.
_INLINE_RE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[(?P<link_text>[^\]]+)\]\((?P<url>[^)]+)\)"
    r"|\[(?P<ref_text>[^\]]+)\]\[(?P<ref>[^\]]+)\]"
    r"|\*\*(?P<bold>.+?)\*\*"
)

BULLET = "•"
NESTED_BULLET = "◦"

# Bullets sit one step in from their category label, so the label reads as the thing they
# hang off rather than as just another line. Telegram's body font is proportional, so this
# is a visual nudge, not column alignment - and a wrapped bullet still returns to the margin.
INDENT = "  "

# Three weights, so a release and a section label never read as one blob: bold+underline for
# the message heading (as cs2.format and utils.points title their messages), bold for the
# release, italic for "Added"/"Fixed" inside the quote.
CHANGELOG_HEADING = "<b><u>Changelog</u></b>"


def _escape(text: str) -> str:
    """Escape text content for Telegram HTML.

    Only '<', '>' and '&' need escaping in content - quotes matter inside an attribute value
    and nowhere else. html.escape's default would turn every apostrophe into "&#x27;", six
    characters where one will do, and a changelog is full of them.
    """
    return html.escape(text, quote=False)


def _render_inline(text: str, link_defs: Dict[str, str]) -> str:
    """Convert one line's Markdown markup to Telegram HTML, escaping everything else.

    Escaping is done per run of plain text rather than over the whole line, because the tags
    this emits must survive. Anything not recognised as markup is escaped, so a stray '<' in
    body text - `/linksteam <steam64>` is a real case - can never open a bogus tag.
    """
    out: List[str] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        start = match.start()
        out.append(_escape(text[pos:start]))
        pos = match.end()

        if match.group("code") is not None:
            out.append(f"<code>{_escape(match.group('code'))}</code>")
        elif match.group("link_text") is not None:
            url = html.escape(match.group("url"), quote=True)
            out.append(f'<a href="{url}">{_escape(match.group("link_text"))}</a>')
        elif match.group("ref_text") is not None:
            label = _escape(match.group("ref_text"))
            url = link_defs.get(match.group("ref").lower())
            # An unresolved reference is a changelog typo; show the text rather than the
            # raw "[text][ref]" markup, which is exactly the noise this module removes.
            out.append(f'<a href="{html.escape(url, quote=True)}">{label}</a>' if url else label)
        else:
            out.append(f"<b>{_escape(match.group('bold'))}</b>")

    out.append(_escape(text[pos:]))
    return "".join(out)


def _collect_link_defs(raw: str) -> Dict[str, str]:
    """Map every "[ref]: url" definition in the text, keyed case-insensitively."""
    defs: Dict[str, str] = {}
    for line in raw.splitlines():
        match = _LINK_DEF_RE.match(line)
        if match:
            defs[match.group(1).lower()] = match.group(2)
    return defs


def _fold_lines(lines: List[str]) -> List[Tuple[str, int, str]]:
    """Join hard-wrapped continuation lines back into one logical line each.

    CHANGELOG.md wraps bullets at ~80 columns. Telegram has no concept of a soft wrap, so
    every source line would otherwise become its own short line in the chat - and markup
    split across a wrap ("**Banger\\n  Points**") would never resolve. Folding first also
    means the chunker can treat one rendered line as an indivisible unit.

    Returns (kind, indent, text) triples, where kind is "heading", "bullet" or "text".
    """
    folded: List[Tuple[str, int, str]] = []
    for line in lines:
        if not line.strip():
            # A blank line ends the current logical line, so the next one cannot fold into it.
            folded.append(("blank", 0, ""))
            continue

        heading = _SUBSECTION_RE.match(line)
        if heading:
            folded.append(("heading", 0, heading.group(1)))
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            folded.append(("bullet", len(bullet.group(1)), bullet.group(2)))
            continue

        if folded and folded[-1][0] in ("bullet", "text"):
            kind, indent, text = folded[-1]
            folded[-1] = (kind, indent, f"{text} {line.strip()}")
        else:
            folded.append(("text", 0, line.strip()))

    return [item for item in folded if item[0] != "blank"]


def _render_body(body_lines: List[str], link_defs: Dict[str, str]) -> List[str]:
    """Render a section's body to one HTML string per displayed line.

    Every inline tag opens and closes within a single returned line. That invariant is what
    lets _pack split a long message between lines without ever cutting a tag in half.

    A blank line precedes each category after the first, so "Added" and "Fixed" read as
    separate groups rather than one run of bullets.
    """
    rendered: List[str] = []
    for kind, indent, text in _fold_lines(body_lines):
        if kind == "heading":
            if rendered:
                rendered.append("")
            rendered.append(f"<i>{_escape(text)}</i>")
        elif kind == "bullet":
            marker = f"{INDENT}{INDENT}{NESTED_BULLET}" if indent else f"{INDENT}{BULLET}"
            rendered.append(f"{marker} {_render_inline(text, link_defs)}")
        else:
            rendered.append(_render_inline(text, link_defs))
    return rendered


def _render_header(version: str, date: str | None) -> str:
    """The one line that stays visible when the body is collapsed.

    A numeric version reads as a version rather than a bare number with a "v" in front of it.
    "Unreleased" is a name, not a number, so it is left alone - "vUnreleased" is nonsense.
    """
    label = f"v{version}" if version[:1].isdigit() else version
    header = f"<b>{_escape(label)}</b>"
    if date:
        header += f" · <i>{_escape(date)}</i>"
    return header


def _split_sections(raw: str) -> List[Tuple[str, str | None, List[str]]]:
    """Split raw changelog text into (version, date, body_lines) per "## [x.y.z]" header.

    Text before the first header (the file preamble) is dropped: a reader asking for an
    entry does not want "All notable changes to this project...".
    """
    sections: List[Tuple[str, str | None, List[str]]] = []
    for line in raw.splitlines():
        header = _VERSION_HEADER_RE.match(line)
        if header:
            sections.append((header.group(1), header.group(2), []))
            continue
        if _LINK_DEF_RE.match(line):
            continue  # consumed into link_defs; never shown
        if sections:
            sections[-1][2].append(line)
    return sections


def render_changelog_html(raw: str, headline: str | None = None) -> List[str]:
    """Render raw CHANGELOG.md text into ready-to-send Telegram HTML messages.

    Each release becomes a visible header line plus its body in a blockquote, so a chat sees
    one line per release until someone taps it open. Returns one string per message; callers
    send them with parse_mode=HTML.

    headline is pre-rendered HTML that leads the first message - CHANGELOG_HEADING for
    /changelog, the upgrade notice for the startup announcement. It is never repeated on the
    later messages of a split reply.
    """
    link_defs = _collect_link_defs(raw)

    rendered: List[Tuple[str, List[str]]] = []
    for version, date, body_lines in _split_sections(raw):
        body = _render_body(body_lines, link_defs)
        if body:
            rendered.append((_render_header(version, date), body))

    messages = pack_sections(rendered)
    if headline:
        # A full first message pushes the headline into one of its own rather than over
        # Telegram's limit. An empty changelog still gets the headline: silence reads as a bug.
        if messages and len(headline) + 2 + len(messages[0]) <= MAX_MESSAGE_CHARS:
            messages[0] = f"{headline}\n\n{messages[0]}"
        else:
            messages.insert(0, headline)

    _logger.debug("Rendered %d changelog section(s) into %d message(s)", len(rendered), len(messages))
    return messages
