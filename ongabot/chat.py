"""This module contains the Chat class."""
import logging
from typing import Callable, Dict

from telegram import Message
from telegram.ext import JobQueue

from eventjob import EventJob
from utils import log

_logger = logging.getLogger(__name__)


class Chat:
    """
    The Chat object represents a chat and related data

    Args:
        chat_id: id of the chat the data belongs to

    Attributes:
        chat_id: id of the chat the data belongs to
        event_jobs: dictionary of job_name:day_to_schedule
        pinned_poll: telegram.Message of a pinned event poll message
    """

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id

        self.event_jobs: Dict[str, EventJob] = {}
        self.pinned_poll: Message = None

    @log.method
    def add_pinned_poll(self, message: Message) -> bool:
        """Add a pinned event poll message"""
        if self.pinned_poll:
            _logger.error("pinned_poll=%s already exist when adding=%s", self.pinned_poll, message)
            return False

        self.pinned_poll = message
        return True

    @log.method
    def get_pinned_poll(self) -> Message:
        """Get a pinned event poll message"""
        return self.pinned_poll

    @log.method
    def remove_pinned_poll(self) -> None:
        """Remove a pinned event poll message"""
        if not self.pinned_poll:
            _logger.debug("Trying to remove pinned_poll=None")
        self.pinned_poll = None

    @log.method
    def add_event_job(self, event_job: EventJob) -> bool:
        """Add an event job"""
        if self.event_jobs.get(event_job.job_name):
            _logger.error(
                "job_name=%s already exist Chat with chat_id=%s!", event_job.job_name, self.chat_id
            )
            return False

        self.event_jobs.update({event_job.job_name: event_job})
        return True

    @log.method
    def remove_event_job(self, job_name: str, job_queue: JobQueue) -> bool:
        """Remove an event job"""
        event_job = self.event_jobs.pop(job_name, None)

        if event_job:
            return event_job.deschedule(job_queue)

        return False

    @log.method
    def schedule_all_event_jobs(self, job_queue: JobQueue, callback: Callable) -> None:
        """Schedule all event jobs"""
        for event_job in self.event_jobs.values():
            event_job.schedule(job_queue, self.chat_id, callback)
