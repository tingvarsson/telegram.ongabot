"""Pick one eligible YouTube Short for a chat's daily post.

Domain layer: decides which search hit to use, holds no HTTP knowledge (ongabot.youtube.client
does the I/O) and no Telegram knowledge (ongabot.ongabot posts the result). Ties the client to
a chat's dedup history and extracts the topics a later reaction can be attributed back to.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol, Sequence, Tuple

from youtube.client import SearchResult, VideoDetail
from youtube.topics import extract_topics
from utils import log

if TYPE_CHECKING:  # pragma: no cover - import cycle: chat -> ... -> youtube.selection
    from chat import Chat

_logger = logging.getLogger(__name__)

# YouTube's own definition of a Short.
MAX_SHORT_SECONDS = 60


@dataclass(frozen=True)
class SelectedVideo:
    """The Short chosen for today's post, with the topics it should be attributed to."""

    video_id: str
    title: str
    url: str
    topics: Tuple[str, ...]


@dataclass(frozen=True)
class PostedShort:
    """A record of a posted Short, kept on Chat so a later reaction can be scored against it."""

    video_id: str
    topics: Tuple[str, ...]
    posted_at: datetime


class VideoSource(Protocol):
    """The slice of ongabot.youtube.client.YouTubeClient this module needs."""

    async def search_shorts(self, query: str, max_results: int = 10) -> Optional[List[SearchResult]]:
        """Return candidate Shorts matching query, or None if unavailable."""

    async def get_video_details(self, video_ids: Sequence[str]) -> Optional[Dict[str, VideoDetail]]:
        """Return duration/tags/title for each id, or None if unavailable."""


def _short_url(video_id: str) -> str:
    return f"https://www.youtube.com/shorts/{video_id}"


@log.log
async def pick_short(client: VideoSource, chat: "Chat", topic: str) -> Optional[SelectedVideo]:
    """Search topic and return the first eligible, not-recently-posted Short under 60s.

    Returns None when the search fails, comes up empty, every hit was already posted to this
    chat recently, or none of the remaining candidates is actually Short-length - the caller
    treats None as "try again" rather than an error.
    """
    results = await client.search_shorts(topic)
    if not results:
        _logger.debug("No search results for topic=%r", topic)
        return None

    candidates = [result for result in results if not chat.is_recently_posted(result.video_id)]
    if not candidates:
        _logger.debug("All %d result(s) for topic=%r were already posted recently", len(results), topic)
        return None

    details = await client.get_video_details([result.video_id for result in candidates])
    if not details:
        return None

    for result in candidates:
        detail = details.get(result.video_id)
        if detail is None or detail.duration_seconds > MAX_SHORT_SECONDS:
            continue
        topics = extract_topics(detail.title, detail.tags)
        return SelectedVideo(
            video_id=detail.video_id,
            title=detail.title,
            url=_short_url(detail.video_id),
            topics=topics,
        )

    _logger.debug(
        "No eligible Short (<=%ds) for topic=%r among %d candidate(s)", MAX_SHORT_SECONDS, topic, len(candidates)
    )
    return None
