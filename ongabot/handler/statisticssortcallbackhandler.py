"""This module contains the StatisticsSortCallbackHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackContext, CallbackQueryHandler

from utils.log import log
from utils.statistics import CALLBACK_DATA_PREFIX, SORT_COLUMNS, render_statistics_message

_logger = logging.getLogger(__name__)

_SORT_KEYS_PATTERN = "|".join(c.key for c in SORT_COLUMNS)
CALLBACK_PATTERN = rf"^{CALLBACK_DATA_PREFIX}:({_SORT_KEYS_PATTERN})$"


class StatisticsSortCallbackHandler(CallbackQueryHandler):
    """Handler for tap-to-sort taps on the /statistics table's inline keyboard."""

    def __init__(self) -> None:
        super().__init__(callback, pattern=CALLBACK_PATTERN)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Re-render the statistics table sorted by the tapped column, in place."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_chat is None:
        _logger.error("Received statistics sort callback without query/data/effective_chat")
        return

    await query.answer()

    sort_by = query.data.removeprefix(f"{CALLBACK_DATA_PREFIX}:")
    chat_id = update.effective_chat.id
    chat = context.bot_data.get_chat(chat_id)

    text, keyboard = render_statistics_message(chat, sort_by=sort_by)

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
        _logger.debug("Statistics table unchanged after re-sort by %s; ignoring", sort_by)
