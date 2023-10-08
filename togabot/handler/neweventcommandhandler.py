"""This module contains the NewEventCommandHandler class."""
import logging

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from eventcreator import create_event
from utils.log import log


_logger = logging.getLogger(__name__)


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self) -> None:
        super().__init__("newevent", callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Create a poll as result of command /newevent"""
    create_event(context, update.effective_chat.id)
