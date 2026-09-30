"""The /shrink session: a mock diagnosis of someone's voting habits, read from the chat's history.

The numbers are the same per-user ones /statistics shows (see utils.statistics). diagnose picks
the first Diagnosis whose rule matches, in the order its rules are listed, and the reply closes with a
treatment line dealt from that diagnosis' pool the same way vote banter is (see quips.deal).
"""

import logging
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from telegram import User

from chat import Chat
from quips import deal
from utils.statistics import UserStatRow, compute_statistics

_logger = logging.getLogger(__name__)

# Fewer polls than this on file (answered or ignored since first seen) is too early to tell.
MIN_POLLS = 3
# Share of polls on file ignored altogether.
AVOIDANT_SHARE = 0.5
# Shares of answers that were Maybe Baby </3 or No-op.
FENCE_SITTING_SHARE = 0.3
COUCH_SHARE = 0.4
# Average slots picked per night played, over at least HOARDING_MIN_PLAYED nights.
HOARDING_SLOTS_AVG = 4.0
HOARDING_MIN_PLAYED = 3
# Share of polls on file with an actual slot pick.
LOBBY_DEPENDENCY_SHARE = 0.8

BOT_PATIENT_TEXT = "I don't treat bots. Conflict of interest."

# A treatment follows "Treatment: ", so it is kept to well under one phone line on its own.
MAX_TREATMENT_LENGTH = 50


class Diagnosis(Enum):
    """What a patient is diagnosed with. The value is how the reply names it."""

    NEW_PATIENT = "New Patient"
    AVOIDANT = "Avoidant Poll Disorder"
    FENCE_SITTING = "Chronic Fence-Sitting"
    COUCH = "Couch Attachment Disorder"
    SLOT_HOARDING = "Compulsive Slot Hoarding"
    LOBBY_DEPENDENCY = "Acute Lobby Dependency"
    UNREMARKABLE = "Clinically Unremarkable"


# Treatment lines, at most MAX_TREATMENT_LENGTH each.
TREATMENTS: Dict[Diagnosis, List[str]] = {
    Diagnosis.NEW_PATIENT: [
        "come back after a few more polls",
        "the file is thin, the couch is warm",
        "vote a few times, then we'll talk",
        "too early to tell. Keep voting.",
        "first sessions are always awkward",
        "no diagnosis yet. Suspiciously clean record.",
        "we're still getting to know each other",
        "fill in a couple of polls and book again",
        "the doctor needs more data. And coffee.",
        "no symptoms yet, give it a few Wednesdays",
    ],
    Diagnosis.AVOIDANT: [
        "answer one poll a week, with or without food",
        "turn notifications on. Yes, all of them.",
        "a No-op is still an answer. Try it.",
        "practice saying 'yes', 'no' or even 'maybe'",
        "exposure therapy: open the group chat daily",
        "mute is not a coping strategy",
        "tap any option. The poll doesn't bite.",
        "we miss you. The poll misses you more.",
        "ghosting is for Halloween, not game night",
        "five minutes a week for feelings and polls",
    ],
    Diagnosis.FENCE_SITTING: [
        "pick a side. Any side. The fence is splintering.",
        "20mg of commitment, taken before voting",
        "say yes or no out loud, three times a day",
        "Schrödinger was a scientist, not a role model",
        "flip a coin, then actually believe it",
        "the Maybe button is for emergencies only now",
        "commitment exercises: start with lunch plans",
        "try a yes. Side effects may include fun.",
        "your calendar called. It wants a decision.",
        "less 'we'll see', more 'see you there'",
    ],
    Diagnosis.COUCH: [
        "one full buy, twice a week, with water",
        "gradual separation from the couch, from tonight",
        "the couch will still be there after the match",
        "swap pajamas for a headset, one night at a time",
        "stand up. Stretch. Queue up.",
        "the squad prescribes one Wednesday, no excuses",
        "No-op is a vote, not a lifestyle",
        "fresh air, then fresh frags",
        "try one slot. Just the one. For science.",
        "a warm-up match counts as cardio",
    ],
    Diagnosis.SLOT_HOARDING: [
        "you can only play one slot at a time. Probably.",
        "leave some slots for the rest of us",
        "tick fewer boxes, gain more sleep",
        "enthusiasm this strong should be bottled",
        "no treatment needed. Keep hoarding.",
        "every slot at once is a lifestyle, not a vote",
        "clear your whole evening. Oh, you already did.",
        "hydrate between slots",
        "a gentle reminder that sleep is also a slot",
        "your availability is a medical marvel",
    ],
    Diagnosis.LOBBY_DEPENDENCY: [
        "no cure needed. The squad depends on you too.",
        "touch grass. Once. Then back to the lobby.",
        "prescribing one night off. Ignore as needed.",
        "this is the healthiest file in the cabinet",
        "your attendance has been donated to science",
        "keep doing what you're doing. Bring snacks.",
        "chronic, incurable and frankly admirable",
        "the lobby is your happy place, and that's fine",
        "mild dependency, maximum frags",
        "see a sunset some time. After the match.",
    ],
    Diagnosis.UNREMARKABLE: [
        "perfectly normal, which is suspicious",
        "nothing to fix. Try being more dramatic.",
        "a file so average it's boring. Congrats.",
        "some Maybe, some game, all balance",
        "remarkably unremarkable. Carry on.",
        "prescribing one wild card vote, for flavour",
        "stable, balanced and a bit mysterious",
        "the median gamer. A noble calling.",
        "come back when you've developed a quirk",
        "healthy habits. Please don't tell the others.",
    ],
}


