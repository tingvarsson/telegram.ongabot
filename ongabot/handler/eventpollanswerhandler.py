"""This module contains the EventPollAnswerHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, PollAnswerHandler

from userdata import UserData
from utils.log import log


_logger = logging.getLogger(__name__)


class EventPollAnswerHandler(PollAnswerHandler):
    """Handler for event poll answer updates"""

    def __init__(self) -> None:
        super().__init__(callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Handle a poll answer update of an event"""
    event = context.bot_data.get_event(update.poll_answer.poll_id)
    event.update_answer(update.poll_answer)
    event.update_status_message(context.bot)

    user_data: UserData = context.user_data
    user_data.init_or_update(update.poll_answer.user)

    # Empty option_ids means the user retracted his vote, ignore those for now
    if update.poll_answer.option_ids:
        user_name = update.poll_answer.user.name

        # Existing poll_answer for that poll_id means the user has changed their vote
        if user_data.get_poll_answer(update.poll_answer.poll_id) is None:
            response = f"Wow {user_name}, what a great job answering that poll!"
        else:
            response = f"Hmm suspicious, looks like {user_name} changed their vote..."

        await context.bot.send_message(
            event.chat_id,
            response,
        )

    user_data.set_poll_answer(update.poll_answer.poll_id, update.poll_answer.option_ids)
