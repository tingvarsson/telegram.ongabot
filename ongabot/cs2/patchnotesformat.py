"""Render CS2 patch notes into the Telegram HTML messages ONGAbot posts.

Same shape as utils.changelogformat's release announcements: each patch is one visible header
line (title and date) with its body collapsed in an expandable blockquote, so a big patch is
two lines in the chat until someone opens it. Body conversion is cs2.bbcode; message packing
and splitting is utils.htmlblocks.
"""

import datetime
import html
import logging
from typing import List, Tuple

from cs2.bbcode import render_bbcode_to_lines
from cs2.steamnews import SteamNewsItem
from utils.htmlblocks import pack_sections

_logger = logging.getLogger(__name__)

FULL_NOTES_LABEL = "Full notes on Steam"


def _render_header(item: SteamNewsItem) -> str:
    """The one line that stays visible when the body is collapsed."""
    posted = datetime.date.fromtimestamp(item.date).isoformat()
    return f"<b>{html.escape(item.title, quote=False)}</b> · <i>{posted}</i>"


def _render_body(item: SteamNewsItem) -> List[str]:
    """The patch's own lines, then a link to the post on Steam.

    The link comes last rather than in the header, so the collapsed preview stays just title
    and date. It also guarantees a body even when the post renders to nothing.
    """
    link = f'<a href="{html.escape(item.url, quote=True)}">{FULL_NOTES_LABEL}</a>'
    return render_bbcode_to_lines(item.contents) + [link]


def render_patch_notes_html(items: List[SteamNewsItem]) -> List[str]:
    """Render patch-note items into ready-to-send Telegram HTML messages, in the order given.

    Several items (patches that landed between two polls) share messages where they fit, the
    way several changelog releases do; one too big for a message is split across several.
    Sorting is the caller's job. Send with parse_mode=HTML.
    """
    sections: List[Tuple[str, List[str]]] = [(_render_header(item), _render_body(item)) for item in items]
    messages = pack_sections(sections)
    _logger.debug("Rendered %d patch note(s) into %d message(s)", len(items), len(messages))
    return messages
