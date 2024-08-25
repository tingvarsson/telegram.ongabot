"""This module contains the HelpCommandHandler class."""

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils import helper
from utils.log import log


class HelpCommandHandler(CommandHandler):
    """Handler for /help command"""

    def __init__(self) -> None:
        super().__init__("help", callback)


@log
def callback(update: Update, _: CallbackContext) -> None:
    """Print the help text for a /start or /help command"""
    update.message.reply_text(helper.create_help_text())
