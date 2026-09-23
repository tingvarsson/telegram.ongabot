"""Emoji sentiment mapping for reactions left on a posted YouTube Short.

A Telegram MessageReactionUpdated carries both the reaction set before and after the change,
not a single "current" set - a removed reaction must undo its earlier score effect, not be
silently ignored. reaction_score_delta is the only entry point: it diffs old vs. new and
returns the net score.py delta to apply via topics.apply_reaction.
"""

from typing import FrozenSet, Sequence

from telegram import ReactionType, ReactionTypeEmoji
from telegram.constants import ReactionEmoji

from youtube.topics import REACTION_STEP

POSITIVE_EMOJI: FrozenSet[str] = frozenset({ReactionEmoji.THUMBS_UP, ReactionEmoji.RED_HEART, ReactionEmoji.FIRE})
NEGATIVE_EMOJI: FrozenSet[str] = frozenset({ReactionEmoji.THUMBS_DOWN, ReactionEmoji.PILE_OF_POO})


def _emoji_set(reactions: Sequence[ReactionType]) -> FrozenSet[str]:
    """The plain emoji characters in a reaction set - custom/paid reactions have none."""
    return frozenset(r.emoji for r in reactions if isinstance(r, ReactionTypeEmoji))


def reaction_score_delta(old_reaction: Sequence[ReactionType], new_reaction: Sequence[ReactionType]) -> float:
    """Net score delta for the change between old_reaction and new_reaction.

    Added positive -> +REACTION_STEP, added negative -> -REACTION_STEP, and a removal has the
    opposite sign of its addition, so retracting a thumbs-up undoes its earlier boost rather
    than being a no-op. Unmapped emoji (and non-emoji reaction types) contribute nothing.
    """
    old_emoji = _emoji_set(old_reaction)
    new_emoji = _emoji_set(new_reaction)
    added = new_emoji - old_emoji
    removed = old_emoji - new_emoji

    delta = 0.0
    for emoji in added:
        if emoji in POSITIVE_EMOJI:
            delta += REACTION_STEP
        elif emoji in NEGATIVE_EMOJI:
            delta -= REACTION_STEP
    for emoji in removed:
        if emoji in POSITIVE_EMOJI:
            delta -= REACTION_STEP
        elif emoji in NEGATIVE_EMOJI:
            delta += REACTION_STEP
    return delta
