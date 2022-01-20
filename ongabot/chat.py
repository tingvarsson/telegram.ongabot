"""This module contains the Chat class."""
import logging
from typing import Callable, Dict

from telegram import Message
from telegram.ext import JobQueue

from event import Event
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
        events: dictionary of Event objects indexed on poll_id
        event_job: EventJob if there is one scheduled for the chat, otherwise None
        pinned_poll: telegram.Message of a pinned event poll message if any, otherwise None
    """

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id

        self.events: Dict[str, Event] = {}
        self.event_job: EventJob = None
        self.pinned_poll: Message = None

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def add_event(self, event: Event) -> bool:
        """Add an Event to BotData"""
        if self.events.get(event.poll_id):
            _logger.error("Event with poll_id=%s already exist in BotData!", event.poll_id)
            return False

        self.events.update({event.poll_id: event})
        return True

    @log.method
    def get_event(self, poll_id: str) -> Event:
        """Get an event from BotData"""

        if not self.events.get(poll_id):
            _logger.error("Event with poll_id=%s doesn't exist in BotData!", poll_id)
            return None

        return self.events.get(poll_id)

    @log.method
    def remove_event(self, poll_id: str) -> None:
        """Remove an event from BotData"""
        if self.events.get(poll_id):
            self.events.pop(poll_id)

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
        if self.event_job:
            _logger.error(
                "job_name=%s already exist Chat with chat_id=%s!", event_job.job_name, self.chat_id
            )
            return False

        self.event_job = event_job
        return True

    @log.method
    def remove_event_job(self, job_queue: JobQueue) -> bool:
        """Remove an event job"""
        if not self.event_job:
            _logger.debug("Trying to remove event_job=None")
            return False

        result = self.event_job.deschedule(job_queue)
        self.event_job = None
        return result

    @log.method
    def schedule_event_job(self, job_queue: JobQueue, callback: Callable) -> None:
        """Schedule event job if it exist"""
        if self.event_job:
            self.event_job.schedule(job_queue, callback)
