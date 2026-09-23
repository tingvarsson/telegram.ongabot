"""This module contains the quip lines used to call out No-op and Maybe Baby voters."""

import random
from typing import Sequence

NO_OP_QUIPS: list[str] = [
    "has entered witness protection for the night",
    "is saving their energy for absolutely nothing",
    "checked the group chat just to say no",
    "voted with their whole chest: not today",
]

MAYBE_BABY_QUIPS: list[str] = [
    "is keeping their options open, and everyone else waiting",
    "will decide the exact moment it stops mattering",
    "is playing hard to schedule",
    "left the door 3% open, for legal reasons",
]


def select_quip(quips: Sequence[str], poll_id: str, user_id: int, option_index: int) -> str:
    """Deterministically pick a quip for a (poll, user, option) triple.

    Seeded on the identifiers rather than stored anywhere, so repeated renders of the
    same status message show the same quip for a given voter without persisting state.
    """
    return random.Random(f"{poll_id}:{user_id}:{option_index}").choice(quips)
