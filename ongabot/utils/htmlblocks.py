"""Generic Telegram-HTML message assembly: expandable blockquotes, splitting, sending.

Extracted out of utils.changelogformat, which needed exactly this - "header + expandable
blockquote + split across Telegram's 4096-char limit without cutting a tag in half + a
plain-text fallback when Telegram rejects the HTML" - for changelog rendering. None of it
actually depends on changelog syntax: it operates on (header, body_lines) tuples of
pre-rendered, tag-balanced-per-line HTML strings. cs2.patchnotesformat reuses it for the same
reason changelogformat needed it in the first place, rather than duplicating this logic.
"""

import html
import logging
import re
from typing import List, Tuple

from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest

from utils.changelog import MAX_MESSAGE_CHARS

_logger = logging.getLogger(__name__)

# Telegram collapses an expandable blockquote to a few preview lines. Below this many lines
# there is nothing worth hiding, and the expand affordance would itself be noise.
EXPANDABLE_MIN_LINES = 4

_BLOCKQUOTE_CLOSE = "</blockquote>"

# Longest named/numeric entity html.escape can emit ("&quot;"), plus room to spare.
_MAX_ENTITY_LEN = 10

_TAG_NAME_RE = re.compile(r"</?(\w+)")
_TAG_RE = re.compile(r"<[^>]+>")

# A preview card per link is exactly the noise collapsing a message into a blockquote is
# meant to remove.
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def to_plain_text(message: str) -> str:
    """Strip the HTML back out of a rendered message.

    Telegram rejects a whole message if any entity is malformed, so a send site that gets a
    BadRequest resends this instead: the reader still gets the content, just without the
    formatting. Better an ugly message than none.
    """
    return html.unescape(_TAG_RE.sub("", message))


def open_blockquote_tag(body: List[str], min_lines: int = EXPANDABLE_MIN_LINES) -> str:
    """The blockquote opening tag for a body, expandable only when long enough to matter."""
    return "<blockquote expandable>" if len(body) >= min_lines else "<blockquote>"


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

    Only reachable from a pathological entry - a single bullet over ~4000 characters - but
    the alternative is Telegram rejecting the message outright.
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
    _logger.warning("Hard-split an oversized line into %d pieces", len(pieces))
    return pieces


def _fit_lines(body: List[str], budget: int) -> List[str]:
    """Body lines, with any line too long for a message of its own split up first."""
    fitted: List[str] = []
    for line in body:
        fitted.extend([line] if len(line) <= budget else _split_long_line(line, budget))
    return fitted


def _split_section(header: str, tag: str, lines: List[str], limit: int) -> List[str]:
    """Spread one section that cannot fit a single message across several.

    Each message closes the blockquote and the next reopens it, so no tag spans two
    messages. Only the first carries the header; the rest continue it.
    """
    messages: List[str] = []
    buffer = header + "\n" + tag + lines[0]
    has_body = True  # whether the open blockquote has a body line yet

    for line in lines[1:]:
        separator = "\n" if has_body else ""
        if len(buffer + separator + line + _BLOCKQUOTE_CLOSE) > limit:
            messages.append(buffer + _BLOCKQUOTE_CLOSE)
            buffer, separator, has_body = tag, "", False
            if not line:
                # A separator line that lands on a message boundary is redundant: the break
                # already separates the two groups it would have separated.
                continue
        buffer += separator + line
        has_body = has_body or bool(line)

    messages.append(buffer + _BLOCKQUOTE_CLOSE)
    _logger.info("Section %r needed %d messages on its own", header, len(messages))
    return messages


def pack_sections(sections: List[Tuple[str, List[str]]], limit: int = MAX_MESSAGE_CHARS) -> List[str]:
    """Lay rendered (header, body_lines) sections out into messages that each fit limit.

    A section is the unit: a message break falls between sections, and one is only cut in
    half when it cannot fit a message even on its own. Reading a section split across two
    messages is worse than reading one message that holds fewer of them.
    """
    messages: List[str] = []
    buffer = ""  # complete, already-sealed sections waiting to be sent together

    for header, body in sections:
        tag = open_blockquote_tag(body)
        # The header shares a message with the first body line, so it comes out of the budget
        # too. Charging every line for it costs a few characters and keeps the bound obvious.
        lines = _fit_lines(body, limit - len(tag) - len(_BLOCKQUOTE_CLOSE) - len(header) - 1)
        whole = header + "\n" + tag + "\n".join(lines) + _BLOCKQUOTE_CLOSE

        if len(whole) > limit:
            # Too big to keep intact: flush what is buffered so it starts on a clean message.
            if buffer:
                messages.append(buffer)
                buffer = ""
            messages.extend(_split_section(header, tag, lines, limit))
            continue

        if buffer and len(buffer) + 2 + len(whole) > limit:
            messages.append(buffer)
            buffer = ""
        buffer = whole if not buffer else buffer + "\n\n" + whole

    if buffer:
        messages.append(buffer)
    _logger.debug("Packed %d section(s) into %d message(s)", len(sections), len(messages))
    return messages


async def send_html_with_fallback(bot: Bot, chat_id: int, text: str) -> None:
    """Send one message as Telegram HTML, falling back to plain text if Telegram rejects it.

    A malformed entity fails the whole message. Callers of this send an announcement or a
    patch note unprompted, so an unformatted message beats a silently missing one.
    """
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, link_preview_options=_NO_PREVIEW)
    except BadRequest as e:
        _logger.warning("Message to chat_id=%s rejected as HTML (%s); resending as plain text", chat_id, e)
        await bot.send_message(chat_id=chat_id, text=to_plain_text(text), link_preview_options=_NO_PREVIEW)
