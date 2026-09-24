"""Offline checks for the Telegram markup a message builder emits.

Telegram rejects a whole message with "Can't parse entities" when its markup is off by a
single character, and until now that only ever surfaced live, in a chat. These checks follow
the Bot API formatting rules (https://core.telegram.org/bots/api#formatting-options) closely
enough to catch it in `make test` instead: unescaped reserved characters, unknown or unbalanced
tags, overlapping entities, and text over the per-message length limit.

check_html / check_markdown_v2 raise MarkupError (an AssertionError, so a unittest reports a
failure rather than an error) and otherwise return the text a reader would see.
"""

import html
import re
from typing import List

# Telegram's limit is on the text left after entity parsing, counted in UTF-16 code units.
MAX_MESSAGE_CHARS = 4096

HTML_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "code",
        "del",
        "em",
        "i",
        "ins",
        "pre",
        "s",
        "span",
        "strike",
        "strong",
        "tg-emoji",
        "tg-spoiler",
        "u",
    }
)
# The only named entities the Bot API accepts; numeric ones are all fine.
_HTML_NAMED_ENTITIES = frozenset({"lt", "gt", "amp", "quot"})
_HTML_TAG_RE = re.compile(r"<(/?)([a-z-]+)(\s[^<>]*)?>")
_HTML_ENTITY_RE = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")

# Characters MarkdownV2 reserves outside code; each must be escaped with a preceding '\'.
MARKDOWN_V2_RESERVED = frozenset("_*[]()~`>#+-=|{}.!")


class MarkupError(AssertionError):
    """A message Telegram would reject."""


def _fail(text: str, pos: int, problem: str) -> MarkupError:
    start = max(0, pos - 20)
    context = text[start:][:40]
    return MarkupError(f"{problem} at offset {pos}: ...{context!r}...")


def _check_length(text: str, visible: str) -> None:
    length = len(visible.encode("utf-16-le")) // 2
    if not visible.strip():
        raise MarkupError(f"message has no visible text: {text!r}")
    if length > MAX_MESSAGE_CHARS:
        raise MarkupError(f"message is {length} characters, over Telegram's {MAX_MESSAGE_CHARS}")


def _open_html_tag(text: str, pos: int, name: str, attrs: str, stack: List[str]) -> None:
    if stack and stack[-1] == "code":
        raise _fail(text, pos, f"<{name}> inside <code>, which holds plain text only")
    if stack and stack[-1] == "pre" and name != "code":
        raise _fail(text, pos, f"<{name}> inside <pre>, which holds plain text or one <code> only")
    if name == "blockquote" and "blockquote" in stack:
        raise _fail(text, pos, "nested <blockquote>")
    if name == "a" and "href=" not in attrs:
        raise _fail(text, pos, "<a> without href")
    stack.append(name)


def _close_html_tag(text: str, pos: int, name: str, stack: List[str]) -> None:
    if not stack:
        raise _fail(text, pos, f"</{name}> with no open tag")
    if stack[-1] != name:
        raise _fail(text, pos, f"</{name}> while <{stack[-1]}> is still open")
    stack.pop()


def check_html(text: str) -> str:
    """Validate a parse_mode=HTML message and return its visible text."""
    stack: List[str] = []
    visible: List[str] = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == "<":
            tag = _HTML_TAG_RE.match(text, pos)
            if tag is None:
                raise _fail(text, pos, "unescaped '<'")
            closing, name, attrs = tag.group(1), tag.group(2), tag.group(3) or ""
            if name not in HTML_TAGS:
                raise _fail(text, pos, f"unsupported tag <{name}>")
            if closing:
                _close_html_tag(text, pos, name, stack)
            else:
                _open_html_tag(text, pos, name, attrs, stack)
            pos = tag.end()
        elif char == ">":
            raise _fail(text, pos, "unescaped '>'")
        elif char == "&":
            entity = _HTML_ENTITY_RE.match(text, pos)
            if entity is None:
                raise _fail(text, pos, "unescaped '&'")
            name = entity.group(1)
            if not name.startswith("#") and name not in _HTML_NAMED_ENTITIES:
                raise _fail(text, pos, f"unsupported entity &{name};")
            visible.append(html.unescape(entity.group(0)))
            pos = entity.end()
        else:
            visible.append(char)
            pos += 1
    if stack:
        raise MarkupError(f"unclosed tag(s) {['<' + name + '>' for name in stack]} in {text!r}")
    plain = "".join(visible)
    _check_length(text, plain)
    return plain


