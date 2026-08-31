"""This module contains the UnLinkSteamCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from utils.log import log

_logger = logging.getLogger(__name__)


class UnLinkSteamCommandHandler(CommandHandler):
    """Handler for /unlinksteam command."""

    def __init__(self) -> None:
        super().__init__("unlinksteam", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Unlink the calling user's Steam account."""
    if update.message is None or update.effective_user is None:
        _logger.error("Received /unlinksteam command without message or effective user")
        return

    if context.user_data is None:
        _logger.error("Received /unlinksteam command without user data in context")
        return

    was_linked = context.user_data.steam64_id is not None
    context.user_data.set_steam64_id(None)
    _logger.info("Unlinked user_id=%s (was_linked=%s)", update.effective_user.id, was_linked)

    if was_linked:
        await update.message.reply_text("Steam account unlinked. Your CS2 games will no longer be shown.")
    else:
        await update.message.reply_text("You don't have a Steam account linked.")
