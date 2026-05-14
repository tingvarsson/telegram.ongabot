"""This module contains the NewEventCommandHandler class."""

import logging
from typing import Tuple

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from eventcreator import create_event
from eventdata import EventData
from utils import helper
from utils.commands import NEWEVENT
from utils.log import log

_logger = logging.getLogger(__name__)

_ALLOWED_ARGS = {"day", "time", "slots", "force"}


class NewEventCommandHandler(CommandHandler):
    """Handler for /newevent command"""

    def __init__(self) -> None:
        super().__init__("newevent", callback)


def _parse_args(args: list) -> Tuple[EventData, bool]:
    """Parse named args for /newevent. Raises ValueError with usage on invalid input.

    Returns a tuple of (EventData, force).
    """
    event_data = EventData()
    force = False

    named = helper.parse_named_args(args, _ALLOWED_ARGS)
    if "day" in named:
        event_data.event_date = helper.parse_date(named["day"])
    if "time" in named:
        event_data.start_time = helper.parse_time(named["time"])
    if "slots" in named:
        event_data.num_slots = helper.parse_num_slots(named["slots"])
    if "force" in named:
        force = named["force"].lower() == "true"

    return event_data, force


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Create a poll as result of command /newevent [day=<val>] [time=<HH:MM>] [slots=<n>] [force=true]"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /newevent command without message or effective chat")
        return

    try:
        event_data, force = _parse_args(context.args or [])
    except ValueError as e:
        await update.message.reply_text(f"{e}\n\n{NEWEVENT.usage}")
        return

    await create_event(context, update.effective_chat.id, event_data, force=force)
