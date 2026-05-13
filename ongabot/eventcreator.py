"""This module contains the helper functions for creating an event."""

import logging
from datetime import date, datetime, time, timedelta

from telegram.error import TelegramError
from telegram.ext import CallbackContext

from chat import Chat
from event import Event
from eventdata import EventData
from utils.log import log

_logger = logging.getLogger(__name__)


@log
async def create_event_callback(context: CallbackContext) -> None:
    """Create the event on callback, after extracting chat_id from job.context"""
    _logger.debug("Poll creation is triggered by timer on %s", datetime.now())
    if context.job is None or context.job.chat_id is None:
        _logger.error("Received event creation callback without job or chat_id in context")
        return

    chat: Chat = context.bot_data.get_chat(context.job.chat_id)
    if chat.event_job is None:
        _logger.error("No event job found for chat_id %s in create_event_callback", context.job.chat_id)
        return

    await create_event(context, context.job.chat_id, chat.event_job.to_event_data())


@log
async def create_event(
    context: CallbackContext,
    chat_id: int,
    event_data: EventData,
) -> None:
    """Create an event"""
    chat: Chat = context.bot_data.get_chat(chat_id)

    # Check for an existing active (non-completed) event on the same date
    for existing in chat.active_events:
        if existing.event_date == event_data.event_date:
            await context.bot.send_message(
                chat_id,
                f"Event already exists for: {event_data.event_date}"
                "\nSend /cancelevent first if you wish to cancel it.",
            )
            _logger.debug("Event already exists for date %s.", event_data.event_date)
            return

    try:
        poll_message = await context.bot.send_poll(
            chat_id,
            _create_poll_text(event_data.event_date, event_data.start_time),
            options=_create_poll_options(event_data.start_time, event_data.num_slots),
            is_anonymous=False,
            allows_multiple_answers=True,
        )
    except TelegramError as e:
        _logger.error("Failed to send poll for chat_id=%s: %s", chat_id, e)
        return

    _logger.debug("poll_message:\n%s", poll_message)

    event = Event(chat_id, poll_message.poll, event_data)

    try:
        await event.send_status_message(context.bot)
    except TelegramError as e:
        _logger.error("Failed to send status message for chat_id=%s poll_id=%s: %s", chat_id, event.poll_id, e)

    chat.add_event(event)

    # Pin new message and save to chat data for future removal
    try:
        await poll_message.pin(disable_notification=True)
        chat.set_pinned_poll(poll_message.poll.id, poll_message)
    except TelegramError as e:
        _logger.error("Failed to pin poll message for chat_id=%s poll_id=%s: %s", chat_id, event.poll_id, e)


_EVENT_NAME_BY_WEEKDAY = {
    0: "MÅGA",
    1: "TIGA",
    2: "ONGA",
    3: "TOGA",
    4: "FREGA",
    5: "LÖGA",
    6: "SÖGA",
}


def _create_poll_text(event_date: date, start_time: time) -> str:
    """Create text field for poll"""
    name = _EVENT_NAME_BY_WEEKDAY[event_date.weekday()]
    if event_date.weekday() != 2:  # Onsdag is the home day, no suffix
        name += " (with ONGA)"
    title = f"Event: {name}"
    when = f"When: {event_date} {start_time.strftime('%H:%M')}"
    return f"{title}\n{when}"


def _create_poll_options(start_time: time, num_slots: int) -> list[str]:
    """Create poll options: num_slots time options at 40-min intervals, then No-op and Maybe Baby"""
    dt = datetime.combine(date.today(), start_time)
    options = []
    for _ in range(num_slots):
        options.append(dt.strftime("%H.%M"))
        dt += timedelta(minutes=40)
    options += ["No-op", "Maybe Baby </3"]
    return options
