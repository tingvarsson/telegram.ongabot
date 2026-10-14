"""The moments a GIF can mark, and the Giphy search phrases each one draws from.

The phrases are search terms, not banter: the caption under the GIF is the message the moment
sends anyway (see quips.py and poke.py). A phrase is picked for what Giphy returns for it, so
short, well-worn reaction terms beat clever ones. Phrases are dealt like banter lines, every
phrase in a pool before any repeats, which together with the random pick among each phrase's
results keeps one mood from showing the same handful of GIFs.
"""

from enum import Enum
from typing import Dict, List

from quips import deal

# Every pool holds exactly this many phrases, so no mood is noticeably more repetitive.
PHRASES_PER_MOOD = 10


class Mood(Enum):
    """One per moment that gets a GIF. The value is used as the phrase pool's deal key."""

    BAIL = "gif_bail"
    COMEBACK = "gif_comeback"
    GHOSTED = "gif_ghosted"
    STACK_FULL = "gif_stack_full"
    CS2_WIN = "gif_cs2_win"
    CS2_LOSS = "gif_cs2_loss"
    POKE = "gif_poke"


PHRASES: Dict[Mood, List[str]] = {
    # Game to No-op: walking out on the squad.
    Mood.BAIL: [
        "rage quit",
        "abandon ship",
        "betrayal",
        "et tu brute",
        "walking away",
        "nope out",
        "i'm out",
        "leaving the party",
        "backing away slowly",
        "traitor",
    ],
    # No-op to game: back from the dead.
    Mood.COMEBACK: [
        "the return",
        "i'm back",
        "comeback",
        "never doubted you",
        "hero arrives",
        "welcome back",
        "change of heart",
        "lets go",
        "plot twist",
        "suit up",
    ],
    # A game vote pulled without a word.
    Mood.GHOSTED: [
        "disappear",
        "homer backing into bushes",
        "vanish",
        "ghosted",
        "ninja vanish",
        "sneaking out",
        "poof gone",
        "where did he go",
        "invisible",
        "smoke bomb escape",
    ],
    # A slot reached five: the stack is on.
    Mood.STACK_FULL: [
        "assemble",
        "squad goals",
        "the team is complete",
        "avengers assemble",
        "lets go team",
        "ready for battle",
        "dream team",
        "gear up",
        "full squad",
        "its happening",
    ],
    # More wins than losses on the night.
    Mood.CS2_WIN: [
        "victory dance",
        "champions",
        "we did it",
        "flawless victory",
        "celebration",
        "winning",
        "gg ez",
        "victory royale",
        "trophy celebration",
        "nailed it",
    ],
    # More losses than wins on the night.
    Mood.CS2_LOSS: [
        "this is fine",
        "crying",
        "defeat",
        "sad trombone",
        "everything is on fire",
        "disappointed",
        "facepalm",
        "rage",
        "mission failed",
        "pain",
    ],
    # The game-day poke at the members who have not voted.
    Mood.POKE: [
        "wake up",
        "waiting",
        "hello anybody there",
        "tapping fingers",
        "are you there",
        "poke",
        "still waiting",
        "knock knock",
        "staring",
        "skeleton waiting",
    ],
}


def next_phrase(mood: Mood) -> str:
    """Deal the next search phrase for mood, every phrase in its pool before any repeats."""
    return deal(mood.value, PHRASES[mood])
