"""This module contains the EventPollHandler class."""
import logging

from telegram import Update
from telegram.ext import CallbackContext, PollHandler

import botdata
from utils.log import log


_logger = logging.getLogger(__name__)


class EventPollHandler(PollHandler):
    """Handler for event poll updates"""

    def __init__(self) -> None:
        super().__init__(callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Handle a poll update of an event"""
    _logger.debug("update:\n%s", update)

    event = botdata.get_event(context.bot_data, update.poll.id)
    event.update_poll(update.poll)
    event.update_status_message(context.bot)
