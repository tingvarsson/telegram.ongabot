"""This module contains the DeScheduleCommandHandler class."""
import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from utils.log import log

_logger = logging.getLogger(__name__)


class DeScheduleCommandHandler(CommandHandler):
    """ Handler for /schedule command """

    def __init__(self) -> None:
        CommandHandler.__init__(self, "deschedule", callback=callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """ Cancels existing jobs """
    _logger.debug("update:\n%s", update)

    current_jobs = context.job_queue.get_jobs_by_name("Weekly scheduled poll creation job")

    if not current_jobs:
        update.message.reply_text("No jobs to cancel")
        return

    for job in current_jobs:
        job.schedule_removal()

    update.message.reply_text(
        "Job cancelled successfully. Polls will no longer be automatically created"
    )
