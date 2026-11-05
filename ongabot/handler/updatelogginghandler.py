"""This module contains the UpdateLoggingHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, TypeHandler

from utils.updatesummary import describe_update

_logger = logging.getLogger(__name__)


class UpdateLoggingHandler(TypeHandler):
    """Handler that logs a one-line summary of every incoming update.

    Registered in a group ahead of the authorization gate, so updates the gate goes on to block
    are logged as well. It never stops an update, so the handlers after it still run.
    """

    def __init__(self) -> None:
        super().__init__(Update, callback)


async def callback(update: Update, _: CallbackContext) -> None:
    """Log what the update is and who sent it."""
    level, summary = describe_update(update)
    _logger.log(level, "Update %s: %s", update.update_id, summary)
