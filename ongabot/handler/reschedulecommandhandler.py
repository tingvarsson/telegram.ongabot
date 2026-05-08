"""This module contains the RescheduleCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from eventcreator import create_event_callback
from eventjob import EventJob
from utils import helper
from utils.commands import RESCHEDULE
from utils.log import log

_logger = logging.getLogger(__name__)


class RescheduleCommandHandler(CommandHandler):
    """Handler for /reschedule command"""

    def __init__(self) -> None:
        super().__init__("reschedule", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Update an existing scheduled job as result of command
    /reschedule [trigger_on=<day>] [day=<day>] [time=<HH:MM>] [slots=<n>]"""
    if update.message is None or update.effective_chat is None or context.job_queue is None:
        _logger.error("Received /reschedule command without message or effective chat")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    if not chat.event_job:
        await update.message.reply_text("No schedule exists. Use /schedule first.")
        return

    if not context.args:
        await update.message.reply_text(
            "At least one of trigger_on/day/time/slots must be provided.\n\n" + RESCHEDULE.usage
        )
        return

    try:
        trigger_on, event_day, start_time, num_slots = helper.parse_event_job_args(
            context.args,
            chat.event_job.trigger_on,
            chat.event_job.event_day,
            chat.event_job.start_time,
            chat.event_job.num_slots,
        )
    except ValueError as e:
        await update.message.reply_text(f"{e}\n\n{RESCHEDULE.usage}")
        return

    if not chat.remove_event_job(context.job_queue):
        await update.message.reply_text("Failed to remove existing schedule. Try /deschedule first.")
        return
    event_job = EventJob(update.effective_chat.id, trigger_on, event_day, start_time, num_slots)
    job = event_job.schedule(context.job_queue, create_event_callback)
    chat.set_event_job(event_job)

    if job.next_t is None:
        _logger.error("Failed to reschedule job for chat_id=%s", update.effective_chat.id)
        await update.message.reply_text("Failed to reschedule job. Please try again.")
        return

    _logger.info(
        "Rescheduled job for chat_id=%s with trigger_on=%s, event_day=%s, start_time=%s, num_slots=%s",
        update.effective_chat.id,
        trigger_on,
        event_day,
        start_time,
        num_slots,
    )
    await update.message.reply_text(
        f"Schedule updated: poll fires every {trigger_on}, events for {event_day}. "
        f"Next trigger on {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"
    )
