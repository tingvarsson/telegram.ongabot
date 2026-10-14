"""The bot's notion of time: which zone a chat lives in, and what "now" and "today" are there.

Every wall-clock time the bot works with - a poll's trigger, an event's start, the day an event
counts as past - is local to a chat. BOT_TIMEZONE sets the zone for every chat that has not
picked its own with /timezone, and UTC is the fallback when it is unset. Quiet hours - when
the bot posts without a notification sound - are chat-local too.
"""

import functools
import logging
import os
import re
import zoneinfo
from datetime import date, datetime, time, tzinfo
from typing import Dict, Optional, Tuple

_logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"
# Chat-local window in which the bot posts silently, so nobody's phone buzzes at night.
DEFAULT_QUIET_HOURS = "23:00-07:00"
_QUIET_HOURS_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
# Longest unknown zone name repeated back in an error; real IANA names are far shorter.
_MAX_SHOWN_NAME = 64


@functools.lru_cache(maxsize=1)
def _zone_names() -> Dict[str, str]:
    """Every known IANA zone name, keyed by its lowercase form so a lookup ignores case.

    Cached: the zone database cannot change while the bot runs, and listing it walks the disk.
    """
    return {name.lower(): name for name in zoneinfo.available_timezones()}


def resolve_timezone(name: str) -> zoneinfo.ZoneInfo:
    """Look up an IANA zone by name, ignoring case, e.g. "europe/stockholm".

    Only names from the zone database are accepted, so user input never reaches ZoneInfo as a
    file path. Raises ValueError for anything else.
    """
    canonical = _zone_names().get(name.strip().lower())
    if canonical is None:
        # Cut short, since the message is echoed back to the chat and must fit one message.
        shown = name if len(name) <= _MAX_SHOWN_NAME else name[:_MAX_SHOWN_NAME] + "…"
        raise ValueError(f"Unknown timezone: {shown!r}. Use an IANA name, e.g. Europe/Stockholm or UTC.")
    return zoneinfo.ZoneInfo(canonical)


def bot_timezone() -> zoneinfo.ZoneInfo:
    """The zone for chats that have not chosen one: BOT_TIMEZONE, or UTC when unset.

    Read on every call, like the other env-driven settings, so a test or a restart with a new
    value takes effect without extra plumbing. An unknown name logs a warning and falls back to
    UTC rather than stopping the bot.
    """
    raw = os.getenv("BOT_TIMEZONE", "").strip()
    if not raw:
        return zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)
    try:
        return resolve_timezone(raw)
    except ValueError:
        _logger.warning("Ignoring unknown BOT_TIMEZONE=%r; using %s", raw, DEFAULT_TIMEZONE)
        return zoneinfo.ZoneInfo(DEFAULT_TIMEZONE)


def now(tz: zoneinfo.ZoneInfo) -> datetime:
    """The current time in tz, timezone-aware."""
    return datetime.now(tz)


def today(tz: zoneinfo.ZoneInfo) -> date:
    """The current date in tz."""
    return now(tz).date()


def _parse_quiet_hours(raw: str) -> Tuple[time, time]:
    """Parse "HH:MM-HH:MM" into (start, end). Raises ValueError for anything else."""
    match = _QUIET_HOURS_RE.match(raw.strip())
    if match is None:
        raise ValueError(f"not HH:MM-HH:MM: {raw!r}")
    start_h, start_m, end_h, end_m = (int(group) for group in match.groups())
    # time() itself rejects an hour past 23 or a minute past 59.
    return time(start_h, start_m), time(end_h, end_m)


def quiet_hours() -> Optional[Tuple[time, time]]:
    """The chat-local (start, end) of quiet hours, or None when they are turned off.

    QUIET_HOURS overrides DEFAULT_QUIET_HOURS, as HH:MM-HH:MM; "off", or a start equal to its
    end, turns them off. Read on every call like BOT_TIMEZONE, and a malformed value logs a
    warning and falls back to the default rather than stopping the bot.
    """
    raw = os.getenv("QUIET_HOURS", "").strip()
    if raw.lower() == "off":
        return None
    try:
        start, end = _parse_quiet_hours(raw or DEFAULT_QUIET_HOURS)
    except ValueError:
        _logger.warning("Ignoring malformed QUIET_HOURS=%r; using %s", raw, DEFAULT_QUIET_HOURS)
        start, end = _parse_quiet_hours(DEFAULT_QUIET_HOURS)
    if start == end:
        return None
    return start, end


def quiet_end(day: date, tz: tzinfo) -> datetime:
    """When quiet hours end on day, aware in tz; midnight when they are off."""
    window = quiet_hours()
    end = window[1] if window is not None else time.min
    return datetime.combine(day, end, tzinfo=tz)


def is_quiet(moment: datetime) -> bool:
    """Whether moment, a wall-clock time in some chat's zone, falls in quiet hours.

    The window includes its start and excludes its end, and may wrap past midnight
    (23:00-07:00) or not (01:00-06:00).
    """
    window = quiet_hours()
    if window is None:
        return False
    start, end = window
    wall = moment.time()
    if start < end:
        return start <= wall < end
    return wall >= start or wall < end
