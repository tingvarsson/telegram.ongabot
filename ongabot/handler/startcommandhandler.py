"""This module contains the StartCommandHandler class."""

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from utils import helper
from utils.dm import private_commands_only
from utils.log import log


class StartCommandHandler(CommandHandler):
    """Handler for /start command"""

    def __init__(self) -> None:
        super().__init__("start", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Print the help text for a /start or /help command"""
    await update.message.reply_text(helper.create_help_text(private=private_commands_only(update, context)))
