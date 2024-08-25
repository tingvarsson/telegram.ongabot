"""This module contains the CancelEventCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from chat import Chat
from utils.log import log


_logger = logging.getLogger(__name__)


class CancelEventCommandHandler(CommandHandler):
    """Handler for /cancelevent command"""

    def __init__(self) -> None:
        super().__init__("cancelevent", callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Cancel active event as result of command /cancelevent"""
    # Retrieve currently pinned message
    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    pinned_poll = chat.get_pinned_poll()

    if pinned_poll is None:
        context.bot.send_message(
            update.effective_chat.id,
            "No known event to cancel! Create a new event with /newevent.",
        )
        _logger.debug("Tried to cancel without existing event.")
        return

    chat.remove_pinned_poll()

    context.bot.send_message(
        update.effective_chat.id,
        pinned_poll.poll.question
        + " \nCancelled successfully. The poll is still accessible in the channel history.",
    )
    _logger.debug("Cancelled event with msg id %s", pinned_poll.message_id)
