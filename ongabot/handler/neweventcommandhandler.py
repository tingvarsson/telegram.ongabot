"""This module contains the NewEventCommandHandler class."""
import logging
from datetime import date

from telegram import TelegramError, Update
from telegram.ext import CommandHandler, CallbackContext

import botdata
from event import Event

from utils import helper
from utils.log import log


_logger = logging.getLogger(__name__)


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self) -> None:
        super().__init__("newevent", callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Create a poll as result of command /newevent"""
    _logger.debug("update:\n%s", update)

    # Retrieve previous pinned poll message and try to unpin if applicable
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is not None:
        next_wed = helper.get_upcoming_date(date.today(), "wednesday").strftime("%Y-%m-%d")
        if next_wed in pinned_poll.poll.question:
            context.bot.send_message(
                update.effective_chat.id,
                "Event already exists for: "
                + next_wed
                + "\nSend /cancelevent first if you wish to create a new event.",
            )
            _logger.debug("Event already exist for next Wednesday (%s).", next_wed)
            return

        try:
            pinned_poll.unpin()
        except TelegramError:
            _logger.warning(
                "Failed trying to unpin message (message_id=%i).", pinned_poll.message_id
            )
        context.chat_data["pinned_poll_msg"] = None

    poll_message = context.bot.send_poll(
        update.effective_chat.id,
        create_poll_text(),
        options=create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    _logger.debug("poll_message:\n%s", poll_message)

    event = Event(update.effective_chat.id, poll_message.poll)
    event.send_status_message(context.bot)

    botdata.add_event(context.bot_data, key=event.poll_id, value=event)

    # Pin new message and save to chat_data for future removal
    poll_message.pin(disable_notification=True)
    context.chat_data["pinned_poll_msg"] = poll_message
    _logger.debug("pinned_poll_msg: %s", poll_message.poll.id)


def create_poll_text() -> str:
    """Create text field for poll"""
    title = "Event: ONGA"
    when = f"When: {helper.get_upcoming_date(date.today(), 'wednesday')}"
    text = f"{title}\n{when}"
    return text


def create_poll_options() -> list[str]:
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
