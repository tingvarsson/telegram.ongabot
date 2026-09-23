"""This module contains the Cs2CommandHandler class."""

import logging
from datetime import date
from typing import Optional

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from cs2.leetify import get_client
from cs2.report import event_results, latest_reportable_event
from utils import helper
from utils.commands import CS2
from utils.log import log

_logger = logging.getLogger(__name__)

_ALLOWED_ARGS = {"target_date"}


class Cs2CommandHandler(CommandHandler):
    """Handler for /cs2 command."""

    def __init__(self) -> None:
        super().__init__("cs2", callback)


async def _resolve_event_date(update: Update, context: CallbackContext, chat: Chat) -> Optional[date]:
    """Pick the date to report on, replying with the reason when there isn't one."""
    args = context.args or []
    if args:
        try:
            named = helper.parse_named_args(args, _ALLOWED_ARGS)
            return helper.parse_date(named["target_date"])
        except ValueError as e:
            await update.message.reply_text(f"{e}\n\n{CS2.usage}")
            return None

    event = latest_reportable_event(chat)
    if event is None:
        await update.message.reply_text("No completed event to report on yet.")
        return None
    return event.event_date


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the CS2 results for a date, as result of /cs2 [<date>|target_date=<date>]"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /cs2 command without message or effective chat")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)

    event_date = await _resolve_event_date(update, context, chat)
    if event_date is None:
        return

    _, text = await event_results(get_client(), chat, event_date, context.application.user_data)
    if text is None:
        _logger.warning("CS2 results unavailable for chat_id=%s on %s", chat.chat_id, event_date)
        await update.message.reply_text("Couldn't reach Leetify right now - try again in a bit.")
        return

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        # The per-match Leetify links would otherwise each drag in a preview card.
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        # A results report reads as a standalone message, not an answer to the command itself.
        do_quote=False,
    )
