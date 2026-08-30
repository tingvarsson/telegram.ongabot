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
    response_pct: float = 0.0
    streak: int = 0
    slots_total: int = 0
    slots_avg: float = 0.0
    no_op: int = 0
    maybe: int = 0
    didnt_bother: int = 0


@dataclass
class StatisticsResult:
    """Computed chat-wide statistics, ready for formatting into a message."""

    event_count: int = 0
    participation_rate: Optional[float] = None
    top_slot: Optional[Tuple[str, int]] = None
    user_rows: List[UserStatRow] = field(default_factory=list)


@dataclass
class _Accumulator:
    """Mutable per-user/per-slot tallies built while iterating events in event_date order."""

    total_responses: Dict[int, int] = field(default_factory=dict)
    slot_text_counts: Dict[str, int] = field(default_factory=dict)
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
    for user, answer in event.poll_answers.items():
        acc.user_by_id[user.id] = user
        acc.first_seen_index.setdefault(user.id, index)
        if not answer.option_ids:
            continue
        respondents += 1
        acc.total_responses[user.id] = acc.total_responses.get(user.id, 0) + 1
        for option_id in answer.option_ids:
            option_text = event.poll.options[option_id].text
            if option_id < event.num_slots:
                acc.slot_text_counts[option_text] = acc.slot_text_counts.get(option_text, 0) + 1
                acc.user_slot_totals[user.id] = acc.user_slot_totals.get(user.id, 0) + 1
            elif option_text == NO_OP_TEXT:
                acc.no_op_counts[user.id] = acc.no_op_counts.get(user.id, 0) + 1
            elif option_text == MAYBE_TEXT:
                acc.maybe_counts[user.id] = acc.maybe_counts.get(user.id, 0) + 1
    return respondents


def _compute_participation_rate(respondent_counts: List[int], chat_member_count: int) -> Optional[float]:
    """Average respondents per event, divided by today's member count (excluding the bot itself)."""
    effective_member_count = chat_member_count - 1
    if effective_member_count <= 0:
        return None
    return (sum(respondent_counts) / len(respondent_counts)) / effective_member_count


def _build_user_rows(acc: _Accumulator, num_events: int, streaks: Dict[int, int]) -> List[UserStatRow]:
    """Build one UserStatRow per user ever seen, scoping eligibility to events since first appearance."""
    rows = []
    for user_id, user in acc.user_by_id.items():
        responses = acc.total_responses.get(user_id, 0)
        eligible = num_events - acc.first_seen_index[user_id]
        slots_total = acc.user_slot_totals.get(user_id, 0)
        rows.append(
            UserStatRow(
                user=user,
                responses=responses,
                response_pct=(responses / eligible) if eligible > 0 else 0.0,
                streak=streaks.get(user_id, 0),
                slots_total=slots_total,
                slots_avg=(slots_total / responses) if responses > 0 else 0.0,
                no_op=acc.no_op_counts.get(user_id, 0),
                maybe=acc.maybe_counts.get(user_id, 0),
                didnt_bother=eligible - responses,
            )
        )
    return rows


def compute_statistics(chat: Chat, chat_member_count: int) -> StatisticsResult:
    """Compute all-time, chat-wide participation statistics from a chat's event history.

    Cancelled events are excluded entirely (a user whose only appearance was in a
    cancelled event gets no row). Retracted votes (empty option_ids) count toward a
    user's first-appearance/eligibility but not toward their response count. Streaks are
    read from the latest event's already-maintained user_streaks. Participation rate
    approximates historical chat membership with today's member count, since no
    historical snapshot exists.
    """
    events = sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date)
    if not events:
        return StatisticsResult()

    acc = _Accumulator()
    respondent_counts = [_tally_event(event, index, acc) for index, event in enumerate(events)]

    latest_event = events[-1]
    top_slot = max(acc.slot_text_counts.items(), key=lambda kv: kv[1]) if acc.slot_text_counts else None
    user_rows = _build_user_rows(acc, len(events), dict(latest_event.user_streaks))

    _logger.debug(
        "Computed statistics for chat_id=%s: %s events, %s known users",
        chat.chat_id,
        len(events),
        len(user_rows),
    )

    return StatisticsResult(
        event_count=len(events),
        participation_rate=_compute_participation_rate(respondent_counts, chat_member_count),
        top_slot=top_slot,
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
    _Column("rate", "Rate%", 5, "Rate %", lambda r: r.response_pct, lambda r: f"{r.response_pct * 100:.0f}%"),
    _Column("streak", "Strk", 4, "Streak", lambda r: r.streak, lambda r: str(r.streak)),
    _Column("slots", "Slot", 4, "Slots", lambda r: r.slots_total, lambda r: str(r.slots_total)),
    _Column("avg", " Avg", 4, "Avg Slots", lambda r: r.slots_avg, lambda r: f"{r.slots_avg:.1f}"),
    _Column("noop", "NoOp", 4, "No-op", lambda r: r.no_op, lambda r: str(r.no_op)),
    _Column("maybe", " May", 4, "Maybe", lambda r: r.maybe, lambda r: str(r.maybe)),
    _Column("bother", " DNB", 4, "Didn't Bother", lambda r: r.didnt_bother, lambda r: str(r.didnt_bother)),
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


def format_statistics(result: StatisticsResult, sort_by: str = DEFAULT_SORT_KEY) -> str:
    """Format a StatisticsResult into a MarkdownV2 message for /statistics."""
    if result.event_count == 0:
        return "No event history yet for this chat\\!"

    sections = [f"*__Chat Statistics__* \\(across {result.event_count} tracked events\\)"]

    if result.participation_rate is not None:
        sections.append(f"Average participation: *{result.participation_rate * 100:.0f}%*")

    if result.top_slot is not None:
        slot_text, count = result.top_slot
        sections.append(f"*Most Popular Slot:* {escape_markdown(slot_text, version=2)} \\({count} picks\\)")

    if result.user_rows:
        sections.append(_format_table(result.user_rows, sort_by))
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


def render_statistics_message(
    chat: Chat, chat_member_count: int, sort_by: str = DEFAULT_SORT_KEY
) -> Tuple[str, InlineKeyboardMarkup]:
    """Compute statistics fresh and render the (text, keyboard) pair for a /statistics reply or edit."""
    result = compute_statistics(chat, chat_member_count)
    return format_statistics(result, sort_by=sort_by), build_sort_keyboard()
