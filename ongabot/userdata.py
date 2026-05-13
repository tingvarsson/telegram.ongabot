"""This module contains the UserData class."""

import logging
from datetime import date
from typing import Dict, Optional, Tuple

from telegram import User

from utils import log

_logger = logging.getLogger(__name__)


class UserData:
    """
    The UserData object represent all persistent data stored for a specific user

    Args:

    Attributes:
        poll_answer: Dict of telegram.PollAnswer given by this user indexed by poll_id
        user: telegram.User object for this user - has to be initialized via init()
    """

    def __init__(self) -> None:
        self.poll_answer: Dict[str, Tuple[int, ...]] = {}
        self.user: Optional[User] = None

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def init_or_update(self, user: User) -> None:
        """Init a UserData with a telegram.User object, or update if already set"""
        self.user = user

    @log.method
    def get_poll_answer(self, poll_id: str) -> Optional[Tuple[int, ...]]:
        """Get a PollAnswer for a given poll_id"""
        return self.poll_answer.get(poll_id)

    @log.method
    def set_poll_answer(self, poll_id: str, poll_answer: Tuple[int, ...]) -> None:
        """Set a PollAnswer for a given poll_id"""
        self.poll_answer.update({poll_id: poll_answer})
        _logger.debug("user_data:\n%s", self)

    @log.method
    def calculate_streak(self, poll_id_to_date: Dict[str, date]) -> int:
        """Return the number of consecutive most-recent events this user voted in."""
        events_by_date = sorted(poll_id_to_date.items(), key=lambda x: x[1], reverse=True)
        streak = 0
        for poll_id, _ in events_by_date:
            if poll_id in self.poll_answer and self.poll_answer[poll_id]:
                streak += 1
            else:
                break
        return streak