def _count(number: int, noun: str) -> str:
    """'1 time', '3 times'."""
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def diagnose(row: UserStatRow) -> Tuple[Diagnosis, str]:
    """Diagnose one user's statistics row: the first rule that matches, and its findings.

    Rules are checked in the order they are written here, so e.g. someone who both ignores
    most polls and answers Maybe when they do is Avoidant, the bigger problem of the two.
    """
    polls = row.responses + row.didnt_bother
    answers = row.responses
    # (diagnosis, does it match, its findings). Both are lazy: the shares of answers are only
    # computed once the Avoidant rule has not matched, and by then answers > 0, since someone
    # with none ignored every poll on file.
    rules: List[Tuple[Diagnosis, Callable[[], bool], Callable[[], str]]] = [
        (
            Diagnosis.NEW_PATIENT,
            lambda: polls < MIN_POLLS,
            lambda: f"only {_count(polls, 'poll')} on file",
        ),
        (
            Diagnosis.AVOIDANT,
            lambda: row.didnt_bother / polls >= AVOIDANT_SHARE,
            lambda: f"ignored {row.didnt_bother} of {polls} polls",
        ),
        (
            Diagnosis.FENCE_SITTING,
            lambda: row.maybe / answers >= FENCE_SITTING_SHARE,
            lambda: f"Maybe Baby {_count(row.maybe, 'time')} in {_count(answers, 'answer')}",
        ),
        (
            Diagnosis.COUCH,
            lambda: row.no_op / answers >= COUCH_SHARE,
            lambda: f"No-op {_count(row.no_op, 'time')} in {_count(answers, 'answer')}",
        ),
        (
            Diagnosis.SLOT_HOARDING,
            lambda: row.played >= HOARDING_MIN_PLAYED and row.slots_avg >= HOARDING_SLOTS_AVG,
            lambda: f"averages {row.slots_avg:.1f} slots a night",
        ),
        (
            Diagnosis.LOBBY_DEPENDENCY,
            lambda: row.play_pct >= LOBBY_DEPENDENCY_SHARE,
            lambda: f"played {row.played} of {polls} polls, streak {row.played_streak}",
        ),
    ]
    for diagnosis, matches, findings in rules:
        if matches():
            return diagnosis, findings()
    return Diagnosis.UNREMARKABLE, f"answered {_pct(row.response_pct)}, played {_pct(row.play_pct)}"


def find_patient(
    rows: Iterable[UserStatRow], user_id: Optional[int] = None, username: Optional[str] = None
) -> Optional[UserStatRow]:
    """The row for user_id, or for username (without the @, any case) when given instead."""
    for row in rows:
        if username is not None:
            if row.user.username and row.user.username.lower() == username.lower():
                return row
        elif row.user.id == user_id:
            return row
    return None


def render_no_file(who: str) -> str:
    """Reply for someone who has never answered a poll in the chat."""
    return f"No file on {who} - never answered a poll here. Vote first, then we'll talk."


def render_session(name: str, row: UserStatRow) -> str:
    """The session note for one patient: diagnosis, findings and a treatment line."""
    diagnosis, findings = diagnose(row)
    _logger.debug(
        "Diagnosed user_id=%s with %s: responses=%s didnt_bother=%s maybe=%s no_op=%s played=%s slots_avg=%.2f",
        row.user.id,
        diagnosis.name,
        row.responses,
        row.didnt_bother,
        row.maybe,
        row.no_op,
        row.played,
        row.slots_avg,
    )
    return "\n".join(
        [
            f"The doctor will see you now, {name}.",
            f"Diagnosis: {diagnosis.value}",
            f"Findings: {findings}",
            f"Treatment: {deal(diagnosis, TREATMENTS[diagnosis])}",
        ]
    )


def render_shrink_message(chat: Chat, user: Optional[User] = None, username: Optional[str] = None) -> str:
    """The /shrink reply for user, or for username (without the @) when given instead."""
    if username is None and user is not None and user.is_bot:
        return BOT_PATIENT_TEXT

    rows = compute_statistics(chat).user_rows
    if username is not None:
        row = find_patient(rows, username=username)
        if row is None:
            _logger.info("No file on @%s in chat_id=%s", username, chat.chat_id)
            return render_no_file(f"@{username}")
        return render_session(row.user.first_name, row)

    if user is None:
        raise ValueError("render_shrink_message needs a user or a username")
    row = find_patient(rows, user_id=user.id)
    if row is None:
        _logger.info("No file on user_id=%s in chat_id=%s", user.id, chat.chat_id)
        return render_no_file(user.first_name)
    return render_session(user.first_name, row)
