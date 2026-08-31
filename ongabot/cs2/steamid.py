"""Parse a Steam64 out of what a user is likely to paste into /linksteam.

Deliberately limited to input that can be resolved offline: a raw Steam64, or the
steamcommunity.com/profiles/<id> URL that contains one. A vanity URL
(steamcommunity.com/id/<name>) is rejected rather than resolved, because resolving it would
mean a Steam Web API key and a second external dependency for the sake of one convenience.
"""

import logging
import re
from typing import Optional

_logger = logging.getLogger(__name__)

# The lowest Steam64 in the individual-account space; every real player id is above it.
MIN_STEAM64 = 76561197960265728
MAX_STEAM64 = 76561202255233023

_PROFILES_URL = re.compile(r"steamcommunity\.com/profiles/(\d+)", re.IGNORECASE)


def parse_steam64(text: Optional[str]) -> Optional[str]:
    """Return the Steam64 in text, or None if there isn't a plausible one."""
    if not text:
        return None

    candidate = text.strip()
    match = _PROFILES_URL.search(candidate)
    if match:
        candidate = match.group(1)

    if not candidate.isdigit():
        _logger.debug("Not a Steam64: %r", text)
        return None

    if not MIN_STEAM64 <= int(candidate) <= MAX_STEAM64:
        _logger.debug("Steam64 %s is outside the individual-account range", candidate)
        return None

    return candidate
