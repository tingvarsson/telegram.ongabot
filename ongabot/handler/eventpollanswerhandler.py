"""This module contains the EventPollAnswerHandler class."""

import logging
from datetime import timedelta

from telegram import Update
from telegram.ext import CallbackContext, JobQueue, PollAnswerHandler

from quips import build_retraction_reply, build_vote_reply, categorize
from userdata import UserData
from utils.log import log

_logger = logging.getLogger(__name__)

# How long a retracted vote may stay empty before the "pulled their vote" reply is sent.
# Changing a vote in Telegram is retract-then-vote, so this must comfortably cover that.
RETRACTION_REPLY_DELAY = timedelta(minutes=10)


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

    poll_id = update.poll_answer.poll_id
    user_id = update.poll_answer.user.id
    job_queue = context.job_queue
    if job_queue is None:
        _logger.warning("No job queue for poll_id=%s; retraction replies are disabled", poll_id)
    else:
        # Any new update supersedes a pending "pulled their vote" reply: a new vote replaces
        # the retraction, and a repeated retraction restarts the wait below.
        _cancel_retraction_reply(job_queue, poll_id, user_id)

    # Look up what the user had before set_poll_answer overwrites it. The last non-empty
    # answer, since Telegram changes a vote as retract-then-vote.
    last_ids = user_data.get_last_poll_answer(poll_id)
    previous = categorize(last_ids, event.num_slots) if last_ids else None

    response = None
    if update.poll_answer.option_ids:
        new = categorize(update.poll_answer.option_ids, event.num_slots)
        _logger.debug("Vote by user_id=%s on poll_id=%s: %s -> %s", user_id, poll_id, previous, new)
        response = build_vote_reply(update.poll_answer.user.name, previous, new)
    elif previous is not None and job_queue is not None:
        # A retraction is usually the first half of a vote change, so only reply if no new
        # vote follows within RETRACTION_REPLY_DELAY.
        _schedule_retraction_reply(job_queue, event.chat_id, poll_id, user_id)

    user_data.set_poll_answer(poll_id, update.poll_answer.option_ids)

    if update.poll_answer.option_ids:
        chat = context.bot_data.get_chat(event.chat_id)
        # Cancelled events are excluded so they neither count towards nor break a streak.
        active_events = [e for e in chat.events.values() if not e.cancelled]
        poll_id_to_date = {e.poll_id: e.event_date for e in active_events}
        poll_id_to_num_slots = {e.poll_id: e.num_slots for e in active_events}
        event.user_streaks[user_id] = user_data.calculate_streak(poll_id_to_date)
        event.user_played_streaks[user_id] = user_data.calculate_played_streak(poll_id_to_date, poll_id_to_num_slots)
        _logger.debug(
            "Streaks for user_id=%s on poll_id=%s: response=%s, played=%s",
            user_id,
            poll_id,
            event.user_streaks[user_id],
            event.user_played_streaks[user_id],
        )

    await event.update_status_message(context.bot)

    if response:
        await context.bot.send_message(event.chat_id, response)


def _retraction_job_name(poll_id: str, user_id: int) -> str:
    """Name of the pending "pulled their vote" reply job for one user in one poll."""
    return f"vote_retracted:{poll_id}:{user_id}"


def _cancel_retraction_reply(job_queue: JobQueue, poll_id: str, user_id: int) -> None:
    """Cancel a pending "pulled their vote" reply, if there is one."""
    for job in job_queue.get_jobs_by_name(_retraction_job_name(poll_id, user_id)):
        job.schedule_removal()
        _logger.info("Cancelled retraction reply for user_id=%s on poll_id=%s", user_id, poll_id)


def _schedule_retraction_reply(job_queue: JobQueue, chat_id: int, poll_id: str, user_id: int) -> None:
    """Schedule the "pulled their vote" reply for RETRACTION_REPLY_DELAY from now.

    Not persisted: a restart inside the window drops that one reply, which is harmless.
    """
    job_queue.run_once(
        retraction_reply_callback,
        when=RETRACTION_REPLY_DELAY,
        chat_id=chat_id,
        user_id=user_id,
        name=_retraction_job_name(poll_id, user_id),
        data=poll_id,
    )
    _logger.info("Scheduled retraction reply for user_id=%s on poll_id=%s", user_id, poll_id)


@log
async def retraction_reply_callback(context: CallbackContext) -> None:
    """Reply to a vote that was retracted and not replaced within RETRACTION_REPLY_DELAY."""
    if context.job is None:
        _logger.error("Retraction reply ran without a job")
        return
    # Job.data is typed as object by python-telegram-bot; this job always sets the poll id.
    poll_id = str(context.job.data)

    event = context.bot_data.get_event(poll_id)
    if event is None or event.cancelled:
        _logger.info("Skipping retraction reply: poll_id=%s is gone or cancelled", poll_id)
        return

    # context.user_data is the retracting user's, since the job was scheduled with user_id.
    user_data: UserData = context.user_data
    if user_data is None or user_data.user is None:
        _logger.error("Retraction reply for poll_id=%s ran without user data", poll_id)
        return
    if user_data.get_poll_answer(poll_id):
        # Safety net in case the cancel in callback raced with the job firing.
        _logger.info("Skipping retraction reply: user_id=%s voted again on poll_id=%s", user_data.user.id, poll_id)
        return
    last_ids = user_data.get_last_poll_answer(poll_id)
    if not last_ids:
        return

    previous = categorize(last_ids, event.num_slots)
    _logger.info("Sending retraction reply for user_id=%s on poll_id=%s (%s)", user_data.user.id, poll_id, previous)
    await context.bot.send_message(event.chat_id, build_retraction_reply(user_data.user.name, previous))
