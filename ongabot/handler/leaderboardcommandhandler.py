"""This module contains the LeaderboardCommandHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from utils.log import log
from utils.points import render_leaderboard_message

_logger = logging.getLogger(__name__)


class LeaderboardCommandHandler(CommandHandler):
    """Handler for /leaderboard command."""

    def __init__(self) -> None:
        super().__init__("leaderboard", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the Banger Points leaderboard for this chat."""
    chat_id = update.effective_chat.id
    chat = context.bot_data.get_chat(chat_id)

    text = render_leaderboard_message(chat)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
