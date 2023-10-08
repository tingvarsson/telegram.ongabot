"""This module contains the TogaCommandHandler class."""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils.log import log


class TogaCommandHandler(CommandHandler):
    """Handler for /toga command"""

    def __init__(self) -> None:
        super().__init__("toga", callback=callback)


@log
def callback(update: Update, _: CallbackContext) -> None:
    """Print the image of the one when the true word of /toga is spoken"""
    with open("toga.jpg", "rb") as photo:
        update.message.reply_photo(photo, "PICKLES")
