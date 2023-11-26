"""This module contains the EventJob class."""
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
        chat_id: id of the chat the event belongs to
        day_to_schedule: weekday to schedule the job on

    Attributes:
        chat_id: id of the chat the event belongs to
        day_to_schedule: weekday to schedule the job on
        job_name: name of the job as used in JobQueue
    """

    def __init__(self, chat_id: int, day_to_schedule: str) -> None:
        self.chat_id = chat_id
        self.day_to_schedule = day_to_schedule

        self.job_name = f"weeky_event_{chat_id}"

    @log.method
    def schedule(self, job_queue: JobQueue, callback: Callable) -> Job:
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
            chat_id=self.chat_id,
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

    @log.method
    def check_if_job_exists(self, job_queue: JobQueue) -> bool:
        """Return true or false whether job already exists in job_queue"""
        current_jobs = job_queue.get_jobs_by_name(self.job_name)
        if not current_jobs:
            return False
        return True
