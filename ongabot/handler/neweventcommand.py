"""This module contains the NewEventCommandHandler class."""
import logging
from datetime import date
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

import utils.helper as helper


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self):
        CommandHandler.__init__(self, "newevent", callback)


def callback(update: Update, context: CallbackContext):
    """Create a poll as result of command /newevent"""
    logger = logging.getLogger()
    logger.debug("ENTER: NewEventCommandHandler::callback")
    logger.debug("update:")
    logger.debug("%s", update)

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
            logger.debug("Attempted to create event for existing date.")
            logger.debug("EXIT: NewEventCommandHandler::callback")
            return
        pinned_poll.unpin()
        context.chat_data["pinned_poll_msg"] = None

    message = context.bot.send_poll(
        update.effective_chat.id,
        create_poll_text(),
        options=create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )

    logger.debug("message:")
    logger.debug("%s", message)

    # Store the new poll in bot_data
    poll_data = {
        message.poll.id: {
            "chat_id": update.effective_chat.id,
            "poll": message.poll,
        }
    }
    context.bot_data.update(poll_data)
    logger.debug("context.bot_data:")
    logger.debug("%s", context.bot_data)

    # Pin new message and save to database for future removal
    message.pin(disable_notification=True)
    context.chat_data["pinned_poll_msg"] = message
    logger.debug("pin msg: %d", message.poll.id)

    logger.debug("EXIT: NewEventCommandHandler::callback")


def create_poll_text():
    """Create text field for poll"""
    title = "Event: ONGA"
    when = f"When: {helper.get_upcoming_wednesday_date(date.today())}"
    message = f"{title}\n{when}"
    return message


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
