"""This module contains the UserData class."""

import logging
from typing import Dict, List

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
        self.poll_answer: Dict[str, List[int]] = {}
        self.user: User = None

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def init_or_update(self, user: User) -> None:
        """Init a UserData with a telegram.User object, or update if already set"""
        self.user = user

    @log.method
    def get_poll_answer(self, poll_id: str) -> List[int]:
        """Get a PollAnswer for a given poll_id"""
        return self.poll_answer.get(poll_id)

    @log.method
    def set_poll_answer(self, poll_id: str, poll_answer: List[int]) -> None:
        """Set a PollAnswer for a given poll_id"""
        self.poll_answer.update({poll_id: poll_answer})
        _logger.debug("user_data:\n%s", self)
