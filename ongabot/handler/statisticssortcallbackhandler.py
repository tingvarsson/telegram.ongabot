"""This module contains the StatisticsSortCallbackHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackContext, CallbackQueryHandler

from utils.dm import GROUP_UNAVAILABLE, can_read_group, is_private_chat
from utils.log import log
from utils.statistics import CALLBACK_DATA_PREFIX, render_statistics_message

_logger = logging.getLogger(__name__)

# Matches any key, not just today's SORT_COLUMNS: a column renamed or removed in a later
# deploy must still route here so a stale button (from a message sent before that deploy)
# falls back to the default sort (see format_statistics's _COLUMNS_BY_KEY.get fallback)
# instead of going dead - Telegram would otherwise spin the tapped button forever since
# answer() would never be called.
# The optional trailing chat id is set on tables sent to a private chat (see build_sort_keyboard).
CALLBACK_PATTERN = rf"^{CALLBACK_DATA_PREFIX}:(\w+)(?::(-?\d+))?$"


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

    sort_by, _, group_id = query.data.removeprefix(f"{CALLBACK_DATA_PREFIX}:").partition(":")
    private = is_private_chat(update)
    if not private:
        # Always the group the tap came from. A group's table never carries a group id, and
        # callback data can be forged, so one found here must not pull in another group.
        chat_id = update.effective_chat.id
    elif not group_id:
        # No group on the button and the private chat has no statistics of its own.
        _logger.warning("Statistics sort tap in private chat_id=%s without a group", update.effective_chat.id)
        await query.answer()
        return
    else:
        # A table in a private chat: re-check the tapper may still read that group.
        chat_id = int(group_id)
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is None or not await can_read_group(context.bot, context.bot_data, chat_id, user_id):
            _logger.info("Refused statistics re-sort of chat_id=%s for user_id=%s", chat_id, user_id)
            await query.answer(GROUP_UNAVAILABLE)
            return

    await query.answer()

    chat = context.bot_data.get_chat(chat_id)
    text, keyboard = render_statistics_message(chat, sort_by=sort_by, in_private_chat=private)

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
        _logger.debug("Statistics table unchanged after re-sort by %s; ignoring", sort_by)
