"""This module contains the TopicsCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
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


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with this chat's learned YouTube Short topic preferences, as result of /topics"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /topics command without message or effective chat")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    await update.message.reply_text(_render_topics(chat))
