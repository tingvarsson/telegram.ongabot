"""This module contains the Event class."""
import logging
import typing
from datetime import date, datetime, timedelta
from typing import Dict

from telegram import TelegramError
from telegram.ext import CallbackContext, Job, JobQueue

import botdata
from event import Event
from utils import helper

_logger = logging.getLogger(__name__)


def schedule_all(job_queue: JobQueue, bot_data: Dict) -> None:
    """Schedule all persistently stored event jobs"""
    if not bot_data:
        return

    chats = bot_data.get("chats")
    if not chats:
        return

    for chat_id, chat_data in chats.items():
        if not chat_data.get("jobs"):
            continue

        for job_name, job in chat_data.get("jobs").items():
            schedule(job_queue, chat_id, job_name, job.get("day_to_schedule"))


def schedule(job_queue: JobQueue, chat_id: int, job_name: str, day_to_schedule: str) -> Job:
    """Schedule an event job, triggering event creation at day_to_schedule"""
    upcoming_date = helper.get_upcoming_date(date.today(), day_to_schedule)

    return job_queue.run_repeating(
        _create_event_callback,
        interval=timedelta(weeks=1),
        first=datetime(
            upcoming_date.year,
            upcoming_date.month,
            upcoming_date.day,
            20,
            0,
            0,
        ),
        context=chat_id,
        name=job_name,
    )


def _create_event_callback(context: CallbackContext) -> None:
    """Create the event on callback, after extracting chat_id from job.context"""
    _logger.debug("Poll creation is triggered by timer on %s", datetime.now())
    chat_id = typing.cast(int, context.job.context)
    create_event(context, chat_id)


def create_event(context: CallbackContext, chat_id: int) -> None:
    """Create an event"""
    # Retrieve previous pinned poll message and try to unpin if applicable
    pinned_poll = botdata.get_pinned_event_poll_message(context.bot_data, chat_id)

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

        try:
            pinned_poll.unpin()
        except TelegramError:
            _logger.warning(
                "Failed trying to unpin message (message_id=%i).", pinned_poll.message_id
            )
        botdata.remove_pinned_event_poll_message(context.bot_data, chat_id)

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

    botdata.add_event(context.bot_data, event.poll_id, event)

    # Pin new message and save to chat_data for future removal
    poll_message.pin(disable_notification=True)
    botdata.add_pinned_event_poll_message(context.bot_data, chat_id=chat_id, message=poll_message)


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
