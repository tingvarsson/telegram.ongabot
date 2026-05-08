"""This module contains the UpdateEventCommandHandler class."""

import logging
from datetime import date, time
from typing import Optional, Tuple

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from eventcreator import create_event
from eventdata import EventData
from utils import helper
from utils.commands import UPDATEEVENT
from utils.log import log

_logger = logging.getLogger(__name__)

_ALLOWED_ARGS = {"target_date", "day", "time", "slots"}


class UpdateEventCommandHandler(CommandHandler):
    """Handler for /updateevent command"""

    def __init__(self) -> None:
        super().__init__("updateevent", callback)


def _parse_args(args: list) -> Tuple[Optional[date], Optional[date], Optional[time], Optional[int]]:
    """Parse named args for /updateevent. Raises ValueError with usage on invalid input."""
    named = helper.parse_named_args(args, _ALLOWED_ARGS)

    target_date: Optional[date] = None
    new_date: Optional[date] = None
    new_time: Optional[time] = None
    new_slots: Optional[int] = None

    if "target_date" in named:
        try:
            target_date = helper.parse_date(named["target_date"])
        except ValueError:
            raise ValueError(UPDATEEVENT.usage) from None
    if "day" in named:
        try:
            new_date = helper.parse_date(named["day"])
        except ValueError:
            raise ValueError(UPDATEEVENT.usage) from None
    if "time" in named:
        try:
            new_time = helper.parse_time(named["time"])
        except ValueError:
            raise ValueError(UPDATEEVENT.usage) from None
    if "slots" in named:
        try:
            new_slots = helper.parse_num_slots(named["slots"])
        except ValueError:
            raise ValueError(UPDATEEVENT.usage) from None

    if new_date is None and new_time is None and new_slots is None:
        raise ValueError("At least one of day/time/slots must be provided.\n\n" + UPDATEEVENT.usage)

    return target_date, new_date, new_time, new_slots


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reconfigure an active event as result of command
    /updateevent [target_date=<val>] [day=<val>] [time=<HH:MM>] [slots=<n>]"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /updateevent command without message or effective chat")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)

    if not context.args:
        await update.message.reply_text("Arguments are required to update an event.\n\n" + UPDATEEVENT.usage)
        return

    try:
        target_date, new_date, new_time, new_slots = _parse_args(context.args)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    candidates = None
    if target_date is not None:
        # If target date provided, narrow down candidates to events matching the date
        candidates = [e for e in chat.active_events if e.event_date == target_date]
    else:
        # If no target date provided, consider all active events as candidates for cancellation
        candidates = chat.active_events

    if not candidates:
        spec = f" for {target_date}" if target_date else ""
        await update.message.reply_text(f"No active event found{spec}.")
        return

    if len(candidates) > 1:
        lines = ["Multiple active events match. Be more specific using target_date=:"]
        for e in sorted(candidates, key=lambda e: (e.event_date, e.start_time)):
            lines.append(f"  • {e.event_date} {e.start_time.strftime('%H:%M')}")
        lines.append(f"\n{UPDATEEVENT.usage}")
        await update.message.reply_text("\n".join(lines))
        return

    # At this point we have identified a single target event to update
    target_event = candidates[0]
    update_event_data = EventData(
        new_date if new_date is not None else target_event.event_date,
        new_time if new_time is not None else target_event.start_time,
        new_slots if new_slots is not None else target_event.num_slots,
    )

    # Validate that the new date doesn't conflict with another active event (except itself)
    if update_event_data.event_date != target_event.event_date:
        for event in chat.active_events:
            if event.event_date == update_event_data.event_date and event is not target_event:
                await update.message.reply_text(
                    f"An active event already exists for {update_event_data.event_date}. "
                    "Cancel it first with /cancelevent."
                )
                return

    # Mark the old event complete and create a new one with the merged configuration
    target_event.mark_complete()
    await chat.remove_pinned_poll(target_event.poll_id)
    _logger.info("Cancelled event poll_id=%s for update", target_event.poll_id)
    await create_event(context, update.effective_chat.id, update_event_data)
