"""This module contains the DeScheduleCommandHandler class."""
import logging
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from chat import Chat
from utils.log import log

_logger = logging.getLogger(__name__)


class DeScheduleCommandHandler(CommandHandler):
    """Handler for /schedule command"""

    def __init__(self) -> None:
        CommandHandler.__init__(self, "deschedule", callback=callback)


@log
def callback(update: Update, context: CallbackContext) -> None:
    """Cancel existing event job in chat"""
    _logger.debug("update:\n%s", update)

    job_name = f"weeky_event_{update.effective_chat.id}"

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    if not chat.remove_event_job(job_name, context.job_queue):
        update.message.reply_text("No jobs to cancel.")

    update.message.reply_text(
        "Job cancelled successfully. Polls will no longer be automatically created."
    )
