"""This module contains the EventPollHandler class."""
import logging
from telegram import Update
from telegram.ext import PollHandler, CallbackContext

from utils.helper import log


class EventPollHandler(PollHandler):
    """Handler for event poll updates"""

    def __init__(self):
        PollHandler.__init__(self, callback=callback)


@log
def callback(update: Update, context: CallbackContext):
    """Handle an poll update"""
    logger = logging.getLogger()
    logger.debug("ENTER: EventPollHandler::callback")
    logger.debug("update:")
    logger.debug("%s", update)
    # Update stored poll_data
    poll_data = context.bot_data[update.poll.id]
    poll_data["poll"] = update.poll
    context.bot_data.update(poll_data)

    logger.debug("context.bot_data:")
    logger.debug("%s", context.bot_data)
    logger.debug("EXIT: EventPollHandler::callback")
