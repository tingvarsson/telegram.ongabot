"""This module contains the StatisticsCommandHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from utils.log import log
from utils.statistics import compute_statistics, format_statistics

_logger = logging.getLogger(__name__)


class StatisticsCommandHandler(CommandHandler):
    """Handler for /statistics command."""

    def __init__(self) -> None:
        super().__init__("statistics", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with all-time participation statistics for this chat."""
    chat_id = update.effective_chat.id
    chat = context.bot_data.get_chat(chat_id)
    chat_member_count = await context.bot.get_chat_member_count(chat_id)

    result = compute_statistics(chat, chat_member_count)
    await update.message.reply_text(format_statistics(result), parse_mode=ParseMode.MARKDOWN_V2)
