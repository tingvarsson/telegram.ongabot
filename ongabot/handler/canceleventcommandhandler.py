"""This module contains the CancelEventCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from utils import helper
from utils.commands import CANCELEVENT
from utils.log import log

_logger = logging.getLogger(__name__)

_ALLOWED_ARGS = {"target_date"}


class CancelEventCommandHandler(CommandHandler):
    """Handler for /cancelevent command"""

    def __init__(self) -> None:
        super().__init__("cancelevent", callback)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Cancel active event as result of command /cancelevent [target_date=<val>]"""
    if update.effective_chat is None or update.message is None:
        _logger.warning("Received /cancelevent command with no effective chat or message.")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    active_events = chat.active_events

    if not active_events:
        await context.bot.send_message(
            update.effective_chat.id,
            "No known event to cancel! Create a new event with /newevent.",
        )
        _logger.debug("Tried to cancel without existing event.")
        return

    target_date = None

    args = context.args or []
    if args:
        try:
            named = helper.parse_named_args(args, _ALLOWED_ARGS)
        except ValueError as e:
            await update.message.reply_text(f"{e}\n\n{CANCELEVENT.usage}")
            return
        if "target_date" in named:
            try:
                target_date = helper.parse_date(named["target_date"])
            except ValueError as e:
                await update.message.reply_text(f"{e}\n\n{CANCELEVENT.usage}")
                return

    candidates = None
    if target_date:
        # If target date provided, narrow down candidates to events matching the date
        candidates = [e for e in active_events if e.event_date == target_date]
    else:
        # If no target date provided, consider all active events as candidates for cancellation
        candidates = active_events

    if not candidates:
        spec = f" for {target_date}" if target_date else ""
        await update.message.reply_text(f"No active event found{spec}.")
        return

    if len(candidates) > 1:
        lines = ["Multiple active events match. Be more specific using target_date=:"]
        for e in sorted(candidates, key=lambda e: (e.event_date, e.start_time)):
            lines.append(f"  • {e.event_date} {e.start_time.strftime('%H:%M')}")
        lines.append(f"\n{CANCELEVENT.usage}")
        await context.bot.send_message(update.effective_chat.id, "\n".join(lines))
        return

    # At this point we have identified a single target event to cancel
    target_event = candidates[0]

    question = target_event.poll.question.splitlines()[0]
    target_event.cancelled = True
    target_event.mark_complete()
    await chat.remove_pinned_poll(target_event.poll_id)

    await context.bot.send_message(
        update.effective_chat.id,
        question + "\nCancelled successfully. The poll is still accessible in the channel history.",
    )
    _logger.debug("Cancelled event with poll_id %s", target_event.poll_id)
