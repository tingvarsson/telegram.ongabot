"""Utilities for computing and formatting Banger Points, the chat leaderboard.

Not every vote is worth the same. Piling onto a slot that already had eight takers is not
the contribution that being the fifth person who made the game happen is. Banger Points
weight each vote by how much it actually mattered:

* marginal impact - a bonus for picking the winning slot, worth most when that slot only
  just reached quorum, plus an extra "rescue" when it landed on quorum exactly;
* diminishing returns - the flex bonus grows with the square root of the slots picked, so
  picking all five is not worth five times picking one;
* scarcity - a rarity bonus for propping up the slots the chat usually ignores.

Two standings come out: Form (the rolling last FORM_EVENT_COUNT events, the live race) and
All-time. Everything is recomputed from the event history on every render, exactly as
utils.statistics does; nothing is persisted.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from telegram import User
from telegram.helpers import escape_markdown

from chat import Chat
from event import Event
from utils.statistics import NO_OP_TEXT, display_names, format_name_cell, group_slot_texts

_logger = logging.getLogger(__name__)

# Players needed on one slot for the event to actually go ahead. Clutch and rescue hinge on
# this: it is the line that makes a vote decisive.
QUORUM = 5
# The rolling window behind the Form column.
FORM_EVENT_COUNT = 20

MAX_LEADERBOARD_ROWS = 10
RANK_WIDTH = 2
TOTAL_WIDTH = 5
DELTA_WIDTH = 4
MOVEMENT_WIDTH = 4

POINTS_ANSWERED = 1.0  # answered the poll at all, No-op and Maybe Baby </3 included
POINTS_NO_OP = 0.5  # extra for an honest No-op: telling the group beats ghosting
POINTS_BOOTED = 3.0  # picked at least one real time slot
POINTS_FLEX = 2.0  # coefficient of the 2*(sqrt(k)-1) diminishing-returns flex curve
POINTS_RARITY = 1.5  # full value for a pick on the chat's least popular slot
POINTS_CLUTCH = 6.0  # scaled by QUORUM/V, so a bare-quorum winning slot pays full value
POINTS_RESCUE = 3.0  # extra when the winning slot landed on quorum exactly
POINTS_TRAILBLAZER = 1.0  # first to answer the poll


@dataclass(frozen=True)
class EventOutcome:
    """What one event's poll actually decided: which slot won, by how much, and whether it goes ahead."""

    event_date: date
    slot_texts: Tuple[str, ...]
    slot_counts: Tuple[int, ...]
    winning_slot: Optional[int]  # index into slot_texts; None when nobody picked a slot
    votes: int  # picks on the winning slot, the "V" the clutch bonus scales by
    went_ahead: bool

    @property
    def winning_text(self) -> Optional[str]:
        """Option text of the winning slot, or None when nobody picked a slot."""
        return None if self.winning_slot is None else self.slot_texts[self.winning_slot]


@dataclass
class EventScore:
    """One user's Banger Points for one event, kept broken down by component.

    The breakdown drives the recap's reason tags and makes each component testable on its own.
    """

    slots: int = 0  # how many real time slots this user picked
    answered: float = 0.0
    no_op: float = 0.0
    booted: float = 0.0
    flex: float = 0.0
    rarity: float = 0.0
    clutch: float = 0.0
    rescue: float = 0.0
    trailblazer: float = 0.0

    @property
    def total(self) -> float:
        """This user's Banger Points for the event."""
        return (
            self.answered
            + self.no_op
            + self.booted
            + self.flex
            + self.rarity
            + self.clutch
            + self.rescue
            + self.trailblazer
        )

    @property
    def tags(self) -> List[str]:
        """Short reasons worth calling out in the recap, so people learn what pays."""
        tags = []
        if self.rescue > 0:
            tags.append("rescue")
        elif self.clutch > 0:
            tags.append("clutch")
        if self.rarity >= POINTS_RARITY:
            tags.append("rare slots")
        if self.trailblazer > 0:
            tags.append("first in")
        return tags


