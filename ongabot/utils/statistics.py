"""Utilities for computing and formatting chat-wide participation statistics."""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.helpers import escape_markdown

from chat import Chat
from event import Event

_logger = logging.getLogger(__name__)

# Option texts for the two non-slot poll options, see eventcreator._create_poll_options.
NO_OP_TEXT = "No-op"
MAYBE_TEXT = "Maybe Baby </3"

CALLBACK_DATA_PREFIX = "stats_sort"
NAME_WIDTH = 12
MAX_TABLE_ROWS = 15


@dataclass
class UserStatRow:
    """One user's row in the all-time statistics table."""

    user: User
    responses: int = 0
    played: int = 0
    response_pct: float = 0.0
    play_pct: float = 0.0
    streak: int = 0
    slots_total: int = 0
    slots_avg: float = 0.0
    no_op: int = 0
    maybe: int = 0
    didnt_bother: int = 0


@dataclass
class SlotStat:
    """One time-slot's popularity across a chat's event history."""

    text: str
    total_picks: int
    event_pct: float  # fraction of answered_events in which this slot got >=1 pick


@dataclass
class StatisticsResult:
    """Computed chat-wide statistics, ready for formatting into a message."""

    event_count: int = 0
    answered_events: int = 0
    avg_participants: Optional[float] = None
    slot_stats: List[SlotStat] = field(default_factory=list)
    user_rows: List[UserStatRow] = field(default_factory=list)


@dataclass
class _Accumulator:
    """Mutable per-user/per-slot tallies built while iterating events in event_date order."""

    total_responses: Dict[int, int] = field(default_factory=dict)
    user_played_counts: Dict[int, int] = field(default_factory=dict)
    slot_text_counts: Dict[str, int] = field(default_factory=dict)
    slot_event_counts: Dict[str, int] = field(default_factory=dict)
    user_slot_totals: Dict[int, int] = field(default_factory=dict)
    no_op_counts: Dict[int, int] = field(default_factory=dict)
    maybe_counts: Dict[int, int] = field(default_factory=dict)
    user_by_id: Dict[int, User] = field(default_factory=dict)
    first_seen_index: Dict[int, int] = field(default_factory=dict)


def _tally_event(event: Event, index: int, acc: _Accumulator) -> int:
    """Tally one event's poll answers into acc; returns respondent count.

    index is this event's position in the ascending-by-date events list, used to record
    each user's first-appearance index (including a retracted-vote-only appearance).
    """
    respondents = 0
    slots_seen_this_event = set()
    for user, answer in event.poll_answers.items():
        acc.user_by_id[user.id] = user
        acc.first_seen_index.setdefault(user.id, index)
        if not answer.option_ids:
            continue
        respondents += 1
        acc.total_responses[user.id] = acc.total_responses.get(user.id, 0) + 1
        played_this_event = False
        for option_id in answer.option_ids:
            option_text = event.poll.options[option_id].text
            if option_id < event.num_slots:
                acc.slot_text_counts[option_text] = acc.slot_text_counts.get(option_text, 0) + 1
                acc.user_slot_totals[user.id] = acc.user_slot_totals.get(user.id, 0) + 1
                slots_seen_this_event.add(option_text)
                played_this_event = True
            elif option_text == NO_OP_TEXT:
                acc.no_op_counts[user.id] = acc.no_op_counts.get(user.id, 0) + 1
            elif option_text == MAYBE_TEXT:
                acc.maybe_counts[user.id] = acc.maybe_counts.get(user.id, 0) + 1
        if played_this_event:
            acc.user_played_counts[user.id] = acc.user_played_counts.get(user.id, 0) + 1
    for text in slots_seen_this_event:
        acc.slot_event_counts[text] = acc.slot_event_counts.get(text, 0) + 1
    return respondents


def _build_slot_stats(acc: _Accumulator, answered_events: int) -> List[SlotStat]:
    """Build one SlotStat per slot ever picked, sorted by text (zero-padded HH.MM sorts chronologically)."""
    stats = [
        SlotStat(
            text=text,
            total_picks=count,
            event_pct=(acc.slot_event_counts.get(text, 0) / answered_events) if answered_events > 0 else 0.0,
        )
        for text, count in acc.slot_text_counts.items()
    ]
    return sorted(stats, key=lambda s: s.text)


