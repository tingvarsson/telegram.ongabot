"""This module builds the chat reply sent right after someone votes in an event poll.

Every reply states what happened - a first answer or a change, and from what to what - and
most add a hand-written line of banter for that exact path, e.g. bailing from game to No-op,
or a motivational one for coming back from No-op to game. See build_vote_reply for the
matrix and BANTER_BY_PATH for which pool each path draws from.
"""

import logging
import random
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

_logger = logging.getLogger(__name__)

# Every pool holds exactly this many lines, so no path gets noticeably more repetitive.
POOL_SIZE = 30
# The banter follows a lead like "Alice went from Maybe to No-op — ", so it is kept to well
# under one phone line on its own.
MAX_LINE_LENGTH = 60


class Answer(Enum):
    """What a poll answer boils down to. The value is how the reply names it."""

    GAME = "game"
    MAYBE = "Maybe"
    NO_OP = "No-op"


def categorize(option_ids: Sequence[int], num_slots: int) -> Answer:
    """Boil a (possibly multi-option) answer down to one Answer.

    The poll's first num_slots options are time slots, followed by No-op and then Maybe Baby
    (see eventcreator._create_poll_options). Any time slot counts as game, the same rule as
    UserData.calculate_played_streak. Otherwise ticking Maybe Baby - even alongside No-op -
    is closer to "unsure" than to "no", so it counts as Maybe.
    """
    if any(option_id < num_slots for option_id in option_ids):
        return Answer.GAME
    if num_slots + 1 in option_ids:
        return Answer.MAYBE
    return Answer.NO_OP


class Banter(Enum):
    """One pool of banter per path that gets one. Named after the path it is written for."""

    FIRST_MAYBE = "first_maybe"
    FIRST_NO_OP = "first_no_op"
    GAME_TO_MAYBE = "game_to_maybe"
    GAME_TO_NO_OP = "game_to_no_op"
    MAYBE_TO_NO_OP = "maybe_to_no_op"
    NO_OP_TO_MAYBE = "no_op_to_maybe"
    MAYBE_TO_GAME = "maybe_to_game"
    NO_OP_TO_GAME = "no_op_to_game"
    RETRACTED_GAME = "retracted_game"
    RETRACTED_MAYBE = "retracted_maybe"
    RETRACTED_NO_OP = "retracted_no_op"


# (previous answer, new answer) -> pool. None as previous means a first answer, None as new
# means the vote was retracted (and not replaced in time). Spelled out path by path rather
# than assembled, so every path that gets banter is visible here. A first game vote and a
# change within the same category keep their classic fixed lines, so they are absent.
BANTER_BY_PATH: Dict[Tuple[Optional[Answer], Optional[Answer]], Banter] = {
    (None, Answer.MAYBE): Banter.FIRST_MAYBE,
    (None, Answer.NO_OP): Banter.FIRST_NO_OP,
    (Answer.GAME, Answer.MAYBE): Banter.GAME_TO_MAYBE,
    (Answer.GAME, Answer.NO_OP): Banter.GAME_TO_NO_OP,
    (Answer.MAYBE, Answer.NO_OP): Banter.MAYBE_TO_NO_OP,
    (Answer.NO_OP, Answer.MAYBE): Banter.NO_OP_TO_MAYBE,
    (Answer.MAYBE, Answer.GAME): Banter.MAYBE_TO_GAME,
    (Answer.NO_OP, Answer.GAME): Banter.NO_OP_TO_GAME,
    (Answer.GAME, None): Banter.RETRACTED_GAME,
    (Answer.MAYBE, None): Banter.RETRACTED_MAYBE,
    (Answer.NO_OP, None): Banter.RETRACTED_NO_OP,
}

