"""This module contains the Cs2CommandHandler class."""

import logging
from datetime import date
from typing import List, Optional

from telegram import LinkPreviewOptions, Message, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from cs2.leetify import get_client
from cs2.report import event_results, latest_reportable_event
from utils import helper
from utils.commands import CS2
from utils.dm import resolve_group
from utils.log import log

_logger = logging.getLogger(__name__)

_ALLOWED_ARGS = {"target_date"}


class Cs2CommandHandler(CommandHandler):
    """Handler for /cs2 command."""

    def __init__(self) -> None:
        super().__init__("cs2", callback)


def _parse_target_date(args: List[str]) -> Optional[date]:
    """The date named in the command args, or None for the latest event. Raises ValueError."""
    if not args:
        return None
    named = helper.parse_named_args(args, _ALLOWED_ARGS)
    return helper.parse_date(named["target_date"])


async def send_cs2(message: Message, context: CallbackContext, chat: Chat, event_date: Optional[date]) -> None:
    """Reply to message with chat's CS2 results for event_date (None: the latest completed event)."""
    if event_date is None:
        event = latest_reportable_event(chat)
        if event is None:
            await message.reply_text("No completed event to report on yet.")
            return
        event_date = event.event_date

    _, text = await event_results(get_client(), chat, event_date, context.application.user_data)
    if text is None:
        _logger.warning("CS2 results unavailable for chat_id=%s on %s", chat.chat_id, event_date)
        await message.reply_text("Couldn't reach Leetify right now - try again in a bit.")
        return

    await message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        # The per-match Leetify links would otherwise each drag in a preview card.
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        # A results report reads as a standalone message, not an answer to the command itself.
        do_quote=False,
    )


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the CS2 results for a date, as result of /cs2 [<date>|target_date=<date>]"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /cs2 command without message or effective chat")
        return

    # Parsed before the group is known, so a bad date is answered right away instead of after
    # a group pick. The picker then carries the resolved ISO date, which keeps its button data
    # short however the user typed the date (a weekday resolves to the date it meant today).
    try:
        event_date = _parse_target_date(context.args or [])
    except ValueError as e:
        await update.message.reply_text(f"{e}\n\n{CS2.usage}")
        return

    chat = await resolve_group(update, context, CS2.command, event_date.isoformat() if event_date else "")
    if chat is None:
        return
    await send_cs2(update.message, context, chat, event_date)
