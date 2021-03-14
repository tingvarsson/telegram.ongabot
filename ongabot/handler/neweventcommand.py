"""This module contains the NewEventCommandHandler class."""
import logging
from datetime import date
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

import utils.helper as helper
from utils.helper import log


_logger = logging.getLogger(__name__)


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self):
        CommandHandler.__init__(self, "newevent", callback)


@log
def callback(update: Update, context: CallbackContext):
    """Create a poll as result of command /newevent"""
    _logger.debug("update:\n%s", update)

    # Retrieve prev pinned msg and unpin
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is not None:
        next_wed = helper.get_upcoming_wednesday_date(date.today()).strftime("%Y-%m-%d")
        if next_wed in pinned_poll.poll.question:
            context.bot.send_message(
                update.effective_chat.id,
                "Event already exists for: "
                + next_wed
                + "\nSend /cancelevent first if you wish to create a new event.",
            )
            _logger.debug("Attempted to create event for existing date.")
            return

        pinned_poll.unpin()
        context.chat_data["pinned_poll_msg"] = None

    poll_message = context.bot.send_poll(
        update.effective_chat.id,
        create_poll_text(),
        options=create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    _logger.debug("poll_message:\n%s", poll_message)

    # Store the new poll in bot_data
    poll_data = {
        "poll_message.poll.id": {
            "chat_id": update.effective_chat.id,
            "poll": poll_message.poll,
        }
    }
    context.bot_data.update(poll_data)
    _logger.debug("context.bot_data:\n%s", context.bot_data)

    # Pin new message and save to chat_data for future removal
    poll_message.pin(disable_notification=True)
    context.chat_data["pinned_poll_msg"] = poll_message
    _logger.debug("pinned_poll_msg: %s", poll_message.poll.id)


def create_poll_text():
    """Create text field for poll"""
    title = "Event: ONGA"
    when = f"When: {helper.get_upcoming_wednesday_date(date.today())}"
    text = f"{title}\n{when}"
    return text


def create_poll_options():
    """Create options for poll"""
    options = [
        "17.30",
        "18.30",
        "19.30",
        "20.30",
        "No-op",
        "Maybe Baby <3",
    ]

    return options
