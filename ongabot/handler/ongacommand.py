"""This module contains the OngaCommandHandler class."""
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils.helper import log


class OngaCommandHandler(CommandHandler):
    """Handler for /onga command"""

    def __init__(self):
        CommandHandler.__init__(self, "onga", callback=callback)


@log
def callback(update: Update, _: CallbackContext):
    """Print the image of the one when the true word of /onga is spoken"""
    with open("onga.jpg", "rb") as photo:
        update.message.reply_photo(photo, "All are naked in front of the ONE!")
