"""Tie a Chat and an Event to a rendered CS2 results message.

The one place that knows how the pieces fit together, so the /cs2 command and the sweep job
in ongabot.py cannot drift apart.
"""

import logging
from typing import Mapping, Optional, Tuple, TYPE_CHECKING

from cs2.format import format_session
from cs2.session import Cs2Session, MatchSource, build_session, steam_links
from utils import log

if TYPE_CHECKING:  # pragma: no cover - import cycle: chat -> event -> ... -> cs2
    from chat import Chat
    from event import Event
    from userdata import UserData

_logger = logging.getLogger(__name__)


@log.log
async def event_session(
    client: MatchSource,
    chat: "Chat",
    event: "Event",
    user_data: Mapping[int, "UserData"],
) -> Optional[Cs2Session]:
    """Fetch the CS2 session for one event, or None when Leetify could not be reached.

    None means "unknown", not "nobody played" - a caller polling through the evening should
    retry rather than report an empty night.
    """
    links = steam_links(chat, user_data)
    if not links:
        _logger.debug("No linked members in chat_id=%s; nothing to report", chat.chat_id)

    return await build_session(client, event.event_date, links)


def render_results(session: Cs2Session, live: bool = False) -> str:
    """Render a fetched session into the CS2 results message.

    Kept here so a caller that fetches once and renders twice - the sweep, dropping the live
    marker on its final pass - does not have to reach into cs2.format itself.
    """
    return format_session(session, live=live)


@log.log
async def event_results(
    client: MatchSource,
    chat: "Chat",
    event: "Event",
    user_data: Mapping[int, "UserData"],
) -> Tuple[Optional[Cs2Session], Optional[str]]:
    """Fetch and render the CS2 results for one event.

    Returns (session, message text), or (None, None) when Leetify could not be reached at
    all - the caller should retry rather than report that nobody played.
    """
    session = await event_session(client, chat, event, user_data)
    if session is None:
        return None, None

    return session, render_results(session)


def latest_reportable_event(chat: "Chat") -> Optional["Event"]:
    """The most recent completed, non-cancelled event, or None if the chat has none.

    Cancelled events are skipped for the same reason utils.points skips them: they are not
    events that happened.
    """
    candidates = [event for event in chat.events.values() if event.completed and not event.cancelled]
    if not candidates:
        return None
    return max(candidates, key=lambda event: event.event_date)