@dataclass
class PointsRow:
    """One user's standing: Banger Points over the Form window and over all time."""

    user: User
    form: float = 0.0
    all_time: float = 0.0


@dataclass
class PointsResult:
    """Computed Banger Points for a chat, ready for formatting into a message."""

    rows: List[PointsRow] = field(default_factory=list)
    outcomes: List[EventOutcome] = field(default_factory=list)
    scores_by_date: Dict[date, Dict[int, EventScore]] = field(default_factory=dict)
    slot_rarity: Dict[str, float] = field(default_factory=dict)  # group label -> points per pick
    form_event_count: int = 0


def _slot_texts(event: Event) -> Tuple[str, ...]:
    """The event's real time-slot option texts, by index. Options past num_slots are No-op/Maybe."""
    return tuple(option.text for option in event.poll.options[: event.num_slots])


def compute_event_outcome(event: Event) -> EventOutcome:
    """Count picks per slot and decide the winning slot, ties going to the earliest slot."""
    texts = _slot_texts(event)
    counts = [0] * len(texts)
    for answer in event.poll_answers.values():
        for option_id in answer.option_ids:
            if option_id < len(counts):
                counts[option_id] += 1

    if not counts or max(counts) == 0:
        return EventOutcome(event.event_date, texts, tuple(counts), None, 0, False)

    # list.index returns the first maximum, which is the earliest slot: the tie-break rule.
    winning_slot = counts.index(max(counts))
    votes = counts[winning_slot]
    return EventOutcome(event.event_date, texts, tuple(counts), winning_slot, votes, votes >= QUORUM)


def _slot_rarity(events: Sequence[Event]) -> Tuple[Dict[str, str], Dict[str, float]]:
    """Map each slot text to its group label, and each label to its rarity points per pick.

    Popularity is min-max normalised across the chat's slot groups, so the least popular slot
    always earns the full POINTS_RARITY and the most popular earns nothing. A plain
    picks/max-picks ratio compresses badly in a chat where people vote for nearly every slot:
    on real data it left the least-loved slot earning a third of what it should. When every
    slot is equally popular none of them is rare, so they all earn nothing.

    Grouping is the same near-identical-time merge /statistics uses, because the poll start
    time drifts between events - 20.30 and 20.40 are the same slot. Keying rarity on the raw
    text would score a rare *spelling* of a popular slot as rare.
    """
    picks: Dict[str, int] = {}
    for event in events:
        texts = _slot_texts(event)
        for answer in event.poll_answers.values():
            for option_id in answer.option_ids:
                if option_id < len(texts):
                    picks[texts[option_id]] = picks.get(texts[option_id], 0) + 1

    label_of: Dict[str, str] = {}
    group_picks: Dict[str, int] = {}
    for group in group_slot_texts(picks):
        group_picks[group.label] = sum(picks[text] for text in group.texts)
        for text in group.texts:
            label_of[text] = group.label

    if not group_picks:
        return label_of, {}
    low, high = min(group_picks.values()), max(group_picks.values())
    rarity = {
        label: (POINTS_RARITY * (1 - (count - low) / (high - low)) if high > low else 0.0)
        for label, count in group_picks.items()
    }
    return label_of, rarity


