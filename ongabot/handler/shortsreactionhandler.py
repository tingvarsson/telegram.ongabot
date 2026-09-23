"""This module contains the ShortsReactionHandler class.

Turns a Telegram reaction left on one of the bot's own posted YouTube Shorts into a topic
score update, so future picks lean toward what a chat has shown it likes. Requires the bot to
be an administrator of the chat - Telegram only sends per-user reaction detail (the
old_reaction/new_reaction diff this handler needs) to admin bots; a non-admin bot only sees
aggregate counts and this handler never fires. It also requires main() to opt into
message_reaction updates via allowed_updates, since they are not delivered by default.
"""

import logging

from telegram import Update
from telegram.ext import CallbackContext, MessageReactionHandler

from chat import Chat
from utils.log import log
from youtube.reactions import reaction_score_delta
from youtube.topics import apply_reaction

_logger = logging.getLogger(__name__)


class ShortsReactionHandler(MessageReactionHandler):
    """Handler for reactions left on a posted YouTube Short."""

    def __init__(self) -> None:
        super().__init__(callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Score a chat's topic preferences from a reaction left on one of its posted Shorts."""
    reaction = update.message_reaction
    if reaction is None:
        return

    chat: Chat = context.bot_data.get_chat(reaction.chat.id)
    posted = chat.posted_shorts.get(reaction.message_id)
    if posted is None:
        # A reaction on some other message, or one old enough to have aged out of history.
        _logger.debug(
            "chat_id=%s: reaction on message_id=%s is not a tracked Short; ignoring",
            chat.chat_id,
            reaction.message_id,
        )
        return

    delta = reaction_score_delta(reaction.old_reaction, reaction.new_reaction)
    if delta == 0.0:
        _logger.debug(
            "chat_id=%s: reaction on message_id=%s (video_id=%s) nets to no score change; ignoring",
            chat.chat_id,
            reaction.message_id,
            posted.video_id,
        )
        return

    apply_reaction(chat.topic_scores, posted.topics, delta)
    _logger.info(
        "chat_id=%s topics=%s delta=%+.2f (video_id=%s, message_id=%s)",
        chat.chat_id,
        posted.topics,
        delta,
        posted.video_id,
        reaction.message_id,
    )
