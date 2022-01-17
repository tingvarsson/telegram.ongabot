"""This module contains the ScheduleCommandHandler class."""
import logging

from telegram import ParseMode, Update
from telegram.ext import CommandHandler, CallbackContext

import botdata
import eventjob
from utils import helper
from utils.log import log


_logger = logging.getLogger(__name__)


class ScheduleCommandHandler(CommandHandler):
    """Handler for /schedule command"""

    def __init__(self) -> None:
        CommandHandler.__init__(self, "schedule", callback=callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Schedule a event creation job to run every week"""
    _logger.debug("update:\n%s", update)

    job_name = f"weeky_event_{update.effective_chat.id}"
    if check_if_job_exists(job_name, context):
        update.message.reply_text(
            r"Scheduled job already exists\. Deschedule first "
            r"if you wish to re\-create the scheduled job\."
            "\n`/deschedule`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if len(context.args) > 1:
        update.message.reply_text(
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
            update.message.reply_text(
                r"Please provide a day that I understand\. "
                rf"What even is *__{context.args[0]}__*\?\!"
                "\n"
                r"_Bitch\._",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        day_to_schedule = context.args[0]

    job = eventjob.schedule(context.job_queue, update.effective_chat.id, job_name, day_to_schedule)

    botdata.add_event_job(context.bot_data, update.effective_chat.id, job_name, day_to_schedule)

    update.message.reply_text(
        f"Poll creation is now scheduled to run every {day_to_schedule} "
        f"starting on {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"
    )


def check_if_job_exists(name: str, context: CallbackContext) -> bool:
    """Return true or false whether job already exists."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    return True
