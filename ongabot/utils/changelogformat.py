"""Render CHANGELOG.md sections into the Telegram HTML ONGAbot posts.

Keeps utils.changelog as the pure source-slicing module; this one is purely presentation.
Like that module, it imports nothing outside the standard library.
"""

import html
import logging
import re
from typing import Dict, List, Tuple

from utils.changelog import MAX_MESSAGE_CHARS

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

# Telegram collapses an expandable blockquote to a few preview lines. Below this many lines
# there is nothing worth hiding, and the expand affordance would itself be noise.
EXPANDABLE_MIN_LINES = 4

_BLOCKQUOTE_CLOSE = "</blockquote>"

# Longest named/numeric entity html.escape can emit ("&quot;"), plus room to spare.
_MAX_ENTITY_LEN = 10

_TAG_NAME_RE = re.compile(r"</?(\w+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _escape(text: str) -> str:
    """Escape text content for Telegram HTML.

    Only '<', '>' and '&' need escaping in content - quotes matter inside an attribute value
    and nowhere else. html.escape's default would turn every apostrophe into "&#x27;", six
    characters where one will do, and a changelog is full of them.
    """
    return html.escape(text, quote=False)


def to_plain_text(message: str) -> str:
    """Strip the HTML back out of a rendered message.

    Telegram rejects a whole message if any entity is malformed, so a send site that gets a
    BadRequest resends this instead: the reader still gets the content, just without the
    formatting. Better an ugly changelog than none.
    """
    return html.unescape(_TAG_RE.sub("", message))


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

    messages = _pack(rendered)
    if headline:
        # A full first message pushes the headline into one of its own rather than over
        # Telegram's limit. An empty changelog still gets the headline: silence reads as a bug.
        if messages and len(headline) + 2 + len(messages[0]) <= MAX_MESSAGE_CHARS:
            messages[0] = f"{headline}\n\n{messages[0]}"
        else:
            messages.insert(0, headline)

    _logger.debug("Rendered %d changelog section(s) into %d message(s)", len(rendered), len(messages))
    return messages


def _open_tag(body: List[str]) -> str:
    """The blockquote opening tag for a body, expandable only when long enough to matter."""
    return "<blockquote expandable>" if len(body) >= EXPANDABLE_MIN_LINES else "<blockquote>"


def _next_token(line: str, start: int) -> Tuple[str, int]:
    """Return the next indivisible unit of a rendered line: a tag, an entity, or a character.

    Splitting anywhere else would cut "<code>" or "&amp;" in half and Telegram would reject
    the whole message.
    """
    if line[start] == "<":
        stop = line.find(">", start) + 1
        if stop > 0:
            return line[start:stop], stop
    elif line[start] == "&":
        stop = line.find(";", start) + 1
        if 0 < stop - start <= _MAX_ENTITY_LEN:
            return line[start:stop], stop
    return line[start], start + 1


def _closing_tags(stack: List[str]) -> str:
    """Closing tags for every currently open tag, innermost first."""
    names = [match.group(1) for match in (_TAG_NAME_RE.match(tag) for tag in reversed(stack)) if match]
    return "".join(f"</{name}>" for name in names)


def _split_long_line(line: str, budget: int) -> List[str]:
    """Cut one rendered line that cannot fit a message, keeping every tag balanced.

    Only reachable from a pathological changelog entry - a single bullet over ~4000
    characters - but the alternative is Telegram rejecting the message outright.
    """
    pieces: List[str] = []
    stack: List[str] = []  # open tags, innermost last
    current = ""
    index = 0
    while index < len(line):
        token, index = _next_token(line, index)
        closing = _closing_tags(stack)
        reopen = "".join(stack)
        # The second clause guarantees progress: never flush a piece that is only reopened
        # tags, or a budget smaller than those tags would loop forever.
        if len(current) + len(token) + len(closing) > budget and len(current) > len(reopen):
            pieces.append(current + closing)
            current = reopen
        current += token
        if token.startswith("</"):
            if stack:
                stack.pop()
        elif token.startswith("<"):
            stack.append(token)

    if current:
        pieces.append(current + _closing_tags(stack))
    _logger.warning("Hard-split an oversized changelog line into %d pieces", len(pieces))
    return pieces


def _fit_lines(body: List[str], budget: int) -> List[str]:
    """Body lines, with any line too long for a message of its own split up first."""
    fitted: List[str] = []
    for line in body:
        fitted.extend([line] if len(line) <= budget else _split_long_line(line, budget))
    return fitted


def _pack(sections: List[Tuple[str, List[str]]], limit: int = MAX_MESSAGE_CHARS) -> List[str]:
    """Lay rendered sections out into messages that each fit Telegram's limit.

    A message boundary closes the blockquote and the next message reopens it, so no tag ever
    spans two messages. A section header is never stranded at the end of a message: it is
    always sent with at least the first line of its body.
    """
    messages: List[str] = []
    buffer = ""  # the message being built; its blockquote is open unless buffer is empty
    has_body = False  # whether the open blockquote has a body line yet

    for header, body in sections:
        tag = _open_tag(body)
        # The header always shares a message with the first body line, so it has to come out
        # of the budget too. Charging every line for it costs a few characters per message
        # and keeps the bound obviously correct.
        lines = _fit_lines(body, limit - len(tag) - len(_BLOCKQUOTE_CLOSE) - len(header) - 1)

        if buffer:
            buffer += _BLOCKQUOTE_CLOSE  # seal the previous section before starting this one
        start = ("\n\n" if buffer else "") + header + "\n" + tag
        if buffer and len(buffer + start + lines[0] + _BLOCKQUOTE_CLOSE) > limit:
            messages.append(buffer)  # already sealed above
            buffer = ""
            start = header + "\n" + tag
        buffer += start + lines[0]
        has_body = True

        for line in lines[1:]:
            separator = "\n" if has_body else ""
            if len(buffer + separator + line + _BLOCKQUOTE_CLOSE) > limit:
                messages.append(buffer + _BLOCKQUOTE_CLOSE)
                buffer, separator, has_body = tag, "", False
                if not line:
                    # A category separator that lands on a message boundary is redundant:
                    # the break already separates the two categories.
                    continue
            buffer += separator + line
            has_body = has_body or bool(line)

    if buffer:
        messages.append(buffer + _BLOCKQUOTE_CLOSE)
    _logger.debug("Packed %d changelog section(s) into %d message(s)", len(sections), len(messages))
    return messages
