"""Which moments get a GIF, and how each one goes out.

Four moments get one: a dramatic vote swing (bailing, coming back, or quietly pulling a game
vote), a time slot reaching a full stack, the CS2 night's verdict and the game-day poke. The
first three are decided here; the poke only needs its mood (see poke.py).

Swings are the only moment that can happen many times a night, so they are rationed: a dice
roll, and a per-chat cooldown after each GIF. The cooldown is in memory only - a restart just
lets the next swing roll straight away.
"""

import logging
import random
import time
from typing import Dict, Optional, Tuple

from telegram import Bot, ReplyParameters

from chat import Chat
from cs2.session import Cs2Session
from gifs.moods import Mood
from gifs.send import send_with_gif
from quips import Answer

_logger = logging.getLogger(__name__)

# The share of dramatic swings that get a GIF, so it stays a surprise.
SWING_GIF_CHANCE = 1 / 3
# The least time between two swing GIFs in one chat, so a lively evening is no GIF wall.
SWING_GIF_COOLDOWN_SECONDS = 30 * 60

# (previous answer, new answer) -> mood, for the swings that get a GIF. None as new means the
# vote was pulled and not replaced in time. Any other path is text only.
SWING_MOODS: Dict[Tuple[Optional[Answer], Optional[Answer]], Mood] = {
    (Answer.GAME, Answer.NO_OP): Mood.BAIL,
    (Answer.NO_OP, Answer.GAME): Mood.COMEBACK,
    (Answer.GAME, None): Mood.GHOSTED,
}

# chat_id -> when its last swing GIF was granted, on _clock.
_last_swing_gif: Dict[int, float] = {}


def _clock() -> float:
    """Seconds on a monotonic clock. A function so tests can move time."""
    return time.monotonic()


def reset() -> None:
    """Forget every chat's swing cooldown. For tests."""
    _last_swing_gif.clear()


def swing_mood(previous: Optional[Answer], new: Optional[Answer]) -> Optional[Mood]:
    """The mood of a vote swing, or None for a path that never gets a GIF."""
    return SWING_MOODS.get((previous, new))


def gated_swing_mood(chat_id: int, previous: Optional[Answer], new: Optional[Answer]) -> Optional[Mood]:
    """The swing's mood if this one gets a GIF: a dramatic path, past the cooldown, and a won roll.

    Granting a GIF starts the chat's cooldown, whether or not one is found in the end.
    """
    mood = swing_mood(previous, new)
    if mood is None:
        return None
    since = _clock() - _last_swing_gif.get(chat_id, float("-inf"))
    if since < SWING_GIF_COOLDOWN_SECONDS:
        _logger.info("No %s GIF for chat_id=%s: cooldown, last one %.0fs ago", mood.name, chat_id, since)
        return None
    if random.random() >= SWING_GIF_CHANCE:
        _logger.info("No %s GIF for chat_id=%s: lost the roll", mood.name, chat_id)
        return None
    _last_swing_gif[chat_id] = _clock()
    _logger.info("Swing in chat_id=%s gets a %s GIF", chat_id, mood.name)
    return mood


def stack_full_text(slot: str) -> str:
    """The celebration for a time slot, e.g. "19.10", reaching a full stack."""
    return f"🎉 Five-stack at {slot}!"


async def send_stack_celebration(bot: Bot, chat: Chat, poll_id: str, slot: str) -> None:
    """Celebrate slot reaching a full stack, replying to the event's poll while it is pinned.

    Sent as text when no GIF is found: the celebration is news on its own. Raises TelegramError
    when even the text fails.
    """
    poll_message = chat.pinned_polls.get(poll_id)
    # A poll deleted since must not stop the celebration, hence allow_sending_without_reply.
    reply = ReplyParameters(poll_message.message_id, allow_sending_without_reply=True) if poll_message else None
    await send_with_gif(
        bot,
        chat,
        stack_full_text(slot),
        Mood.STACK_FULL,
        reply_parameters=reply,
        disable_notification=chat.is_quiet(),
    )
    _logger.info("Celebrated a full stack at %s in chat_id=%s", slot, chat.chat_id)


def cs2_verdict(session: Cs2Session) -> Optional[Tuple[Mood, str]]:
    """The night's mood and caption, e.g. "Night's over: 2W 1L", or None for an even night.

    Draws are shown when there are any, but only wins against losses decide the mood.
    """
    outcomes = [match.outcome for match in session.matches]
    wins, losses, draws = outcomes.count("W"), outcomes.count("L"), outcomes.count("D")
    if wins == losses:
        return None
    caption = f"Night's over: {wins}W {losses}L" + (f" {draws}D" if draws else "")
    return (Mood.CS2_WIN if wins > losses else Mood.CS2_LOSS), caption


async def send_cs2_verdict(
    bot: Bot, chat: Chat, session: Cs2Session, results_message_id: int, disable_notification: bool = False
) -> None:
    """Reply to the final CS2 results with a GIF for the night, when it was not an even one.

    GIF only: the results already say everything the caption does, so nothing is sent without
    a GIF, and a failure is only logged.
    """
    verdict = cs2_verdict(session)
    if verdict is None:
        _logger.info("No CS2 verdict GIF for chat_id=%s: an even night", chat.chat_id)
        return
    mood, caption = verdict
    await send_with_gif(
        bot,
        chat,
        caption,
        mood,
        reply_parameters=ReplyParameters(results_message_id, allow_sending_without_reply=True),
        disable_notification=disable_notification,
        text_fallback=False,
    )