def _build_user_rows(acc: _Accumulator, num_events: int, streaks: Dict[int, int]) -> List[UserStatRow]:
    """Build one UserStatRow per user ever seen, scoping eligibility to events since first appearance."""
    rows = []
    for user_id, user in acc.user_by_id.items():
        responses = acc.total_responses.get(user_id, 0)
        played = acc.user_played_counts.get(user_id, 0)
        eligible = num_events - acc.first_seen_index[user_id]
        slots_total = acc.user_slot_totals.get(user_id, 0)
        rows.append(
            UserStatRow(
                user=user,
                responses=responses,
                played=played,
                response_pct=(responses / eligible) if eligible > 0 else 0.0,
                play_pct=(played / eligible) if eligible > 0 else 0.0,
                streak=streaks.get(user_id, 0),
                slots_total=slots_total,
                slots_avg=(slots_total / responses) if responses > 0 else 0.0,
                no_op=acc.no_op_counts.get(user_id, 0),
                maybe=acc.maybe_counts.get(user_id, 0),
                didnt_bother=eligible - responses,
            )
        )
    return rows


def compute_statistics(chat: Chat) -> StatisticsResult:
    """Compute all-time, chat-wide participation statistics from a chat's event history.

    Cancelled events are excluded entirely (a user whose only appearance was in a
    cancelled event gets no row). Retracted votes (empty option_ids) count toward a
    user's first-appearance/eligibility but not toward their response count. Streaks are
    read from the latest event's already-maintained user_streaks. avg_participants
    averages respondent counts over answered events only, not diluted by zero-response
    events.
    """
    events = sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date)
    if not events:
        return StatisticsResult()

    acc = _Accumulator()
    respondent_counts = [_tally_event(event, index, acc) for index, event in enumerate(events)]

    latest_event = events[-1]
    answered_events = sum(1 for count in respondent_counts if count > 0)
    avg_participants = (sum(respondent_counts) / answered_events) if answered_events > 0 else None
    slot_stats = _build_slot_stats(acc, answered_events)
    user_rows = _build_user_rows(acc, len(events), dict(latest_event.user_streaks))

    _logger.debug(
        "Computed statistics for chat_id=%s: %s events, %s known users",
        chat.chat_id,
        len(events),
        len(user_rows),
    )

    return StatisticsResult(
        event_count=len(events),
        answered_events=answered_events,
        avg_participants=avg_participants,
        slot_stats=slot_stats,
        user_rows=user_rows,
    )


@dataclass(frozen=True)
class _Column:
    """One sortable column: drives table layout, sort order, and the sort-button keyboard."""

    key: str
    header: str
    width: int
    button_label: str
    value: Callable[[UserStatRow], float]
    render: Callable[[UserStatRow], str]


SORT_COLUMNS: List[_Column] = [
    _Column("responses", "Resp", 4, "Responses", lambda r: r.responses, lambda r: str(r.responses)),
    _Column(
        "resp_rate", "Resp%", 5, "Response Rate", lambda r: r.response_pct, lambda r: f"{r.response_pct * 100:.0f}%"
    ),
    _Column("streak", "Strk", 4, "Streak", lambda r: r.streak, lambda r: str(r.streak)),
    _Column("played", "Play", 4, "Played", lambda r: r.played, lambda r: str(r.played)),
    _Column("play_rate", "Play%", 5, "Played Rate", lambda r: r.play_pct, lambda r: f"{r.play_pct * 100:.0f}%"),
    _Column("slots", "Slot", 4, "Total Slots", lambda r: r.slots_total, lambda r: str(r.slots_total)),
    _Column("avg", " Avg", 4, "Avg Slots", lambda r: r.slots_avg, lambda r: f"{r.slots_avg:.1f}"),
    _Column("maybe", " May", 4, "Maybe", lambda r: r.maybe, lambda r: str(r.maybe)),
    _Column("noop", "NoOp", 4, "No-op", lambda r: r.no_op, lambda r: str(r.no_op)),
    _Column("bother", " DNB", 4, "Didn't Bother Answer", lambda r: r.didnt_bother, lambda r: str(r.didnt_bother)),
]
_COLUMNS_BY_KEY: Dict[str, _Column] = {c.key: c for c in SORT_COLUMNS}
DEFAULT_SORT_KEY = "responses"


