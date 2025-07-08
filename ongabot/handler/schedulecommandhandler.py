"""This module contains the ScheduleCommandHandler class."""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from eventcreator import create_event_callback
from eventjob import EventJob
from utils import helper
from utils.log import log


_logger = logging.getLogger(__name__)


class ScheduleCommandHandler(CommandHandler):
    """Handler for /schedule command"""

    def __init__(self) -> None:
        CommandHandler.__init__(self, "schedule", callback=callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Schedule a event creation job to run every week"""
    if len(context.args) > 1:
        await update.message.reply_text(
            "Only one argument supported `/schedule <day>[OPTIONAL]`"
            "\n\nExample:"
            "\n`/schedule` default to schedule job on sundays"
            "\n`/schedule monday` to schedule job on mondays",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    day_to_schedule = "sunday"
    if len(context.args) == 1:
        if not helper.is_valid_weekday(context.args[0]):
            await update.message.reply_text(
                r"Please provide a day that I understand\. "
                rf"What even is *__{context.args[0]}__*\?\!"
                "\n"
                r"_Bitch\._",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        day_to_schedule = context.args[0]

    event_job = EventJob(update.effective_chat.id, day_to_schedule)
    if event_job.check_if_job_exists(context.job_queue):
        await update.message.reply_text(
            r"Scheduled job already exists\. Deschedule first "
            r"if you wish to re\-create the scheduled job\."
            "\n`/deschedule`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    job = event_job.schedule(context.job_queue, create_event_callback)

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    chat.set_event_job(event_job)

    await update.message.reply_text(
        f"Poll creation is now scheduled to run every {day_to_schedule} "
        f"starting on {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"
    )
