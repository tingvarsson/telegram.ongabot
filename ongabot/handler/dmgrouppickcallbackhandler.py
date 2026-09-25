"""This module contains the DmGroupPickCallbackHandler class."""

import logging
from datetime import date
from typing import Awaitable, Callable, Dict

from telegram import Message, Update
from telegram.ext import CallbackContext, CallbackQueryHandler

from chat import Chat
from utils.commands import CS2, LEADERBOARD, STATISTICS, TOPICS
from utils.dm import DM_PICK_PREFIX, NO_LONGER_IN_GROUP, can_read_group, decode_pick, group_title
from utils.log import log

from .cs2commandhandler import send_cs2
from .leaderboardcommandhandler import send_leaderboard
from .statisticscommandhandler import send_statistics
from .topicscommandhandler import send_topics

_logger = logging.getLogger(__name__)

CALLBACK_PATTERN = rf"^{DM_PICK_PREFIX}:"

# (message to reply to, context, the picked group, the arg the picker carried)
Sender = Callable[[Message, CallbackContext, Chat, str], Awaitable[None]]


async def _statistics(message: Message, _context: CallbackContext, chat: Chat, _arg: str) -> None:
    await send_statistics(message, chat)


async def _leaderboard(message: Message, _context: CallbackContext, chat: Chat, _arg: str) -> None:
    await send_leaderboard(message, chat)


async def _topics(message: Message, _context: CallbackContext, chat: Chat, _arg: str) -> None:
    await send_topics(message, chat)


async def _cs2(message: Message, context: CallbackContext, chat: Chat, arg: str) -> None:
    await send_cs2(message, context, chat, date.fromisoformat(arg) if arg else None)


# Every command whose private-chat reply can go through the group picker (utils.dm.resolve_group).
SENDERS: Dict[str, Sender] = {
    STATISTICS.command: _statistics,
    LEADERBOARD.command: _leaderboard,
    TOPICS.command: _topics,
    CS2.command: _cs2,
}


class DmGroupPickCallbackHandler(CallbackQueryHandler):
    """Handler for a tap on the group picker a read command sends in a private chat."""

    def __init__(self) -> None:
        super().__init__(callback, pattern=CALLBACK_PATTERN)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Answer the picked command for the picked group, below the picker."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        _logger.error("Received group-pick callback without query/data/effective_user")
        return

    message = query.message
    if not isinstance(message, Message):
        # Telegram hands over a picker too old to reply to as an inaccessible message.
        _logger.info("Ignoring a tap on an inaccessible group picker from user_id=%s", update.effective_user.id)
        await query.answer()
        return

    try:
        command, chat_id, arg = decode_pick(query.data)
        send = SENDERS[command]
    except (ValueError, KeyError):
        _logger.warning("Ignoring group-pick callback with unknown data=%r", query.data)
        await query.answer()
        return

    user_id = update.effective_user.id
    await query.answer()
    if not await can_read_group(context.bot, context.bot_data, chat_id, user_id):
        _logger.info("Refused /%s for chat_id=%s to user_id=%s", command, chat_id, user_id)
        await query.edit_message_text(NO_LONGER_IN_GROUP)
        return

    _logger.info("Answering /%s for chat_id=%s to user_id=%s in a private chat", command, chat_id, user_id)
    # Replacing the picker with the group's name drops its buttons, so it can't be tapped
    # twice, and labels the reply that follows with the group it is about.
    await query.edit_message_text(await group_title(context.bot, chat_id))
    await send(message, context, context.bot_data.get_chat(chat_id), arg)
