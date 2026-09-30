"""This module contains the TimezoneCommandHandler class."""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, Job

from chat import Chat
from eventcreator import create_event_callback
from utils import clock
from utils.commands import TIMEZONE
from utils.log import log

_logger = logging.getLogger(__name__)

# The argument that clears a chat's own zone, so it follows the bot default again.
RESET_ARG = "default"


class TimezoneCommandHandler(CommandHandler):
    """Handler for /timezone command"""

    def __init__(self) -> None:
        super().__init__("timezone", callback=callback)


def _describe(chat: Chat) -> str:
    """The chat's zone, marked when it is the bot default, and the local time there."""
    source = "" if chat.timezone_name else " (bot default)"
    return f"Timezone: {chat.tz}{source}\nLocal time: {chat.now():%Y-%m-%d %H:%M}"


def _next_poll_line(job: Optional[Job]) -> str:
    """A line naming the next weekly poll, or nothing when the chat has no schedule."""
    if job is None or job.next_t is None:
        return ""
    return f"\nNext weekly poll: {job.next_t:%Y-%m-%d %H:%M} ({job.next_t.tzinfo})"


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Show or set the chat's timezone as result of /timezone [<zone>|default]"""
    if update.message is None or update.effective_chat is None or context.job_queue is None:
        _logger.error("Received /timezone command without message, effective chat or job queue")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    args = context.args or []

    if not args:
        await update.message.reply_text(_describe(chat))
        return
    if len(args) != 1:
        await update.message.reply_text(TIMEZONE.usage)
        return

    if args[0].lower() == RESET_ARG:
        name = None
    else:
        try:
            name = str(clock.resolve_timezone(args[0]))
        except ValueError as e:
            await update.message.reply_text(f"{e}\n\n{TIMEZONE.usage}")
            return

    chat.set_timezone(name)

    # The weekly poll fires at a wall-clock time in the chat's zone, so its job has to be
    # rebuilt. A CS2 sweep or poke already scheduled for today keeps its time; the hourly passes
    # schedule every later one in the new zone.
    job = None
    if chat.event_job:
        chat.event_job.deschedule(context.job_queue)
        job = chat.schedule_event_job(context.job_queue, create_event_callback)

    await update.message.reply_text(f"{_describe(chat)}{_next_poll_line(job)}")
