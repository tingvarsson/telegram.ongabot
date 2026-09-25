"""This module contains the TopicsCommandHandler class."""

import logging

from telegram import Message, Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from utils.commands import TOPICS
from utils.dm import resolve_group
from utils.log import log

_logger = logging.getLogger(__name__)


class TopicsCommandHandler(CommandHandler):
    """Handler for /topics command."""

    def __init__(self) -> None:
        super().__init__("topics", callback)


def _render_topics(chat: Chat) -> str:
    if not chat.topic_scores:
        return "No topic preferences learned yet - check back after a few daily Shorts."
    ranked = sorted(chat.topic_scores.items(), key=lambda item: item[1], reverse=True)
    return "\n".join(f"{topic}: {score:.2f}" for topic, score in ranked)


async def send_topics(message: Message, chat: Chat) -> None:
    """Reply to message with chat's learned topic preferences, in the group or in a private chat."""
    await message.reply_text(_render_topics(chat))


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the group's learned YouTube Short topic preferences, as result of /topics"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /topics command without message or effective chat")
        return

    chat = await resolve_group(update, context, TOPICS.command)
    if chat is None:
        return
    await send_topics(update.message, chat)
