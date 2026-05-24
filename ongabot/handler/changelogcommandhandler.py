"""This module contains the ChangelogCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from _version import __version__
from utils.changelog import get_version_entry
from utils.log import log

_logger = logging.getLogger(__name__)


class ChangelogCommandHandler(CommandHandler):
    """Handler for /changelog command."""

    def __init__(self) -> None:
        super().__init__("changelog", callback)


@log
async def callback(update: Update, _: CallbackContext) -> None:
    """Reply with the changelog entry for the current bot version."""
    entry = get_version_entry(__version__)
    await update.message.reply_text(entry)
