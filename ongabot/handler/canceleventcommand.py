"""This module contains the CancelEventCommandHandler class."""
import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext


class CancelEventCommandHandler(CommandHandler):
    """Handler for /cancelevent command"""

    def __init__(self):
        CommandHandler.__init__(self, "cancelevent", callback)


def callback(update: Update, context: CallbackContext):
    """Cancel active event as result of command /cancelevent"""
    logger = logging.getLogger()
    logger.debug("ENTER: CancelEventCommandHandler::callback")

    # Retrieve currently pinned message
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is None:
        context.bot.send_message(
            update.effective_chat.id, "No event to cancel! Create a new event with /newevent first."
        )
        logger.debug("Tried to cancel without existing event")
        logger.debug("EXIT: CancelEventCommandHandler::callback")
        return

    pinned_poll.unpin()
    context.chat_data["pinned_poll_msg"] = None

    context.bot.send_message(
        update.effective_chat.id,
        pinned_poll.poll.question
        + " \nCancelled successfully. The poll is still accessible in the channel history.",
    )
    logger.debug("Cancelled event with msg id %s", pinned_poll.message_id)
    logger.debug("EXIT: CancelEventCommandHandler::callback")
