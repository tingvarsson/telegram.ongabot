"""Pick the top-ranked YouTube Short a chat has not had yet, for /short.

Domain layer: decides which search hits count as Shorts and in what order, holds no HTTP
knowledge (ongabot.youtube.client does the I/O) and no Telegram knowledge (the /short handler
posts the result). Ties the client to a chat's dedup history.

Two shapes of request:

* No topics - this week's most-viewed Shorts in YouTube's Gaming category.
* Topics - the most-viewed Shorts matching the topics, this week first, widening to this month
  and then all time whenever a window has nothing the chat hasn't already seen.

Ranked lists are cached in-process for a few hours (see fetch_ranked), so repeated /short calls
walk down the same chart without spending another search each.
"""

import enum
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence, Tuple

from youtube.client import SearchResult, VideoDetail
from utils import log

if TYPE_CHECKING:  # pragma: no cover - import cycle: chat -> ... -> youtube.selection
    from chat import Chat

_logger = logging.getLogger(__name__)

# YouTube raised the Shorts limit from 60 seconds to 3 minutes in 2024.
MAX_SHORT_SECONDS = 180

# YouTube's videoCategoryId for "Gaming".
GAMING_CATEGORY_ID = "20"

# Query for the weekly Gaming chart. A bare category search is mostly regular uploads that
# happen to be under 4 minutes; the hashtag steers results towards real Shorts.
WEEKLY_QUERY = "#shorts"

# How long a ranked list is reused. View counts shift slowly enough that a few hours is fresh,
# and it bounds a busy chat to a handful of 100-unit searches a day per query.
CACHE_TTL = timedelta(hours=3)
CACHE_MAX_ENTRIES = 32


class Window(enum.Enum):
    """A publish window a search is limited to, with the label used when presenting a pick."""

    WEEK = (7, "this week")
    MONTH = (30, "this month")
    ALL_TIME = (None, "of all time")

    def __init__(self, days: Optional[int], label: str) -> None:
        # None means no publishedAfter limit at all.
        self.days = days
        self.label = label


@dataclass(frozen=True)
class RankedShort:
    """A confirmed Short in a ranked list, most-viewed first."""

    video_id: str
    title: str
    url: str
    view_count: int


@dataclass(frozen=True)
class SelectedVideo:
    """The Short chosen for a /short post, with where it ranked and what it was searched for."""

    video_id: str
    title: str
    url: str
    view_count: int
    # 1-based position among the filtered, view-sorted Shorts of the window - not among the
    # ones this chat hasn't seen - so "#3 this week" means the third most-viewed Short.
    rank: int
    window: Window
    # The /short arguments; empty for the weekly Gaming chart.
    topics: Tuple[str, ...]


@dataclass(frozen=True)
class PickResult:
    """The outcome of pick_short - exactly one of the three fields is set.

    * ``video`` - a Short to post.
    * ``unavailable`` - no window returned data at all (API failure or quota), so the caller
      should suggest trying again later.
    * ``exhausted`` - data came back, but it was empty or every Short in it was already posted
      to this chat recently.
    """

    video: Optional[SelectedVideo] = None
    unavailable: bool = False
    exhausted: bool = False


@dataclass(frozen=True)
class PostedShort:
    """Unused. Only exists so pickles written before /short went on-demand still load.

    Chat.posted_shorts used to hold these, so older bot_data pickles reference
    youtube.selection.PostedShort by name; unpickling fails without the class.
    Chat.__setstate__ drops posted_shorts once loaded.
    """

    video_id: str
    topics: Tuple[str, ...]
    posted_at: datetime


class VideoSource(Protocol):
    """The slice of ongabot.youtube.client.YouTubeClient this module needs."""

    async def search_shorts(
        self,
        query: str,
        *,
        order: str = "viewCount",
        published_after: Optional[datetime] = None,
        category_id: Optional[str] = None,
        max_results: int = 50,
    ) -> Optional[List[SearchResult]]:
        """Return candidate Shorts, or None if unavailable."""

    async def get_video_details(self, video_ids: Sequence[str]) -> Optional[Dict[str, VideoDetail]]:
        """Return duration/views/live state/title for each id, or None if unavailable."""


@dataclass(frozen=True)
class _CacheEntry:
    fetched_at: datetime
    shorts: Tuple[RankedShort, ...]


_CacheKey = Tuple[str, Window, Optional[str]]

# Module-level rather than on BotData, for the same reason as youtube.client.get_client: BotData
# is pickled by PicklePersistence and this is throwaway state. Insertion-ordered, so the first
# key is always the oldest entry.
_cache: Dict[_CacheKey, _CacheEntry] = {}


def _now() -> datetime:
    """Current UTC time; a seam for tests to control the cache TTL and publish windows."""
    return datetime.now(timezone.utc)


def clear_cache() -> None:
    """Forget every cached ranked list."""
    _cache.clear()


