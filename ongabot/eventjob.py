"""This module contains the EventJob class."""

import logging
from datetime import date, datetime, time, timedelta
from typing import Callable

from telegram.ext import Job, JobQueue

from eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME, EventData
from utils import helper, log

_logger = logging.getLogger(__name__)

DEFAULT_TRIGGER_DAY = "sunday"


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

    @log.method
    def schedule(self, job_queue: JobQueue, callback: Callable) -> Job:
        """Schedule this event job in the provided job_queue"""
        upcoming_date = helper.get_upcoming_date(date.today(), self.trigger_on)

        _logger.info(
            "Scheduling event job for chat_id=%s on %s (upcoming date: %s) "
            "with event day %s, start time %s, and %s slots",
            self.chat_id,
            self.trigger_on,
            upcoming_date,
            self.event_day,
            self.start_time,
            self.num_slots,
        )
        return job_queue.run_repeating(
            callback,
            interval=timedelta(weeks=1),
            first=datetime(
                upcoming_date.year,
                upcoming_date.month,
                upcoming_date.day,
                20,
                0,
                0,
            ),
            chat_id=self.chat_id,
            name=self.job_name,
        )

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
    def to_event_data(self) -> EventData:
        """Build a concrete EventData for the next upcoming occurrence of this job's event day."""
        event_date = helper.get_upcoming_date(date.today(), self.event_day)
        return EventData(event_date, self.start_time, self.num_slots)
