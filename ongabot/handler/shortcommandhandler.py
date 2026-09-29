"""This module contains the ShortCommandHandler class."""

import logging
from datetime import datetime
from typing import List, Sequence

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackContext, CommandHandler

from botdata import BotData
from utils.commands import SHORT
from utils.log import log
from youtube import selection
from youtube.client import get_client
from youtube.selection import SelectedVideo

_logger = logging.getLogger(__name__)

UNAVAILABLE_TEXT = "Couldn't reach YouTube right now - try again in a bit."

# The topics are echoed back in the reply, so a cap keeps it far below Telegram's message limit
# and the search query sane. Stated in SHORT.usage.
MAX_TOPICS_LENGTH = 100

# What the chat has run out of, named in the exhausted reply when no topics were given.
WEEKLY_SCOPE = "this week's gaming list"

# Compact view-count suffixes, largest first.
_VIEW_UNITS = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))


class ShortCommandHandler(CommandHandler):
    """Handler for /short command"""

    def __init__(self) -> None:
        # Non-blocking: a cache miss makes a search plus a videos.list call to YouTube, which
        # can take a few seconds, and the application processes updates one at a time otherwise.
        super().__init__("short", callback, block=False)


def format_views(count: int) -> str:
    """Compact view count: 999, 1.2K, 12.4M, 3B - one decimal, a trailing .0 dropped."""
    for index, (size, suffix) in enumerate(_VIEW_UNITS):
        if count < size:
            continue
        value = round(count / size, 1)
        # 999_960 rounds to 1000.0K; show it as the next unit up instead.
        if value >= 1000 and index > 0:
            size, suffix = _VIEW_UNITS[index - 1]
            value = round(count / size, 1)
        return f"{value:g}{suffix}"
    return str(count)


def render_short_message(video: SelectedVideo, topics: Sequence[str]) -> str:
    """The /short post: a header with rank, window and views, then the URL on its own line.

    Plain text, so Telegram shows its video preview for the link. The header reads
    "#3 this week · 12.4M views", or "#1 for counter strike this month · 3.1M views" with topics.
    """
    views = f"{format_views(video.view_count)} {'view' if video.view_count == 1 else 'views'}"
    scope = f" for {' '.join(topics)}" if topics else ""
    return f"#{video.rank}{scope} {video.window.label} · {views}\n{video.url}"


def render_exhausted_message(topics: Sequence[str]) -> str:
    """Reply when every Short found was already posted to the chat within the no-repeat period."""
    if topics:
        return f"You've already had every top Short I could find for {' '.join(topics)} - try other topics."
    return f"You've already had every top Short I could find for {WEEKLY_SCOPE} - try some topics."


def _parse_topics(args: Sequence[str]) -> List[str]:
    """The /short arguments as search topics: lowercased, stripped, empties dropped."""
    return [topic for topic in (arg.strip().lower() for arg in args) if topic]


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Post the top Short this chat hasn't had yet, as result of /short"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /short command without message or effective chat")
        return

    chat_id = update.effective_chat.id
    topics = _parse_topics(context.args or [])
    if len(" ".join(topics)) > MAX_TOPICS_LENGTH:
        _logger.info("Rejected /short in chat_id=%s: topics longer than %d characters", chat_id, MAX_TOPICS_LENGTH)
        await update.message.reply_text(SHORT.usage)
        return

    bot_data: BotData = context.bot_data
    chat = bot_data.get_chat(chat_id)

    result = await selection.pick_short(get_client(), chat, topics)
    if result.video is None:
        text = UNAVAILABLE_TEXT if result.unavailable else render_exhausted_message(topics)
        _logger.info(
            "No Short to post to chat_id=%s for topics=%r (unavailable=%s, exhausted=%s)",
            chat_id,
            topics,
            result.unavailable,
            result.exhausted,
        )
        await update.message.reply_text(text)
        return

    video = result.video
    # Recorded before the send, with no await in between since the pick: this handler is
    # non-blocking, so a second /short sent while this one's send is in flight would otherwise
    # pick the same Short from the cached list and post it twice.
    chat.record_shorts_post(video.video_id, datetime.now())
    try:
        # A Short reads as a post of its own, not an answer to the command message itself.
        await update.message.reply_text(render_short_message(video, topics), do_quote=False)
    except TelegramError as e:
        # Forgotten again, so the chat can still get this Short on the next /short.
        chat.forget_shorts_post(video.video_id)
        _logger.error("Failed to post Short video_id=%s to chat_id=%s: %s", video.video_id, chat_id, e)
        return

    _logger.info(
        "Posted Short video_id=%s to chat_id=%s (#%d %s, query=%r)",
        video.video_id,
        chat_id,
        video.rank,
        video.window.name,
        " ".join(topics) or selection.WEEKLY_QUERY,
    )