def _cache_get(key: _CacheKey, now: datetime) -> Optional[List[RankedShort]]:
    entry = _cache.get(key)
    if entry is None:
        return None
    if now - entry.fetched_at >= CACHE_TTL:
        del _cache[key]
        return None
    return list(entry.shorts)


def _cache_put(key: _CacheKey, shorts: List[RankedShort], now: datetime) -> None:
    # Re-inserting moves the key to the end, so eviction order stays by fetch time.
    _cache.pop(key, None)
    while len(_cache) >= CACHE_MAX_ENTRIES:
        oldest = next(iter(_cache))
        _logger.debug("Evicting cached Shorts for %r", oldest)
        del _cache[oldest]
    _cache[key] = _CacheEntry(fetched_at=now, shorts=tuple(shorts))


def _short_url(video_id: str) -> str:
    return f"https://www.youtube.com/shorts/{video_id}"


def _is_short(detail: VideoDetail) -> bool:
    """A real, finished Short: not a live/upcoming broadcast and within the Shorts length limit."""
    return not detail.live and detail.duration_seconds <= MAX_SHORT_SECONDS


async def fetch_ranked(
    client: VideoSource, query: str, window: Window, category_id: Optional[str] = None
) -> Optional[List[RankedShort]]:
    """Return the Shorts for query in window, most-viewed first, or None if YouTube failed.

    One search plus one batched videos.list call; the details drop live broadcasts and
    anything over MAX_SHORT_SECONDS. Results (including an empty list) are cached for
    CACHE_TTL; a None is not, so the next call retries.
    """
    key = (query, window, category_id)
    now = _now()
    cached = _cache_get(key, now)
    if cached is not None:
        _logger.debug("Shorts cache hit for query=%r window=%s category=%s", query, window.name, category_id)
        return cached
    _logger.debug("Shorts cache miss for query=%r window=%s category=%s", query, window.name, category_id)

    published_after = now - timedelta(days=window.days) if window.days is not None else None
    results = await client.search_shorts(query, published_after=published_after, category_id=category_id)
    if results is None:
        return None

    # search.list occasionally repeats an id; keep the first occurrence so ranks stay unique.
    video_ids = list(dict.fromkeys(result.video_id for result in results))
    details = await client.get_video_details(video_ids)
    if details is None:
        return None

    shorts = [details[video_id] for video_id in video_ids if video_id in details and _is_short(details[video_id])]
    # search.list's viewCount order is approximate; sort on the real counts. sorted() is stable,
    # so ties keep YouTube's order.
    shorts.sort(key=lambda detail: detail.view_count, reverse=True)
    ranked = [
        RankedShort(
            video_id=detail.video_id,
            title=detail.title,
            url=_short_url(detail.video_id),
            view_count=detail.view_count,
        )
        for detail in shorts
    ]
    _logger.info(
        "Ranked %d Short(s) of %d search result(s) for query=%r window=%s category=%s",
        len(ranked),
        len(results),
        query,
        window.name,
        category_id,
    )

    _cache_put(key, ranked, now)
    return ranked


@log.log
async def pick_short(client: VideoSource, chat: "Chat", topics: Sequence[str]) -> PickResult:
    """Return the highest-ranked Short this chat hasn't had recently.

    Without topics this is this week's Gaming chart only. With topics, the joined topics are
    searched across every category, widening WEEK -> MONTH -> ALL_TIME while a window yields
    nothing unseen. A window that fails also widens; the result is only ``unavailable`` when
    no window returned data at all.
    """
    clean_topics = tuple(topic.strip() for topic in topics if topic.strip())
    if clean_topics:
        query = " ".join(clean_topics)
        windows: Tuple[Window, ...] = (Window.WEEK, Window.MONTH, Window.ALL_TIME)
        category_id: Optional[str] = None
    else:
        query = WEEKLY_QUERY
        windows = (Window.WEEK,)
        category_id = GAMING_CATEGORY_ID

    got_data = False
    for window in windows:
        ranked = await fetch_ranked(client, query, window, category_id)
        if ranked is None:
            _logger.warning("Could not fetch Shorts for query=%r window=%s", query, window.name)
            continue
        got_data = True

        for rank, short in enumerate(ranked, start=1):
            if chat.is_recently_posted(short.video_id):
                continue
            _logger.info(
                "Picked Short %s (#%d %s, %d views) for query=%r",
                short.video_id,
                rank,
                window.label,
                short.view_count,
                query,
            )
            return PickResult(
                video=SelectedVideo(
                    video_id=short.video_id,
                    title=short.title,
                    url=short.url,
                    view_count=short.view_count,
                    rank=rank,
                    window=window,
                    topics=clean_topics,
                )
            )
        _logger.debug("No unseen Short among %d for query=%r window=%s", len(ranked), query, window.name)

    if not got_data:
        return PickResult(unavailable=True)
    _logger.info("No unseen Short for query=%r in any window - all empty or already posted", query)
    return PickResult(exhausted=True)