def score_event(
    event: Event,
    outcome: EventOutcome,
    label_of: Dict[str, str],
    rarity: Dict[str, float],
) -> Dict[int, EventScore]:
    """Score every user who answered this event's poll. Retracted votes and ghosts score nothing."""
    texts = outcome.slot_texts
    scores: Dict[int, EventScore] = {}
    for user, answer in event.poll_answers.items():
        if not answer.option_ids:
            continue  # retracted vote: present in the dict, but not a response
        score = EventScore(answered=POINTS_ANSWERED)
        picked_slots = [option_id for option_id in answer.option_ids if option_id < len(texts)]
        other_texts = {event.poll.options[option_id].text for option_id in answer.option_ids if option_id >= len(texts)}
        if NO_OP_TEXT in other_texts:
            score.no_op = POINTS_NO_OP
        if picked_slots:
            score.slots = len(picked_slots)
            score.booted = POINTS_BOOTED
            score.flex = POINTS_FLEX * (math.sqrt(len(picked_slots)) - 1)
            score.rarity = sum(rarity.get(label_of.get(texts[i], texts[i]), 0.0) for i in picked_slots)
            if outcome.went_ahead and outcome.winning_slot in picked_slots:
                score.clutch = POINTS_CLUTCH * QUORUM / outcome.votes
                if outcome.votes == QUORUM:
                    score.rescue = POINTS_RESCUE
        if event.first_answer is not None and event.first_answer.id == user.id:
            score.trailblazer = POINTS_TRAILBLAZER
        scores[user.id] = score
    return scores


@dataclass
class _Accumulator:
    """Mutable tallies built while iterating a chat's events in event_date order."""

    users_by_id: Dict[int, User] = field(default_factory=dict)
    form_totals: Dict[int, float] = field(default_factory=dict)
    all_totals: Dict[int, float] = field(default_factory=dict)
    outcomes: List[EventOutcome] = field(default_factory=list)
    scores_by_date: Dict[date, Dict[int, EventScore]] = field(default_factory=dict)

    def add(
        self,
        event: Event,
        outcome: EventOutcome,
        scores: Dict[int, EventScore],
        in_form_window: bool,
    ) -> None:
        """Fold one scored event into the running totals."""
        self.outcomes.append(outcome)
        self.scores_by_date[event.event_date] = scores
        # Every user who appears in the poll gets a row, even if a retracted vote scored nothing.
        for user in event.poll_answers:
            self.users_by_id[user.id] = user
        for user_id, score in scores.items():
            self.all_totals[user_id] = self.all_totals.get(user_id, 0.0) + score.total
            if in_form_window:
                self.form_totals[user_id] = self.form_totals.get(user_id, 0.0) + score.total

    def build_rows(self) -> List[PointsRow]:
        """One standings row per user ever seen."""
        return [
            PointsRow(
                user=user,
                form=self.form_totals.get(user_id, 0.0),
                all_time=self.all_totals.get(user_id, 0.0),
            )
            for user_id, user in self.users_by_id.items()
        ]


def _events_for(chat: Chat) -> List[Event]:
    """A chat's non-cancelled events, oldest first - the shared input to every standings view."""
    return sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date)


def _compute_from_events(events: List[Event], chat_id: Optional[int] = None) -> PointsResult:
    """Compute standings from an explicit, already-filtered/sorted events list.

    Factored out of compute_points so the event recap can call it a second time on a
    truncated events list - "everyone's standing as of just before this event" - to diff
    against the full-history result and show what moved. chat_id is for logging only; the
    "as of before" call has no chat_id of its own that means anything scoped to a sub-slice.
    """
    if not events:
        return PointsResult()

    label_of, rarity = _slot_rarity(events)
    form_start = max(0, len(events) - FORM_EVENT_COUNT)
    acc = _Accumulator()

    for index, event in enumerate(events):
        outcome = compute_event_outcome(event)
        acc.add(event, outcome, score_event(event, outcome, label_of, rarity), index >= form_start)
        _logger.debug(
            "Event %s in chat_id=%s: winning slot %s with V=%s, went_ahead=%s, counts=%s",
            event.event_date,
            chat_id,
            outcome.winning_text,
            outcome.votes,
            outcome.went_ahead,
            dict(zip(outcome.slot_texts, outcome.slot_counts)),
        )

    rows = acc.build_rows()

    _logger.debug(
        "Computed Banger Points for chat_id=%s: %s events (%s in form window), %s users, rarity=%s",
        chat_id,
        len(events),
        len(events) - form_start,
        len(rows),
        rarity,
    )

    return PointsResult(
        rows=rows,
        outcomes=acc.outcomes,
        scores_by_date=acc.scores_by_date,
        slot_rarity=rarity,
        form_event_count=len(events) - form_start,
    )


