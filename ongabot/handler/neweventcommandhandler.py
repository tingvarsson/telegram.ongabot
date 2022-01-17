"""This module contains the NewEventCommandHandler class."""
import logging
from datetime import date

from telegram import TelegramError, Update
from telegram.ext import CommandHandler, CallbackContext

<<<<<<< HEAD
import botdata
from event import Event

from utils import helper
=======
from event import create_event
>>>>>>> 5942646 ([ongabot] Move pinned_poll to bot_chat and some formatting)
from utils.log import log


_logger = logging.getLogger(__name__)


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self) -> None:
        super().__init__("newevent", callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Create a poll as result of command /newevent"""
    _logger.debug("update:\n%s", update)

    create_event(context, update.effective_chat.id)
