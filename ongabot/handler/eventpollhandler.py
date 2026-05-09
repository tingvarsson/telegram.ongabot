"""This module contains the EventPollHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, PollHandler

from utils.log import log

_logger = logging.getLogger(__name__)


class EventPollHandler(PollHandler):
    """Handler for event poll updates"""

    def __init__(self) -> None:
        super().__init__(callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Handle a poll update of an event"""
    if update.poll is None:
        _logger.error("Received poll update without poll")
        return

    event = context.bot_data.get_event(update.poll.id)
    if event is None:
        return
    event.update_poll(update.poll)
    await event.update_status_message(context.bot)
