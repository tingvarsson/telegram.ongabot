"""This module contains the StatisticsCommandHandler class."""

import logging

from telegram import Message, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from utils.commands import STATISTICS
from utils.dm import resolve_group
from utils.log import log
from utils.statistics import render_statistics_message

_logger = logging.getLogger(__name__)


class StatisticsCommandHandler(CommandHandler):
    """Handler for /statistics command."""

    def __init__(self) -> None:
        super().__init__("statistics", callback)


async def send_statistics(message: Message, chat: Chat) -> None:
    """Reply to message with chat's statistics table, in the group or in a private chat."""
    in_private_chat = message.chat.type == ChatType.PRIVATE
    text, keyboard = render_statistics_message(chat, in_private_chat=in_private_chat)
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with all-time participation statistics for the group, as result of /statistics"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /statistics command without message or effective chat")
        return

    chat = await resolve_group(update, context, STATISTICS.command)
    if chat is None:
        return
    await send_statistics(update.message, chat)
