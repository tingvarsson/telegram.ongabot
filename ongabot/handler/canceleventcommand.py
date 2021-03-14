"""This module contains the CancelEventCommandHandler class."""
import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils.helper import log


_logger = logging.getLogger(__name__)


class CancelEventCommandHandler(CommandHandler):
    """Handler for /cancelevent command"""

    def __init__(self):
        CommandHandler.__init__(self, "cancelevent", callback)


@log
def callback(update: Update, context: CallbackContext):
    """Cancel active event as result of command /cancelevent"""
    # Retrieve currently pinned message
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is None:
        context.bot.send_message(
            update.effective_chat.id, "No event to cancel! Create a new event with /newevent first."
        )
        _logger.debug("Tried to cancel without existing event")
        return

    pinned_poll.unpin()
    context.chat_data["pinned_poll_msg"] = None

    context.bot.send_message(
        update.effective_chat.id,
        pinned_poll.poll.question
        + " \nCancelled successfully. The poll is still accessible in the channel history.",
    )
    _logger.debug("Cancelled event with msg id %s", pinned_poll.message_id)
