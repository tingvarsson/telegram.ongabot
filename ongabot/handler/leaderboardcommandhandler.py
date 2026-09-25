"""This module contains the LeaderboardCommandHandler class."""

import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from utils.commands import LEADERBOARD
from utils.dm import resolve_group
from utils.log import log
from utils.points import render_leaderboard_message

_logger = logging.getLogger(__name__)


class LeaderboardCommandHandler(CommandHandler):
    """Handler for /leaderboard command."""

    def __init__(self) -> None:
        super().__init__("leaderboard", callback)


async def send_leaderboard(message: Message, chat: Chat) -> None:
    """Reply to message with chat's Banger Points leaderboard, in the group or in a private chat."""
    text = render_leaderboard_message(chat)
    # A leaderboard reads as a standalone report, not an answer to the command message itself.
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, do_quote=False)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the Banger Points leaderboard for the group, as result of /leaderboard"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /leaderboard command without message or effective chat")
        return

    chat = await resolve_group(update, context, LEADERBOARD.command)
    if chat is None:
        return
    await send_leaderboard(update.message, chat)
