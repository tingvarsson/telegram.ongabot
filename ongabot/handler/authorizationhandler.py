"""This module contains the AuthorizationHandler class."""

import logging

from telegram import Update
from telegram.ext import ApplicationHandlerStop, CallbackContext, TypeHandler

from utils.auth import get_bot_admins
from utils.log import log

_logger = logging.getLogger(__name__)


class AuthorizationHandler(TypeHandler):
    """Handler that gates all updates to authorized chats only."""

    def __init__(self) -> None:
        super().__init__(Update, callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Block updates from chats that are not authorized."""
    chat = update.effective_chat
    if chat is None:
        return  # PollAnswer updates carry no chat; let them through

    # Allow bot admins to run /authorize and /deauthorize in any chat
    msg = update.effective_message
    if msg and msg.text:
        cmd = msg.text.split()[0].split("@")[0].lower()
        if cmd in ("/authorize", "/deauthorize"):
            if update.effective_user and update.effective_user.id in get_bot_admins():
                return

    if not context.bot_data.is_authorized(chat.id):
        if msg:
            await msg.reply_text(
                "This bot is not enabled for this chat. Contact the bot administrator."
            )
        raise ApplicationHandlerStop()
