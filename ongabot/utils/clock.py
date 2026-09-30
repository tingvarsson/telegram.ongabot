"""The bot's notion of time: which zone a chat lives in, and what "now" and "today" are there.

Every wall-clock time the bot works with - a poll's trigger, an event's start, the day an event
counts as past - is local to a chat. BOT_TIMEZONE sets the zone for every chat that has not
picked its own with /timezone, and UTC is the fallback when it is unset.
"""

import functools
import logging
import os
import zoneinfo
from datetime import date, datetime
from typing import Dict

_logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"


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
        raise ValueError(f"Unknown timezone: {name!r}. Use an IANA name, e.g. Europe/Stockholm or UTC.")
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
