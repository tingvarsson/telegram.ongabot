"""This module contains the EventPollAnswerHandler class."""
import logging

from telegram import PollAnswer, Update
from telegram.ext import CallbackContext, PollAnswerHandler

from utils.log import log


_logger = logging.getLogger(__name__)


class EventPollAnswerHandler(PollAnswerHandler):
    """Handler for event poll answer updates"""

    def __init__(self) -> None:
        super().__init__(callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Handle a poll answer update of an event"""
    _logger.debug("update:\n%s", update)

    event = context.bot_data.get_event(update.poll_answer.poll_id)
    event.update_answer(update.poll_answer)
    event.update_status_message(context.bot)

    # Empty option_ids means the user retracted his vote, ignore those for now
    if update.poll_answer.option_ids:
        user_name = update.poll_answer.user.name

        # Existing poll_answer for that poll_id means the user has changed their vote
        if _get_poll_answer(context.user_data, update.poll_answer.poll_id):
            response = f"Hmm suspicious, looks like {user_name} changed their vote..."
        else:
            response = f"Wow {user_name}, what a great job answering that poll!"

        context.bot.send_message(
            event.chat_id,
            response,
        )

    _set_poll_answer(context.user_data, update.poll_answer)
    _logger.debug("context.user_data:\n%s", context.user_data)


def _get_poll_answer(user_data: dict, poll_id: str) -> dict:
    if not user_data:
        return None

    if not user_data.get("poll_answers"):
        return None

    return user_data.get("poll_answers").get(poll_id)


def _set_poll_answer(user_data: dict, poll_answer: PollAnswer) -> None:
    if not user_data:
        new_user = {
            "user": poll_answer.user,
            "poll_answers": {},
        }
        user_data.update(new_user)

    answer = {
        poll_answer.poll_id: {
            "poll_answer": poll_answer.option_ids,
        },
    }
    user_data.get("poll_answers").update(answer)
