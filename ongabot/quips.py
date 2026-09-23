"""This module contains the quip lines used to call out No-op and Maybe Baby voters.

The pool is dynamic: refresh_quip_pool pulls it from JokeAPI (see jokes.py) on a repeating
job (see ongabot.py), so quips are not a fixed, hand-written list. FALLBACK_QUIPS only covers
the gap before the first successful refresh, or a prolonged JokeAPI outage.
"""

import logging
import random
from typing import List, Sequence

from jokes import JokeApiClient

_logger = logging.getLogger(__name__)

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
    fetched = await client.fetch_jokes()
    if not fetched:
        _logger.warning("Quip pool refresh found nothing usable; keeping existing pool of %d", len(_pool))
        return
    _pool = fetched
    _logger.info("Refreshed quip pool with %d joke(s)", len(_pool))


def select_quip(quips: Sequence[str], poll_id: str, user_id: int, option_index: int) -> str:
    """Deterministically pick a quip for a (poll, user, option) triple.

    Seeded on the identifiers rather than stored anywhere, so repeated renders of the same
    status message show the same quip for a given voter without persisting state.
    """
    return random.Random(f"{poll_id}:{user_id}:{option_index}").choice(quips)
