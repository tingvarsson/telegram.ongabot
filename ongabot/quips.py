"""This module contains the quip lines used to call out No-op and Maybe Baby voters.

The pool is dynamic: refresh_quip_pool pulls it from JokeAPI (see jokes.py) on a repeating
job (see ongabot.py), so quips are not a fixed, hand-written list. FALLBACK_QUIPS only covers
the gap before the first successful refresh, or a prolonged JokeAPI outage.
"""

import logging
import random
from typing import List, Optional

from jokes import JokeApiClient

_logger = logging.getLogger(__name__)

# The quip follows "<name> — " in a chat message, so anything past about one phone line
# reads as a rambling story rather than a callout. Longer jokes are dropped at refresh time.
MAX_QUIP_LENGTH = 80
# JokeAPI returns at most 10 jokes per refresh and the length cap drops some of them. Below this
# many survivors the pool is topped up with FALLBACK_QUIPS, so next_quip always has something
# other than the last quip to pick for the ~6 hours until the next refresh.
MIN_POOL_SIZE = 3

FALLBACK_QUIPS: List[str] = [
    "has entered witness protection for the night",
    "is saving their energy for absolutely nothing",
    "checked the group chat just to say no",
    "voted with their whole chest: not today",
    "is keeping their options open, and everyone else waiting",
    "is playing hard to schedule",
]

# The live pool, replaced wholesale by refresh_quip_pool. Empty until the first refresh.
_pool: List[str] = []

# The quip handed out most recently (in any chat), so next_quip never repeats it back to back.
# Kept in memory only - after a restart the first pick is simply unconstrained.
_last_quip: Optional[str] = None  # pylint: disable=invalid-name


def get_quip_pool() -> List[str]:
    """Return the current quip pool, or FALLBACK_QUIPS if it has never been refreshed."""
    return _pool if _pool else FALLBACK_QUIPS


async def refresh_quip_pool(client: JokeApiClient) -> None:
    """Refresh the live quip pool from JokeAPI.

    A failed or empty fetch leaves the existing pool in place - a stale pool (or the static
    fallback, before the first refresh) is better than briefly emptying it out from under a
    render in progress.
    """
    global _pool  # pylint: disable=global-statement
    fetched = await client.fetch_jokes() or []
    usable = [joke for joke in fetched if len(joke) <= MAX_QUIP_LENGTH]
    if len(usable) < len(fetched):
        _logger.info("Dropped %d joke(s) longer than %d chars", len(fetched) - len(usable), MAX_QUIP_LENGTH)
    if not usable:
        _logger.warning("Quip pool refresh found nothing usable; keeping existing pool of %d", len(_pool))
        return
    if len(usable) < MIN_POOL_SIZE:
        _logger.info("Only %d usable joke(s); topping up the quip pool with the fallback quips", len(usable))
        usable += FALLBACK_QUIPS
    _pool = usable
    _logger.info("Refreshed quip pool with %d joke(s)", len(_pool))


def next_quip() -> str:
    """Pick a random quip from the current pool, never the same one twice in a row.

    The quip is a one-off chat message sent right after a No-op/Maybe-Baby vote, so it is
    drawn fresh on every vote; excluding the previous pick keeps a voter toggling their vote
    from getting the same line straight back, even though the pool holds at most ~10 jokes.
    """
    global _last_quip  # pylint: disable=global-statement
    pool = get_quip_pool()
    # Fall back to the whole pool when excluding the last quip would leave nothing to pick.
    candidates = [quip for quip in pool if quip != _last_quip] or pool
    _last_quip = random.choice(candidates)
    _logger.debug("Picked quip from %d candidate(s) out of a pool of %d", len(candidates), len(pool))
    return _last_quip
