"""This module contains the Event class."""
import logging
from datetime import date, datetime, timedelta
from typing import Callable

from telegram.ext import Job, JobQueue

from utils import helper, log

_logger = logging.getLogger(__name__)


class EventJob:
    """
    The EventJob object represents a event job that can be scheduled in a job queue

    Args:
        job_name: name of the job
        day_to_schedule: weekday to schedule the job on

    Attributes:
        job_name: name of the job
        day_to_schedule: weekday to schedule the job on
    """

    def __init__(self, job_name: str, day_to_schedule: str) -> None:
        self.job_name = job_name
        self.day_to_schedule = day_to_schedule

    @log.method
    def schedule(self, job_queue: JobQueue, chat_id: int, callback: Callable) -> Job:
        """Schedule this event job in the provided job_queue"""
        upcoming_date = helper.get_upcoming_date(date.today(), self.day_to_schedule)

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
            context=chat_id,
            name=self.job_name,
        )

    @log.method
    def deschedule(self, job_queue: JobQueue) -> bool:
        """Deschedule this event job"""
        current_jobs = job_queue.get_jobs_by_name(self.job_name)
        if not current_jobs:
            return False

        for job in current_jobs:
            job.schedule_removal()
        return True
