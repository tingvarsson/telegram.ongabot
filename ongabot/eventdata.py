"""This module contains the EventData dataclass."""

from dataclasses import dataclass
from datetime import date, time

DEFAULT_EVENT_DAY = "wednesday"
DEFAULT_START_TIME = time(18, 30)
DEFAULT_NUM_SLOTS = 5


@dataclass
class EventData:
    """Groups the concrete date, start time, and slot count that define a single event.

    event_date has no default: which date is "the coming Wednesday" depends on the chat's
    timezone, so the caller works it out from the chat's local today.
    """

    event_date: date
    start_time: time = DEFAULT_START_TIME
    num_slots: int = DEFAULT_NUM_SLOTS
