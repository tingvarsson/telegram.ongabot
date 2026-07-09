"""This module contains the ChangelogCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from _version import __version__
from utils.changelog import get_changelog
from utils.commands import CHANGELOG
from utils.log import log

_logger = logging.getLogger(__name__)


class ChangelogCommandHandler(CommandHandler):
    """Handler for /changelog command."""

    def __init__(self) -> None:
        super().__init__("changelog", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the last N changelog entries (default 1) as seen from this build."""
    count = 1
    if context.args:
        arg = context.args[0]
        if not arg.isdigit() or int(arg) < 1:
            await update.message.reply_text(CHANGELOG.usage)
            return
        count = int(arg)
    entry = get_changelog(__version__, count)
    await update.message.reply_text(entry)
