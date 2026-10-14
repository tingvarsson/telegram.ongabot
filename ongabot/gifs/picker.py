"""Pick a GIF for a mood: deal a search phrase, search it (cached), and pick an unseen hit.

Everything here lives in memory only. After a restart the cache is simply cold and a chat may
see a GIF again a little sooner; neither is worth a place in the pickled bot data.
"""

import collections
import logging
import random
import time
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from gifs.client import Gif, GiphyClient, get_client
from gifs.moods import Mood, next_phrase

_logger = logging.getLogger(__name__)

# How long one phrase's search results are reused. A day keeps a busy chat at a handful of
# searches a day, well under the beta key's 100 calls an hour, while new GIFs still trickle in.
CACHE_TTL_SECONDS = 24 * 60 * 60
# How many of the latest GIFs sent to a chat are left out of its next picks.
RECENT_PER_CHAT = 50


@dataclass(frozen=True)
class PickedGif:
    """A GIF to send, and the phrase that found it, for the log."""

    gif: Gif
    phrase: str


# phrase -> (when searched, results). Failed searches are not cached, so the next moment retries.
_cache: Dict[str, Tuple[float, List[Gif]]] = {}
# chat_id -> ids of the latest GIFs picked for it, oldest first.
_recent: Dict[int, Deque[str]] = {}


def _clock() -> float:
    """Seconds on a monotonic clock. A function so tests can move time."""
    return time.monotonic()


def reset() -> None:
    """Forget every cached search and every chat's recent GIFs. For tests."""
    _cache.clear()
    _recent.clear()


async def _search(client: GiphyClient, phrase: str) -> Optional[List[Gif]]:
    """phrase's search results, from the cache while fresh. None when the search failed."""
    cached = _cache.get(phrase)
    if cached is not None and _clock() - cached[0] < CACHE_TTL_SECONDS:
        _logger.debug("GIF search cache hit for phrase=%r (%d result(s))", phrase, len(cached[1]))
        return cached[1]

    _logger.debug("GIF search cache miss for phrase=%r", phrase)
    results = await client.search(phrase)
    if results is not None:
        _cache[phrase] = (_clock(), results)
    return results


async def pick_gif(chat_id: int, mood: Mood, client: Optional[GiphyClient] = None) -> Optional[PickedGif]:
    """A GIF for mood that chat_id has not been sent lately, or None when there is none to give.

    None covers a missing API key, a failed search, no results for the dealt phrase, and every
    result having been sent to the chat recently. The pick is recorded right away, before the
    caller sends it, so two moments in quick succession never pick the same GIF.
    """
    phrase = next_phrase(mood)
    results = await _search(client or get_client(), phrase)
    if not results:
        return None

    recent = _recent.setdefault(chat_id, collections.deque(maxlen=RECENT_PER_CHAT))
    candidates = [gif for gif in results if gif.gif_id not in recent]
    if not candidates:
        _logger.info("Every GIF for phrase=%r was sent to chat_id=%s lately", phrase, chat_id)
        return None

    gif = random.choice(candidates)
    recent.append(gif.gif_id)
    return PickedGif(gif=gif, phrase=phrase)
