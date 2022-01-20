"""This module contains the functions for creating an event."""
import logging
import typing
from datetime import date, datetime

from telegram.ext import CallbackContext

from chat import Chat
from event import Event
from utils import helper
from utils.log import log


_logger = logging.getLogger(__name__)


@log
def create_event_callback(context: CallbackContext) -> None:
    """Create the event on callback, after extracting chat_id from job.context"""
    _logger.debug("Poll creation is triggered by timer on %s", datetime.now())
    chat_id = typing.cast(int, context.job.context)
    create_event(context, chat_id)


@log
def create_event(context: CallbackContext, chat_id: int) -> None:
    """Create an event"""
    # Retrieve previous pinned poll message and try to unpin if applicable
    chat: Chat = context.bot_data.get_chat(chat_id)
    pinned_poll = chat.get_pinned_poll()

    if pinned_poll is not None:
        next_wed = helper.get_upcoming_date(date.today(), "wednesday").strftime("%Y-%m-%d")
        if next_wed in pinned_poll.poll.question:
            context.bot.send_message(
                chat_id,
                "Event already exists for: "
                + next_wed
                + "\nSend /cancelevent first if you wish to create a new event.",
            )
            _logger.debug("Event already exist for next Wednesday (%s).", next_wed)
            return

        chat.remove_pinned_poll()

    poll_message = context.bot.send_poll(
        chat_id,
        _create_poll_text(),
        options=_create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    _logger.debug("poll_message:\n%s", poll_message)

    event = Event(chat_id, poll_message.poll)
    event.send_status_message(context.bot)

    chat.add_event(event)

    # Pin new message and save to chat_data for future removal
    poll_message.pin(disable_notification=True)
    chat.set_pinned_poll(poll_message)


def _create_poll_text() -> str:
    """Create text field for poll"""
    title = "Event: ONGA"
    when = f"When: {helper.get_upcoming_date(date.today(), 'wednesday')}"
    text = f"{title}\n{when}"
    return text


def _create_poll_options() -> list[str]:
    """Create options for poll"""
    options = [
        "18.00",
        "19.00",
        "20.00",
        "21.00",
        "No-op",
        "Maybe Baby </3",
    ]

    return options
