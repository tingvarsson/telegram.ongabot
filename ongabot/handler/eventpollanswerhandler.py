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
    if update.poll_answer is None or update.poll_answer.user is None:
        _logger.error("Received poll answer update without poll answer")
        return

    event = context.bot_data.get_event(update.poll_answer.poll_id)
    if event is None:
        _logger.error("Received poll answer update for unknown poll_id=%s", update.poll_answer.poll_id)
        return

    if context.user_data is None:
        _logger.error("Received poll answer update without user data in context")
        return

    user_data: UserData = context.user_data
    user_data.init_or_update(update.poll_answer.user)
    event.update_answer(update.poll_answer)

    # Build response before set_poll_answer changes state (first-vote vs changed-vote check)
    response = None
    # Empty option_ids means the user retracted his vote, ignore those for now
    if update.poll_answer.option_ids:
        user_name = update.poll_answer.user.name
        if user_data.get_poll_answer(update.poll_answer.poll_id) is None:
            response = f"Wow {user_name}, what a great job answering that poll!"
        else:
            response = f"Hmm suspicious, looks like {user_name} changed their vote..."

    user_data.set_poll_answer(update.poll_answer.poll_id, update.poll_answer.option_ids)

    if update.poll_answer.option_ids:
        chat = context.bot_data.get_chat(event.chat_id)
        # Cancelled events are excluded so they neither count towards nor break a streak.
        active_events = [e for e in chat.events.values() if not e.cancelled]
        poll_id_to_date = {e.poll_id: e.event_date for e in active_events}
        poll_id_to_num_slots = {e.poll_id: e.num_slots for e in active_events}
        user_id = update.poll_answer.user.id
        event.user_streaks[user_id] = user_data.calculate_streak(poll_id_to_date)
        event.user_played_streaks[user_id] = user_data.calculate_played_streak(poll_id_to_date, poll_id_to_num_slots)
        _logger.debug(
            "Streaks for user_id=%s on poll_id=%s: response=%s, played=%s",
            user_id,
            update.poll_answer.poll_id,
            event.user_streaks[user_id],
            event.user_played_streaks[user_id],
        )

    await event.update_status_message(context.bot)

    if response:
        await context.bot.send_message(event.chat_id, response)
