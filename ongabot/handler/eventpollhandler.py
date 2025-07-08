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
    event = context.bot_data.get_event(update.poll.id)
    event.update_poll(update.poll)
    event.update_status_message(context.bot)