def compute_points(chat: Chat) -> PointsResult:
    """Compute Banger Points standings from a chat's event history.

    Cancelled events are excluded entirely: from scoring, from the Form window, and from the
    rarity denominator. Form sums the most recent FORM_EVENT_COUNT events; All-time sums
    every event.
    """
    return _compute_from_events(_events_for(chat), chat_id=chat.chat_id)


def _previous_result(chat: Chat, event: Event) -> PointsResult:
    """Standings as of just before event - the "before" side of the recap's movement diff."""
    events = [e for e in _events_for(chat) if e.event_date < event.event_date]
    return _compute_from_events(events, chat_id=chat.chat_id)


# MarkdownV2 requires "-" escaped even inside a bold entity - it is literal text there, not
# code/pre content, so the ordinary escaping rule still applies.
_FORM_HEADING = "*Form*"
_ALL_TIME_HEADING = f"*{escape_markdown('All-time', version=2)}*"


def _form_key(row: PointsRow) -> Tuple[float, float]:
    """Form first, All-time as the tie-break so a tie on Form is not ordered arbitrarily."""
    return (row.form, row.all_time)


def _all_time_key(row: PointsRow) -> Tuple[float, float]:
    """All-time's mirror of _form_key - its own ranking, not a fallback view of Form's."""
    return (row.all_time, row.form)


def _ranks(rows: List[PointsRow], key: Callable[[PointsRow], Tuple[float, float]]) -> Dict[int, int]:
    """Every row's 1-indexed rank under key, unlimited - the full board a display cap trims from."""
    ordered = sorted(rows, key=key, reverse=True)
    return {row.user.id: index + 1 for index, row in enumerate(ordered)}


def _format_delta(value: Optional[float]) -> str:
    """This event's points gained, or "-" for a row that didn't score it."""
    text = "-" if value is None else f"+{round(value):d}"
    return text.rjust(DELTA_WIDTH)


def _format_movement(current_rank: int, previous_rank: Optional[int]) -> str:
    """Rank movement since previous_rank: ▲ up, ▼ down, – unchanged, NEW with no prior rank."""
    if previous_rank is None:
        return "NEW".rjust(MOVEMENT_WIDTH)
    delta = previous_rank - current_rank  # a smaller rank number is better, so this is signed "up"
    if delta > 0:
        return f"▲{delta}".rjust(MOVEMENT_WIDTH)
    if delta < 0:
        return f"▼{-delta}".rjust(MOVEMENT_WIDTH)
    return "–".rjust(MOVEMENT_WIDTH)


def _board_table(
    rows: List[PointsRow],
    names: Dict[int, str],
    key: Callable[[PointsRow], Tuple[float, float]],
    value_of: Callable[[PointsRow], float],
    limit: int,
    previous_ranks: Optional[Dict[int, int]] = None,
    event_deltas: Optional[Dict[int, float]] = None,
) -> str:
    """One board's fenced table: rank/name/total, plus this-event delta and movement when given
    a previous ranking to diff against - see _previous_result. Without one (a plain /leaderboard
    call has no "before" state), the table is just rank/name/total.
    """
    ranked = sorted(rows, key=key, reverse=True)[:limit]
    lines = []
    for rank, row in enumerate(ranked, start=1):
        total = f"{round(value_of(row)):d}".rjust(TOTAL_WIDTH)
        line = f"{str(rank).rjust(RANK_WIDTH)} {format_name_cell(names[row.user.id])} {total}"
        if previous_ranks is not None:
            delta = event_deltas.get(row.user.id) if event_deltas else None
            movement = _format_movement(rank, previous_ranks.get(row.user.id))
            line += f" {_format_delta(delta)} {movement}"
        lines.append(line)
    return "```\n" + "\n".join(lines) + "\n```"


