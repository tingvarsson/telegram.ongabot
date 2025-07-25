"""This module contains the helper functions for creating an event."""

import logging
from datetime import date, datetime

from telegram.ext import CallbackContext

from chat import Chat
from event import Event
from utils import helper
from utils.log import log


_logger = logging.getLogger(__name__)


@log
async def create_event_callback(context: CallbackContext) -> None:
    """Create the event on callback, after extracting chat_id from job.context"""
    _logger.debug("Poll creation is triggered by timer on %s", datetime.now())
    await create_event(context, context.job.chat_id)


@log
async def create_event(context: CallbackContext, chat_id: int) -> None:
    """Create an event"""
    # Retrieve previous pinned poll message and try to unpin if applicable
    chat: Chat = context.bot_data.get_chat(chat_id)
    pinned_poll = chat.get_pinned_poll()

    if pinned_poll is not None:
        next_thu = helper.get_upcoming_date(date.today(), "thursday").strftime("%Y-%m-%d")
        if next_thu in pinned_poll.poll.question:
            await context.bot.send_message(
                chat_id,
                "Event already exists for: "
                + next_thu
                + "\nSend /cancelevent first if you wish to create a new event.",
            )
            _logger.debug("Event already exist for next Thursday (%s).", next_thu)
            return

        await chat.remove_pinned_poll()

    poll_message = await context.bot.send_poll(
        chat_id,
        _create_poll_text(),
        options=_create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    _logger.debug("poll_message:\n%s", poll_message)

    event = Event(chat_id, poll_message.poll)
    await event.send_status_message(context.bot)

    chat.add_event(event)

    # Pin new message and save to chat_data for future removal
    await poll_message.pin(disable_notification=True)
    chat.set_pinned_poll(poll_message)


def _create_poll_text() -> str:
    """Create text field for poll"""
    title = "Event: TOGA (with ONGA)"
    when = f"When: {helper.get_upcoming_date(date.today(), 'thursday')}"
    text = f"{title}\n{when}"
    return text


def _create_poll_options() -> list[str]:
    """Create options for poll"""
    options = [
        "18.30",
        "19.10",
        "19.50",
        "20.40",
        "21.20",
        "No-op",
        "Maybe Baby </3",
    ]

    return options