class _MarkdownV2Checker:
    """One pass over a MarkdownV2 message, tracking which entities are open."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.stack: List[str] = []
        self.visible: List[str] = []

    def run(self) -> str:
        """Walk the whole message; raise at the first problem, else return the visible text."""
        while self.pos < len(self.text):
            self._step()
        if self.stack:
            raise MarkupError(f"unclosed entity marker(s) {self.stack} in {self.text!r}")
        plain = "".join(self.visible)
        _check_length(self.text, plain)
        return plain

    def _step(self) -> None:
        text, pos = self.text, self.pos
        char = text[pos]
        at_line_start = pos == 0 or text[pos - 1] == "\n"
        if char == "\\":
            self._escaped(pos + 1)
        elif char == "`":
            self._code(pos)
        elif text.startswith("||", pos):
            self._toggle("||", 2)
        elif text.startswith("__", pos):
            self._toggle("__", 2)
        elif char in "_*~":
            self._toggle(char, 1)
        elif char == "[":
            self.stack.append("[")
            self.pos += 1
        elif char == "]":
            self._link_end()
        elif char == ">" and at_line_start:
            self.pos += 1  # blockquote line marker
        elif char in MARKDOWN_V2_RESERVED:
            raise _fail(text, pos, f"unescaped reserved character {char!r}")
        else:
            self.visible.append(char)
            self.pos += 1

    def _escaped(self, target: int) -> None:
        if target >= len(self.text) or not 1 <= ord(self.text[target]) <= 126:
            raise _fail(self.text, self.pos, "'\\' that escapes no ASCII character")
        self.visible.append(self.text[target])
        self.pos = target + 1

    def _toggle(self, marker: str, width: int) -> None:
        if self.stack and self.stack[-1] == marker:
            self.stack.pop()
        elif marker in self.stack:
            raise _fail(self.text, self.pos, f"{marker!r} closes across another open entity {self.stack[-1]!r}")
        else:
            self.stack.append(marker)
        self.pos += width

    def _code(self, pos: int) -> None:
        """Consume an inline `code` or ```pre``` entity; inside, only '`' and '\\' are special."""
        fence = "```" if self.text.startswith("```", pos) else "`"
        scan = pos + len(fence)
        while scan < len(self.text):
            if self.text[scan] == "\\":
                if scan + 1 >= len(self.text):
                    break
                self.visible.append(self.text[scan + 1])
                scan += 2
            elif self.text[scan] == "`":
                if not self.text.startswith(fence, scan):
                    raise _fail(self.text, scan, "unescaped '`' inside a code block")
                self.pos = scan + len(fence)
                return
            else:
                self.visible.append(self.text[scan])
                scan += 1
        raise _fail(self.text, pos, f"unterminated {fence!r} code entity")

    def _link_end(self) -> None:
        """Close a [text](url) link; inside the url only ')' and '\\' are special."""
        if not self.stack or self.stack[-1] != "[":
            raise _fail(self.text, self.pos, "unescaped ']'")
        self.stack.pop()
        if not self.text.startswith("(", self.pos + 1):
            raise _fail(self.text, self.pos, "link text without a (url)")
        scan = self.pos + 2
        while scan < len(self.text):
            if self.text[scan] == "\\":
                scan += 2
            elif self.text[scan] == ")":
                self.pos = scan + 1
                return
            else:
                scan += 1
        raise _fail(self.text, self.pos, "unterminated link url")


def check_markdown_v2(text: str) -> str:
    """Validate a parse_mode=MarkdownV2 message and return its visible text."""
    return _MarkdownV2Checker(text).run()


def check_plain_text(text: str) -> str:
    """Validate a message sent without a parse mode: only the length can be wrong."""
    _check_length(text, text)
    return text