POOLS: Dict[Banter, List[str]] = {
    # Fence-sitting.
    Banter.FIRST_MAYBE: [
        "Schrödinger's teammate: both in and out until observed",
        "the fence is comfy, apparently",
        "keeping everyone guessing, as is tradition",
        "a firm, confident, unwavering 'eh'",
        "we'll pencil you in. Very lightly.",
        "loading... please wait",
        "one foot in the lobby, one foot on the couch",
        "the official vote of people with a backup plan",
        "commitment issues, but make it a poll",
        "that's a 50/50 we can work with",
        "hovering over the accept button like it's a mine",
        "the Maybe Baby is strong with this one",
        "we'll save a seat. Probably.",
        "maybe is just yes with stage fright",
        "reserving the right to show up dramatically",
        "a true master of the soft commit",
        "holding every option open like a CT on a stack",
        "not a no! We'll take it.",
        "the heart says yes, the calendar says hmm",
        "consulting the stars, the family and the fridge",
        "we'll know more after the vibe check",
        "buying time like a force-buy round",
        "all the hope, none of the certainty",
        "check back later, results may vary",
        "flipped a coin and it landed on its edge",
        "noncommittal, but in a charming way",
        "the classic 'I'll see how I feel'",
        "somewhere between ready and asleep",
        "we'll leave the lobby door unlocked",
        "hope springs eternal",
    ],
    # Sitting it out.
    Banter.FIRST_NO_OP: [
        "has entered witness protection for the night",
        "saving their energy for absolutely nothing",
        "checked the group chat just to say no",
        "a hard pass, delivered with confidence",
        "the couch has claimed another one",
        "benched by their own coach",
        "respect the honesty, mourn the loss",
        "one less person to blame for the loss",
        "the squad will remember this",
        "sitting this one out like a lurker in spawn",
        "gone AFK before the match even started",
        "the most decisive vote in the whole poll",
        "declining the invite, loudly",
        "has chosen peace. For tonight.",
        "No-op: does nothing, exactly as advertised",
        "going dark. Radio silence.",
        "their seat goes to the highest bidder",
        "rage-quit before the warmup",
        "at least they said it out loud",
        "someone has a life tonight, apparently",
        "chose sleep over clutches",
        "left the lobby before it was a lobby",
        "the bench appreciates the company",
        "we'll tell the stories without you",
        "a vote that simply says: nope",
        "unavailable, unbothered, unplugged",
        "sending thoughts and prayers instead of frags",
        "already in pajamas, probably",
        "zero rounds, zero regrets",
        "the lobby weeps quietly",
    ],
    # Going wobbly.
    Banter.GAME_TO_MAYBE: [
        "cold feet already?",
        "the confidence lasted about five minutes",
        "downgraded from a yes to a shrug",
        "someone checked their calendar",
        "the commitment was nice while it lasted",
        "wobbling like a jiggle-peek",
        "from locked in to loosely attached",
        "the yes has developed a slight limp",
        "hedging bets like a seasoned gambler",
        "real life has entered the chat",
        "that slot looks lonely without you",
        "someone at home has spoken, presumably",
        "going from full buy to eco",
        "wait, what happened in the last hour?",
        "the enthusiasm has left the building",
        "backpedaling at max walk speed",
        "one step back, still in the doorway",
        "the dream is alive, but on life support",
        "suddenly the vibes are uncertain",
        "retreating to the safety of the fence",
        "the yes got a little less yes",
        "we saw that, and we're choosing hope",
        "trading a sure thing for a maybe. Bold.",
        "demoted from starter to substitute",
        "second thoughts arriving right on schedule",
        "hold on, is this a slow-motion bail?",
        "the plan got downgraded to a draft",
        "turning a promise into a possibility",
        "falling back to the fence line",
        "the resolve cracked like cheap glass",
    ],
    # Bailing out.
    Banter.GAME_TO_NO_OP: [
        "cold feet, huh?",
        "bailed harder than a 1v5 retake",
        "the squad has been abandoned",
        "from locked in to logged off",
        "betrayal, in poll form",
        "Et tu, teammate?",
        "the slot is empty and so are our hearts",
        "left us hanging like a bad smoke",
        "went from carry to couch in one click",
        "the team is down a player before warmup",
        "abandoned the match. Cooldown incoming.",
        "that's a rage-quit before the first round",
        "the promise was a bluff all along",
        "we had a deal!",
        "unsubscribed from game night",
        "full retreat, no smoke, no flash",
        "picked the couch over the crew",
        "a whole slot, gone just like that",
        "gone like a drop you forgot to pick up",
        "the lineup just got shorter",
        "a tragic turn of events",
        "somebody call a vote kick. Oh wait.",
        "and just like that, the squad shrinks",
        "switched sides mid-round",
        "packed up and left without a word",
        "the retreat was swift and merciless",
        "we'll remember this at the next draft",
        "that's a teamkill on game night",
        "leaving before the bomb even got planted",
        "the audacity, honestly",
    ],
    # The maybe was a no all along.
    Banter.MAYBE_TO_NO_OP: [
        "at least it's a clear no now",
        "the maybe was a no in a trench coat",
        "saw that coming from spawn",
        "the fence finally collapsed",
        "the suspense is over, and so is the hope",
        "the box has been opened. It's a no.",
        "thanks for the honesty, eventually",
        "the coin landed. Tails.",
        "maybe baby, now maybe not",
        "we all knew, but thanks for confirming",
        "from probably not to definitely not",
        "the soft no has hardened",
        "decisive at last, just in the wrong direction",
        "the vibe check came back negative",
        "the verdict is in: couch wins",
        "the maybe has been officially retired",
        "confirmed: not coming, not sorry",
        "we'll stop saving that seat now",
        "every maybe dies a little eventually",
        "picked a side, finally. The wrong one.",
        "the hope was fun while it lasted",
        "fell off the fence, on the couch side",
        "clarity achieved, attendance not",
        "the 'we'll see' has been seen",
        "the long goodbye is complete",
        "upgraded the uncertainty to a no",
        "at least the ending wasn't a twist",
        "the mystery is solved, sadly",
        "said maybe, meant no, now says no",
        "the loading screen is done: it's a no",
    ],
    # The door opens a crack.
    Banter.NO_OP_TO_MAYBE: [
        "the door is open a crack",
        "wait, is that a pulse?",
        "the couch is losing its grip",
        "from no to hmm. Progress!",
        "something stirs in the shadows",
        "the ice is melting",
        "a comeback arc is forming",
        "we see you peeking through the blinds",
        "not a yes, but we'll take the plot twist",
        "the lobby light is back on",
        "hope has entered the chat",
        "negotiations have reopened",
        "one small step toward the lobby",
        "second thoughts, and good ones this time",
        "the no has softened. Keep going.",
        "from hard pass to soft maybe",
        "we're so back (maybe)",
        "the witness protection program has a leak",
        "reconsidering, as they should",
        "the fence is closer to the lobby side",
        "a flicker of interest detected",
        "halfway out of the pajamas",
        "defrosting nicely",
        "the bench is getting restless",
        "the no is now under review",
        "a door, a crack, a glimmer",
        "one more nudge and they're in",
        "the plot thickens",
        "reconnecting... 50%",
        "maybe is the new yes, right?",
    ],
    # Motivational: hype for committing.
    Banter.MAYBE_TO_GAME: [
        "that's the spirit!",
        "finally, a straight answer. Let's go!",
        "the squad just got stronger",
        "commitment looks good on you",
        "left the fence behind. Legend.",
        "locked in. Love to see it.",
        "welcome to the lineup!",
        "that's what we like to hear",
        "the maybe grew up to be a yes",
        "full buy, no hesitation. Respect.",
        "decisive, heroic, ready to frag",
        "now we're talking!",
        "the lobby lights up",
        "that's a clutch decision right there",
        "certified teammate energy",
        "from maybe to MVP candidate",
        "the stars aligned. See you there!",
        "this is how legends are made",
        "backing the team when it counts",
        "one more gamer, infinite more hype",
        "said yes to the squad. Hero behavior.",
        "the vibe check passed with flying colors",
        "ready up, it's happening!",
        "the doubt is gone, the frags await",
        "that's the energy we needed",
        "your seat has been warmed for you",
        "the team roars in approval",
        "commitment unlocked!",
        "good call. Great call, actually.",
        "one step closer to a full five-stack",
    ],
    # Motivational: hype for the comeback.
    Banter.NO_OP_TO_GAME: [
        "the prodigal gamer returns!",
        "comeback of the season!",
        "the couch lost. The squad won.",
        "back from the dead and ready to frag",
        "redemption arc complete",
        "that's a reconnect we love to see",
        "from benched to starting lineup!",
        "never doubted you. Okay, briefly.",
        "the hero we needed tonight",
        "the lobby just got a lot louder",
        "plot twist of the week!",
        "respawned and ready",
        "a true legend changes plans for the team",
        "the no has been overruled. Welcome back!",
        "out of retirement for one more night",
        "pajamas off, headset on!",
        "the squad celebrates this U-turn",
        "from no-show to showtime",
        "choosing glory over sleep. Respect.",
        "out of witness protection and into the lobby",
        "that's a 1v5 clutch of a decision",
        "welcome back, soldier",
        "the comeback kid strikes again",
        "the bench is empty, the lobby is full",
        "saw the light. The RGB light.",
        "the team is whole again!",
        "turned it around like a pistol-round win",
        "the best kind of flip-flop",
        "hype levels rising!",
        "grab a seat, the party just got better",
    ],
    # Ghosting the lobby.
    Banter.RETRACTED_GAME: [
        "ghosting the lobby, are we?",
        "the slot has been vacated without notice",
        "gone without a trace or a goodbye",
        "vanished like a ninja defuse",
        "the vote evaporated. Suspicious.",
        "the checkbox is empty and so is the slot",
        "the seat is empty and nobody knows why",
        "disconnected. Reconnect pending?",
        "we'll wait by the lobby. Forever, maybe.",
        "silent exit, loud implications",
        "the vote got un-voted",
        "a vote was here. Now it's not.",
        "no yes, no no, just vibes",
        "Houdini would be proud",
        "this feels like the start of a bail",
        "the squad looks around nervously",
        "going stealth mode on game night",
        "the ctrl+z of commitments",
        "timed out like a bad connection",
        "the lineup has a mysterious gap",
        "we noticed. We always notice.",
        "packing up quietly, hoping nobody saw",
        "retreated without calling it",
        "the slot is up for grabs again",
        "shadow-realmed their own vote",
        "now you see it, now you don't",
        "a vote in the hand was worth two in the bush",
        "left the server with no explanation",
        "the audacity of an empty checkbox",
        "unplugged from the plan, it seems",
    ],
    # Not even a maybe.
    Banter.RETRACTED_MAYBE: [
        "not even a maybe anymore",
        "too uncommitted even for maybe",
        "the fence got too crowded",
        "maybe has become maybe not, maybe",
        "from uncertain to unknown",
        "a new low in commitment",
        "the maybe went out to get milk",
        "even the fence was too much pressure",
        "the soft commit went softer",
        "wavering has evolved into vanishing",
        "the question mark just left",
        "an answer so vague it disappeared",
        "fading out like a flash in daylight",
        "undecided about being undecided",
        "retracted the maybe. Impressive, somehow.",
        "the fog of war thickens",
        "committed to not committing",
        "the Maybe Baby left the nursery",
        "the most maybe move possible",
        "now officially unknown",
        "the coin rolled under the couch",
        "somewhere between here and nowhere",
        "the maybe got cold feet too",
        "a vote of no confidence in their own vote",
        "that was a lot of hmm",
        "the hope meter just dropped",
        "answer pending, indefinitely",
        "from 50/50 to 0/0",
        "the ghost of a maybe lingers",
        "keeping us guessing at expert level",
    ],
    # Can't even commit to no.
    Banter.RETRACTED_NO_OP: [
        "can't even commit to no",
        "the no was too much commitment",
        "unsaying the no. Interesting...",
        "the no is gone. Is a yes coming?",
        "the door just creaked open",
        "an ex-no. A former no.",
        "the couch lost its grip for a moment",
        "undoing the no is basically a yes, right?",
        "we're choosing to read this as hope",
        "the no has left the building",
        "suspiciously close to changing their mind",
        "no longer a no. Not yet a yes.",
        "stay tuned for the next episode",
        "the rejection has been rejected",
        "a double negative, poll edition",
        "pulled the no, left us hoping",
        "the bench is empty. Where did they go?",
        "is this a comeback in slow motion?",
        "the veto has been vetoed",
        "we saw that little flicker of hope",
        "not coming, not not coming",
        "the decline was declined",
        "the lobby holds its breath",
        "un-no-ing is a bold strategy",
        "the no evaporated. Draw your own conclusions.",
        "a hard pass turned soft and disappeared",
        "maybe the couch wasn't that comfy",
        "rethinking the whole no thing",
        "a no-op on the no-op",
        "the refusal has been refunded",
    ],
}