def _format_name_cell(name: str) -> str:
    """Truncate/pad a display name to NAME_WIDTH and escape it for a MarkdownV2 code entity."""
    clean = name.replace("\n", " ").replace("\r", " ")
    cell = clean[: NAME_WIDTH - 1] + "." if len(clean) > NAME_WIDTH else clean.ljust(NAME_WIDTH)
    return escape_markdown(cell, version=2, entity_type="code")


def _format_table(rows: List[UserStatRow], sort_by: str) -> str:
    column = _COLUMNS_BY_KEY.get(sort_by, _COLUMNS_BY_KEY[DEFAULT_SORT_KEY])
    ranked = sorted(rows, key=column.value, reverse=True)[:MAX_TABLE_ROWS]

    header = "Name".ljust(NAME_WIDTH) + " " + " ".join(c.header for c in SORT_COLUMNS)
    lines = [header]
    for row in ranked:
        cells = " ".join(c.render(row).rjust(c.width) for c in SORT_COLUMNS)
        lines.append(f"{_format_name_cell(row.user.full_name)} {cells}")

    return "```\n" + "\n".join(lines) + "\n```"


AVG_PARTICIPANTS_LABEL = "Average number of Bangers per event"
SLOT_ROW_PREFIX = "Slot picked - "


def _chat_stat_rows(result: StatisticsResult) -> List[Tuple[str, str, str]]:
    """Build (what, #, %) rows for the merged chat table: 3 summary rows, then one per slot."""
    answered_pct = f"{result.answered_events / result.event_count * 100:.0f}%" if result.event_count > 0 else "-"
    avg_text = f"{result.avg_participants:.1f}" if result.avg_participants is not None else "-"
    known_users = len(result.user_rows)
    avg_pct = (
        f"{result.avg_participants / known_users * 100:.0f}%"
        if result.avg_participants is not None and known_users > 0
        else "-"
    )
    rows = [
        ("Total Events", str(result.event_count), "100%"),
        ("Answered Events", str(result.answered_events), answered_pct),
        (AVG_PARTICIPANTS_LABEL, avg_text, avg_pct),
    ]
    for slot in result.slot_stats:
        rows.append((f"{SLOT_ROW_PREFIX}{slot.text}", str(slot.total_picks), f"{slot.event_pct * 100:.0f}%"))
    return rows


def _format_chat_table(result: StatisticsResult) -> str:
    """Format the merged Chat Statistics table: three columns (what, #, %), no header row."""
    rows = _chat_stat_rows(result)
    what_width = max(len(what) for what, _, _ in rows)
    value_width = max(len(value) for _, value, _ in rows)
    pct_width = max(len(pct) for _, _, pct in rows)
    lines = [f"{what.ljust(what_width)} {value.rjust(value_width)} {pct.rjust(pct_width)}" for what, value, pct in rows]
    return "```\n" + "\n".join(lines) + "\n```"


def format_statistics(result: StatisticsResult, sort_by: str = DEFAULT_SORT_KEY) -> str:
    """Format a StatisticsResult into a MarkdownV2 message for /statistics."""
    if result.event_count == 0:
        return "No event history yet for this chat\\!"

    sections = ["*__Chat Statistics__*", _format_chat_table(result)]

    sections.append("*__User Statistics__*")
    if result.user_rows:
        sections.append(_format_table(result.user_rows, sort_by))
        sections.append("_Tap a button to sort User Statistics by that column_")
    else:
        sections.append("No participation data yet\\.")

    return "\n\n".join(sections)


def build_sort_keyboard() -> InlineKeyboardMarkup:
    """Build the inline keyboard of sort buttons for the statistics table, 2 per row."""
    buttons = [
        InlineKeyboardButton(c.button_label, callback_data=f"{CALLBACK_DATA_PREFIX}:{c.key}") for c in SORT_COLUMNS
    ]
    rows = []
    for start in range(0, len(buttons), 2):
        end = start + 2
        rows.append(buttons[start:end])
    return InlineKeyboardMarkup(rows)


def render_statistics_message(chat: Chat, sort_by: str = DEFAULT_SORT_KEY) -> Tuple[str, InlineKeyboardMarkup]:
    """Compute statistics fresh and render the (text, keyboard) pair for a /statistics reply or edit."""
    result = compute_statistics(chat)
    return format_statistics(result, sort_by=sort_by), build_sort_keyboard()
