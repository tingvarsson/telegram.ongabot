"""This module contains the UserData class."""

import logging
from datetime import date
from typing import Callable, Dict, Optional, Tuple

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
        steam64_id: Steam64 this user linked via /linksteam, or None when unlinked. UserData
            is keyed globally by user id, so one link serves every chat the user is in.
    """

    def __init__(self) -> None:
        self.poll_answer: Dict[str, Tuple[int, ...]] = {}
        self.user: Optional[User] = None
        self.steam64_id: Optional[str] = None

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Set default values for any missing attributes (for backward compatibility with older persisted data)
        if not hasattr(self, "steam64_id"):
            # Linking is opt-in consent, so nobody is linked retroactively.
            self.steam64_id = None

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def set_steam64_id(self, steam64_id: Optional[str]) -> None:
        """Link this user to a Steam64, or pass None to unlink."""
        self.steam64_id = steam64_id
        _logger.debug("user_data:\n%s", self)

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

    def _streak(self, poll_id_to_date: Dict[str, date], participated: Callable[[str], bool]) -> int:
        """Count consecutive most-recent events (newest first) for which participated() holds.

        Only polls present in poll_id_to_date are considered, so a poll the caller filtered
        out (e.g. a cancelled event) is skipped rather than breaking the streak.
        """
        events_by_date = sorted(poll_id_to_date.items(), key=lambda x: x[1], reverse=True)
        streak = 0
        for poll_id, _ in events_by_date:
            if not participated(poll_id):
                break
            streak += 1
        return streak

    @log.method
    def calculate_streak(self, poll_id_to_date: Dict[str, date]) -> int:
        """Return the number of consecutive most-recent events this user voted in.

        Any non-empty answer counts, including the non-slot No-op and Maybe Baby </3
        options - this is a response streak. See calculate_played_streak for slot picks only.
        """
        return self._streak(poll_id_to_date, lambda poll_id: bool(self.poll_answer.get(poll_id)))

    @log.method
    def calculate_played_streak(self, poll_id_to_date: Dict[str, date], poll_id_to_num_slots: Dict[str, int]) -> int:
        """Return the number of consecutive most-recent events this user picked a time slot in.

        A poll's first num_slots options are the time slots; No-op and Maybe Baby </3 are
        appended after them (see eventcreator._create_poll_options), so an answer counts as
        played only if it holds an option id below that event's num_slots. A poll missing from
        poll_id_to_num_slots defaults to 0 slots, i.e. nothing can be confirmed as a slot pick
        and the streak breaks.
        """

        def played(poll_id: str) -> bool:
            num_slots = poll_id_to_num_slots.get(poll_id, 0)
            return any(option_id < num_slots for option_id in self.poll_answer.get(poll_id, ()))

        return self._streak(poll_id_to_date, played)
