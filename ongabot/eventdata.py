"""This module contains the EventData dataclass."""

from dataclasses import dataclass, field
from datetime import date, time

from utils import helper

DEFAULT_EVENT_DAY = "wednesday"
DEFAULT_START_TIME = time(18, 30)
DEFAULT_NUM_SLOTS = 5


def _default_event_date() -> date:
    return helper.get_upcoming_date(date.today(), DEFAULT_EVENT_DAY)


@dataclass
class EventData:
    """Groups the concrete date, start time, and slot count that define a single event."""

    event_date: date = field(default_factory=_default_event_date)
    start_time: time = DEFAULT_START_TIME
    num_slots: int = DEFAULT_NUM_SLOTS
