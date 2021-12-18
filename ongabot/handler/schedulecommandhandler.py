"""This module contains the ScheduleCommandHandler class."""
import logging
import typing
from datetime import date, datetime, timedelta
from typing import Any

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils import helper
from utils.log import log
from .neweventcommandhandler import callback as create_new_poll


_logger = logging.getLogger(__name__)


class ScheduleCommandHandler(CommandHandler):
    """Handler for /schedule command"""

    def __init__(self) -> None:
        CommandHandler.__init__(self, "schedule", callback=callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Schedule a poll creation job to run every week"""
    job_name = "Weekly scheduled poll creation job"
    day_to_schedule = "sunday"
    _logger.debug("update:\n%s", update)

    if check_if_job_exists(job_name, context):
        update.message.reply_text(
            "Scheduled job already exists. "
            "Send /deschedule first if you wish to create a new scheduled job"
        )
        return

    if len(context.args) > 1:
        update.message.reply_text(
            "Only one argument supported `/schedule <day>[OPTIONAL]`\n\n"
            "Example:\n`/schedule` default to schedule job on sundays \n"
            "`/schedule monday` to schedule job on mondays",
            parse_mode="MarkdownV2",
        )
        return

    if len(context.args) == 1:
        if not is_args_valid(context.args[0]):
            update.message.reply_text("Please provide a day that I understand. Bitch.")
            return
        day_to_schedule = context.args[0]

    poll_creation_dto = {"context": context, "update": update}

    upcoming_scheduled_date = helper.get_upcoming_date(date.today(), day_to_schedule)

    job = context.job_queue.run_repeating(
        create_poll,
        interval=timedelta(weeks=1),
        first=datetime(
            upcoming_scheduled_date.year,
            upcoming_scheduled_date.month,
            upcoming_scheduled_date.day,
            20,
            0,
            0,
        ),
        context=poll_creation_dto,
        name=job_name,
    )
    update.message.reply_text(
        f"Poll creation is now scheduled to run every {day_to_schedule} "
        f"starting on {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"
    )


def check_if_job_exists(name: str, context: CallbackContext) -> bool:
    """Returns true of false whether job already exists."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    return True


def is_args_valid(day: str) -> bool:
    """Validates that the supplied arg is a valid day"""
    if day.lower() not in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        return False
    return True


def create_poll(context: CallbackContext) -> None:
    """Creates a new poll by calling /neweventcommand"""
    _logger.debug("Poll creation is triggered by timer on %s", datetime.now())
    create_new_poll(
        typing.cast(typing.Dict[str, Any], context.job.context)["update"],
        typing.cast(typing.Dict[str, Any], context.job.context)["context"],
    )
