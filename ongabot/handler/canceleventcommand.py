"""This module contains the CancelEventCommandHandler class."""
import logging
from datetime import date
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from .neweventcommand import get_upcoming_wednesday_date


class CancelEventCommandHandler(CommandHandler):
    """Handler for /cancelevent command"""

    def __init__(self):
        CommandHandler.__init__(self, "cancelevent", callback)


def callback(update: Update, context: CallbackContext):
    """Cancel active event as result of command /cancelevent"""
    logger = logging.getLogger()

    # Retrieve currently pinned message
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is not None:
        pinned_poll.unpin()
        context.chat_data["pinned_poll_msg"] = None

        context.bot.send_message(
            update.effective_chat.id,
            "Event for "
            + get_upcoming_wednesday_date(date.today()).strftime("%Y-%m-%d")
            + " cancelled successfully. The poll is still accessible in the channel history.",
        )
        logger.debug("Cancelled event with msg id %s", pinned_poll.msg.id)
    else:
        context.bot.send_message(
            update.effective_chat.id, "No event to cancel! Create a new event with /newevent first."
        )
        logger.debug("Tried to cancel without existing event")