# Per-pool shuffled decks, dealt from the end, and the line each pool dealt last. Kept in
# memory only - after a restart every pool is simply reshuffled.
_bags: Dict[Banter, List[str]] = {}
_last: Dict[Banter, str] = {}


def next_banter(kind: Banter) -> str:
    """Deal the next line from kind's pool.

    Lines come from a shuffled deck, so all POOL_SIZE lines are used before any repeats, and
    a fresh shuffle never starts with the line that was just dealt.
    """
    bag = _bags.get(kind)
    if not bag:
        bag = list(POOLS[kind])
        random.shuffle(bag)
        # Dealt from the end: swap the previous deck's last line away from the top.
        if len(bag) > 1 and bag[-1] == _last.get(kind):
            bag[0], bag[-1] = bag[-1], bag[0]
        _bags[kind] = bag
        _logger.debug("Reshuffled banter pool %s", kind.name)
    line = bag.pop()
    _last[kind] = line
    return line


def build_vote_reply(name: str, previous: Optional[Answer], new: Answer) -> str:
    """Build the reply to a vote. previous is None for a user's first answer to the poll."""
    if previous is None and new is Answer.GAME:
        return f"Wow {name}, what a great job answering that poll!"
    if previous is new:
        # Covers slot-to-slot moves, like 19.00 -> 19.40, as well as re-voting the same thing.
        return f"Hmm suspicious, looks like {name} changed their vote..."
    if previous is None:
        lead = f"{name} votes {new.value}"
    else:
        lead = f"{name} went from {previous.value} to {new.value}"
    kind = BANTER_BY_PATH[(previous, new)]
    _logger.debug("Vote reply for %s uses banter pool %s", name, kind.name)
    return f"{lead} — {next_banter(kind)}"


def build_retraction_reply(name: str, previous: Answer) -> str:
    """Build the reply to a vote that was retracted and not replaced in time."""
    kind = BANTER_BY_PATH[(previous, None)]
    return f"{name} pulled their {previous.value} vote — {next_banter(kind)}"
