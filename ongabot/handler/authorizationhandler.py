"""This module contains the AuthorizationHandler class."""

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ApplicationHandlerStop, CallbackContext, TypeHandler

from utils.auth import get_bot_admins
from utils.commands import PRIVATE_COMMAND_NAMES, PRIVATE_COMMANDS
from utils.dm import DM_PICK_PREFIX
from utils.log import log
from utils.statistics import CALLBACK_DATA_PREFIX as STATS_SORT_PREFIX

_logger = logging.getLogger(__name__)

NOT_ENABLED = "This bot is not enabled for this chat. Contact the bot administrator."

PRIVATE_CHAT_HINT = "In a private chat I answer these, about your group, without posting in it:\n" + " ".join(
    f"/{cmd.command}" for cmd in PRIVATE_COMMANDS
)

# Inline buttons a private chat may tap. Their handlers check that the tapper may still read
# the group the button is about, so the gate does not have to.
_PRIVATE_CALLBACK_PREFIXES = {DM_PICK_PREFIX, STATS_SORT_PREFIX}


class AuthorizationHandler(TypeHandler):
    """Handler that gates all updates to authorized chats only."""

    def __init__(self) -> None:
        super().__init__(Update, callback)


def _command(update: Update) -> str | None:
    """The command an update's message starts with, lowercased and without @botname."""
    msg = update.effective_message
    if msg and msg.text and msg.text.startswith("/"):
        return msg.text.split()[0].split("@")[0].lower()
    return None


def _allowed_in_private_chat(update: Update) -> bool:
    """True for the updates an unauthorized private chat may send: private commands and their buttons."""
    query = update.callback_query
    if query is not None:
        return query.data is not None and query.data.split(":", 1)[0] in _PRIVATE_CALLBACK_PREFIXES
    command = _command(update)
    return command is not None and command.removeprefix("/") in PRIVATE_COMMAND_NAMES


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Block updates from chats that are not authorized."""
    chat = update.effective_chat
    if chat is None:
        return  # PollAnswer updates carry no chat; let them through

    # Allow bot admins to run /authorize and /deauthorize in any chat
    if _command(update) in ("/authorize", "/deauthorize"):
        if update.effective_user and update.effective_user.id in get_bot_admins():
            return

    if context.bot_data.is_authorized(chat.id):
        return

    private = chat.type == ChatType.PRIVATE
    if private and _allowed_in_private_chat(update):
        return

    msg = update.effective_message
    if msg:
        await msg.reply_text(PRIVATE_CHAT_HINT if private else NOT_ENABLED)
    raise ApplicationHandlerStop()
