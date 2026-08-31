"""This module contains the LinkSteamCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from cs2.steamid import parse_steam64
from utils.commands import LINKSTEAM
from utils.log import log

_logger = logging.getLogger(__name__)


class LinkSteamCommandHandler(CommandHandler):
    """Handler for /linksteam command."""

    def __init__(self) -> None:
        super().__init__("linksteam", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Link the calling user's Steam account, so their CS2 games are recognised.

    Self-service by design: linking publishes this user's match stats to the chat, so it is
    their own consent to give and nobody else's.
    """
    if update.message is None or update.effective_user is None:
        _logger.error("Received /linksteam command without message or effective user")
        return

    if context.user_data is None:
        _logger.error("Received /linksteam command without user data in context")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(LINKSTEAM.usage)
        return

    steam64_id = parse_steam64(args[0])
    if steam64_id is None:
        _logger.info("Rejected /linksteam input from user_id=%s", update.effective_user.id)
        await update.message.reply_text(f"That doesn't look like a Steam64.\n\n{LINKSTEAM.usage}")
        return

    context.user_data.set_steam64_id(steam64_id)
    _logger.info("Linked user_id=%s to steam64_id=%s", update.effective_user.id, steam64_id)
    await update.message.reply_text(
        f"Linked to Steam64 {steam64_id}. Your CS2 games will show up in event results.\n" "Send /unlinksteam to undo."
    )
