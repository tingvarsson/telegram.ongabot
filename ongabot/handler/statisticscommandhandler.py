"""This module contains the StatisticsCommandHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from utils.log import log
from utils.statistics import render_statistics_message

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

    text, keyboard = render_statistics_message(chat)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
