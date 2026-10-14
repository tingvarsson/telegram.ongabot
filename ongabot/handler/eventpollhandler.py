"""This module contains the EventPollHandler class."""

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackContext, PollHandler

from gifs.moments import send_stack_celebration
from utils.log import log

_logger = logging.getLogger(__name__)


class EventPollHandler(PollHandler):
    """Handler for event poll updates"""

    def __init__(self) -> None:
        super().__init__(callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Handle a poll update of an event"""
    if update.poll is None:
        _logger.error("Received poll update without poll")
        return

    event = context.bot_data.get_event(update.poll.id)
    if event is None:
        if context.bot_data.is_verification_poll(update.poll.id):
            # /unverify and /verify polls are tallied when they close, see verification.py.
            _logger.debug("Ignoring poll update for verification poll_id=%s", update.poll.id)
        else:
            _logger.error("Received poll update for unknown poll_id=%s", update.poll.id)
        return
    event.update_poll(update.poll)
    chat = context.bot_data.get_chat(event.chat_id)

    # Poll updates carry the per-slot vote counts, so this is where a slot is seen reaching a
    # full stack. Claimed before the first await, so the next update cannot celebrate it again.
    slot = event.claim_stack_celebration()
    if slot is not None:
        try:
            await send_stack_celebration(context.bot, chat, event.poll_id, slot)
        except TelegramError as e:
            # Released, so the next vote on the poll retries the celebration.
            event.stack_celebrated = False
            _logger.warning("Failed to celebrate a full stack in chat_id=%s: %s", event.chat_id, e)

    await event.update_status_message(context.bot, unverified=chat.unverified)