def format_leaderboard(result: PointsResult) -> str:
    """Format a PointsResult into the MarkdownV2 message body for /leaderboard.

    Form and All-time are shown as two independently-ranked tables rather than one table with
    both totals, so a member's position can differ between them - the same shape the post-event
    recap uses, see format_event_recap.
    """
    if not result.outcomes:
        return "No event history yet for this chat\\!"
    if not result.rows:
        return "No participation data yet\\."

    names = display_names(row.user for row in result.rows)
    form_table = _board_table(result.rows, names, _form_key, lambda r: r.form, MAX_LEADERBOARD_ROWS)
    all_time_table = _board_table(result.rows, names, _all_time_key, lambda r: r.all_time, MAX_LEADERBOARD_ROWS)
    footer = escape_markdown(f"Form covers the last {result.form_event_count} events.", version=2)

    return "\n\n".join(
        [
            "*__Banger Points__*",
            f"{_FORM_HEADING}\n{form_table}",
            f"{_ALL_TIME_HEADING}\n{all_time_table}",
            f"_{footer}_",
        ]
    )


def _recap_headline(outcome: EventOutcome) -> str:
    """One escaped plain-text line saying what the poll decided."""
    if outcome.winning_text is None:
        return escape_markdown("Nobody picked a slot - no points on the table.", version=2)
    if outcome.went_ahead:
        return escape_markdown(f"{outcome.winning_text} took it with {outcome.votes} - quorum met!", version=2)
    return escape_markdown(
        f"{outcome.winning_text} led with {outcome.votes} - {QUORUM} needed, no game.",
        version=2,
    )


def format_event_recap(result: PointsResult, event: Event, previous: Optional[PointsResult] = None) -> str:
    """Format the post-event message: what the poll decided, then a Form and an All-time
    leaderboard snapshot - each row showing this event's points gained and the rank movement
    since previous, the standings as of just before this event (see _previous_result).

    previous defaults to an empty result so a caller probing just the headline/outcome lookup
    (e.g. an unrecognised event) doesn't need to supply one.
    """
    outcome = next((o for o in result.outcomes if o.event_date == event.event_date), None)
    if outcome is None:
        return ""

    previous = previous if previous is not None else PointsResult()
    scores = result.scores_by_date.get(event.event_date, {})
    event_deltas = {user_id: score.total for user_id, score in scores.items()}
    names = display_names(row.user for row in result.rows)

    form_table = _board_table(
        result.rows,
        names,
        _form_key,
        lambda r: r.form,
        MAX_LEADERBOARD_ROWS,
        previous_ranks=_ranks(previous.rows, _form_key),
        event_deltas=event_deltas,
    )
    all_time_table = _board_table(
        result.rows,
        names,
        _all_time_key,
        lambda r: r.all_time,
        MAX_LEADERBOARD_ROWS,
        previous_ranks=_ranks(previous.rows, _all_time_key),
        event_deltas=event_deltas,
    )

    return "\n\n".join(
        [
            "*__Banger Points__*",
            _recap_headline(outcome),
            f"{_FORM_HEADING}\n{form_table}",
            f"{_ALL_TIME_HEADING}\n{all_time_table}",
        ]
    )


def render_leaderboard_message(chat: Chat) -> str:
    """Compute Banger Points fresh and render the /leaderboard reply text."""
    return format_leaderboard(compute_points(chat))


def render_event_recap_message(chat: Chat, event: Event) -> str:
    """Compute Banger Points fresh and render the post-event recap for one event.

    The recap is a snapshot at completion time: polls are never closed, so a late vote can
    still change this event's points afterwards. /leaderboard recomputes live and is the
    source of truth.
    """
    return format_event_recap(compute_points(chat), event, _previous_result(chat, event))
