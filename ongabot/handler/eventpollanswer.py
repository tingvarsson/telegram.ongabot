"""This module contains the EventPollAnswerHandler class."""
import logging
from telegram import Update
from telegram.ext import PollAnswerHandler, CallbackContext

from utils.helper import log

_logger = logging.getLogger(__name__)


class EventPollAnswerHandler(PollAnswerHandler):
    """Handler for event poll answer updates"""

    def __init__(self):
        PollAnswerHandler.__init__(self, callback=callback)


@log
def callback(update: Update, context: CallbackContext):
    """Handle an poll update"""
    _logger.debug("update:\n%s", update)

    context.bot.send_message(
        context.bot_data[update.poll_answer.poll_id]["chat_id"],
        f"Wow {update.poll_answer.user.name}, what a great job answering that poll!",
    )

    # Store poll answer in user_data
    user_data = {
        "user": update.poll_answer.user,
        "poll_answers": {
            update.poll_answer.poll_id: {
                "poll_answer": update.poll_answer.option_ids,
            },
        },
    }
    context.user_data.update(user_data)
    _logger.debug("context.user_data:\n%s", context.user_data)
