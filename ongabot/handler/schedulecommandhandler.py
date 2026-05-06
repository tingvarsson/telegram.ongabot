"""This module contains the ScheduleCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from eventcreator import create_event_callback
from eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME
from eventjob import DEFAULT_TRIGGER_DAY, EventJob
from utils import helper
from utils.commands import SCHEDULE
from utils.log import log

_logger = logging.getLogger(__name__)


class ScheduleCommandHandler(CommandHandler):
    """Handler for /schedule command"""

    def __init__(self) -> None:
        super().__init__("schedule", callback=callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Schedule a event creation job to run every week"""
    if update.effective_chat is None or update.message is None or context.job_queue is None:
        logging.error("Invalid update or missing job queue in ScheduleCommandHandler callback")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    if chat.event_job:
        await update.message.reply_text(
            "Scheduled job already exists. Deschedule first if you wish to re-create it.\n/deschedule"
        )
        return

    try:
        trigger_on, event_day, start_time, num_slots = helper.parse_event_job_args(
            context.args or [], DEFAULT_TRIGGER_DAY, DEFAULT_EVENT_DAY, DEFAULT_START_TIME, DEFAULT_NUM_SLOTS
        )
    except ValueError as e:
        await update.message.reply_text(f"{e}\n\n{SCHEDULE.usage}")
        return

    event_job = EventJob(update.effective_chat.id, trigger_on, event_day, start_time, num_slots)
    job = event_job.schedule(context.job_queue, create_event_callback)
    chat.set_event_job(event_job)

    if job.next_t is None:
        _logger.error("Failed to schedule job for chat_id=%s", update.effective_chat.id)
        await update.message.reply_text("Failed to schedule job. Please try again.")
        return

    _logger.info(
        "Scheduled job for chat_id=%s with trigger_on=%s, event_day=%s, start_time=%s, num_slots=%s",
        update.effective_chat.id,
        trigger_on,
        event_day,
        start_time,
        num_slots,
    )
    await update.message.reply_text(
        f"Poll creation scheduled every {trigger_on}, events for {event_day}. "
        f"Starting on {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"
    )
