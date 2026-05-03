"""This module contains the AuthorizeCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from utils.auth import get_bot_admins
from utils.log import log

_logger = logging.getLogger(__name__)


class AuthorizeCommandHandler(CommandHandler):
    """Handler for /authorize command"""

    def __init__(self) -> None:
        super().__init__("authorize", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Authorize the current chat to use the bot"""
    if update.effective_user.id not in get_bot_admins():
        await update.message.reply_text("You are not allowed to do that.")
        return

    chat_id = update.effective_chat.id
    context.bot_data.authorize_chat(chat_id)
    await update.message.reply_text(f"Chat {chat_id} is now authorized to use ONGAbot.")
    _logger.info("Chat %s authorized by user %s", chat_id, update.effective_user.id)
