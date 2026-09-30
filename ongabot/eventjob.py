"""This module contains the EventJob class."""

import logging
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Callable, Optional

from telegram.ext import Job, JobQueue

from eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME, EventData
from utils import helper, log

_logger = logging.getLogger(__name__)

DEFAULT_TRIGGER_DAY = "sunday"
# Wall-clock time in the chat's timezone at which the weekly poll is created.
TRIGGER_TIME = time(20, 0)


def ptb_weekday(day_name: str) -> int:
    """Map a weekday name to JobQueue.run_daily's day numbering.

    python-telegram-bot counts 0 = Sunday .. 6 = Saturday, unlike datetime.weekday()'s
    0 = Monday; mixing the two up silently moves the poll a day.
    """
    return (helper.get_weekday_index_from_name(day_name) + 1) % 7


class EventJob:
    """
    The EventJob object represents a event job that can be scheduled in a job queue

    Args:
        chat_id: id of the chat the event belongs to
        trigger_on: weekday on which to trigger the job (when to create the poll)
        event_day: weekday the created poll refers to (which day the event is on)
        start_time: start time for the first poll option
        num_slots: number of time-slot options in the poll

    Attributes:
        chat_id: id of the chat the event belongs to
        trigger_on: weekday on which to trigger the job
        event_day: weekday the created poll refers to
        start_time: start time for the first poll option
        num_slots: number of time-slot options in the poll
        job_name: name of the job as used in JobQueue
        last_triggered_on: chat-local date the job last created a poll, or None if it has not
            since this was tracked - what tells a missed trigger apart after a restart
    """

    def __init__(
        self,
        chat_id: int,
        trigger_on: str = DEFAULT_TRIGGER_DAY,
        event_day: str = DEFAULT_EVENT_DAY,
        start_time: time = DEFAULT_START_TIME,
        num_slots: int = DEFAULT_NUM_SLOTS,
    ) -> None:
        self.chat_id = chat_id
        self.trigger_on = trigger_on
        self.event_day = event_day
        self.start_time = start_time
        self.num_slots = num_slots
        self.last_triggered_on: Optional[date] = None

        self.job_name = f"weeky_event_{chat_id}"  # typo preserved for persistence compatibility

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Set default values for any missing attributes (for backward compatibility with older persisted data)
        if not hasattr(self, "trigger_on"):
            old = self.__dict__.pop("day_to_schedule", None)
            if old is not None:
                self.trigger_on = old
            else:
                self.trigger_on = DEFAULT_TRIGGER_DAY
        if not hasattr(self, "event_day"):
            self.event_day = DEFAULT_EVENT_DAY
        if not hasattr(self, "start_time"):
            self.start_time = DEFAULT_START_TIME
        if not hasattr(self, "num_slots"):
            self.num_slots = DEFAULT_NUM_SLOTS
        if not hasattr(self, "last_triggered_on"):
            self.last_triggered_on = None

    @log.method
    def schedule(self, job_queue: JobQueue, callback: Callable, tz: tzinfo) -> Job:
        """Schedule this event job in the provided job_queue, at TRIGGER_TIME in tz.

        run_daily is cron-based, so the poll stays at the same local time across a DST change,
        which a fixed one-week interval would not.
        """
        _logger.info(
            "Scheduling event job for chat_id=%s every %s at %s %s with event day %s, start time %s, and %s slots",
            self.chat_id,
            self.trigger_on,
            TRIGGER_TIME,
            tz,
            self.event_day,
            self.start_time,
            self.num_slots,
        )
        return job_queue.run_daily(
            callback,
            time=TRIGGER_TIME.replace(tzinfo=tz),
            days=(ptb_weekday(self.trigger_on),),
            chat_id=self.chat_id,
            name=self.job_name,
        )

    def missed_event_date(self, now: datetime) -> Optional[date]:
        """The event date whose poll a trigger missed while the bot was down, or None.

        now is aware, in the chat's timezone. A trigger counts as missed when its most recent
        occurrence is due, the job has not run on or after that day, and the event it would have
        created has not happened yet. Without a record of the last run nothing counts as missed,
        so a job from before that was tracked never creates a poll on its own at startup.
        """
        if self.last_triggered_on is None:
            return None

        # Most recent trigger at or before now. Aware wall-clock arithmetic keeps it at 20:00
        # local on both sides of a DST change.
        days_back = (now.weekday() - helper.get_weekday_index_from_name(self.trigger_on)) % 7
        trigger = datetime.combine(now.date() - timedelta(days=days_back), TRIGGER_TIME, tzinfo=now.tzinfo)
        if trigger > now:
            trigger -= timedelta(weeks=1)

        if self.last_triggered_on >= trigger.date():
            return None
        event_date = helper.get_upcoming_date(trigger.date(), self.event_day)
        if event_date < now.date():
            return None
        return event_date

    @log.method
    def deschedule(self, job_queue: JobQueue) -> bool:
        """Deschedule this event job"""
        current_jobs = job_queue.get_jobs_by_name(self.job_name)
        if not current_jobs:
            _logger.info("No jobs found to deschedule.")
            return False

        for job in current_jobs:
            job.schedule_removal()
        return True

    @log.method
    def to_event_data(self, today: date) -> EventData:
        """Build a concrete EventData for the next occurrence of this job's event day from today.

        today is the chat's local date, so an event late on Sunday evening still lands on the
        chat's coming Wednesday wherever the host runs.
        """
        event_date = helper.get_upcoming_date(today, self.event_day)
        return EventData(event_date, self.start_time, self.num_slots)
