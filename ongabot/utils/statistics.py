"""Utilities for computing and formatting chat-wide participation statistics."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User
from telegram.helpers import escape_markdown

from chat import Chat
from event import Event

_logger = logging.getLogger(__name__)

# Option texts for the two non-slot poll options, see eventcreator._create_poll_options.
NO_OP_TEXT = "No-op"
MAYBE_TEXT = "Maybe Baby </3"

CALLBACK_DATA_PREFIX = "stats_sort"
NAME_WIDTH = 10
MAX_TABLE_ROWS = 15

# Slot times this close together are reported as one slot (e.g. 20.30 and 20.40), since
# the poll start time drifts between events. The span cap keeps a long run of close times
# from chain-merging into one very wide group.
SLOT_GROUP_MAX_GAP_MINUTES = 15
SLOT_GROUP_MAX_SPAN_MINUTES = 30


@dataclass
class UserStatRow:
    """One user's row in the all-time statistics table."""

    user: User
    responses: int = 0
    played: int = 0
    response_pct: float = 0.0
    play_pct: float = 0.0
    response_streak: int = 0  # consecutive most-recent events answered at all
    played_streak: int = 0  # consecutive most-recent events with an actual slot pick
    slots_total: int = 0
    slots_avg: float = 0.0  # average slots picked per event the user could actually play

    no_op: int = 0
    maybe: int = 0
    didnt_bother: int = 0


@dataclass
class SlotStat:
    """One time-slot's popularity across a chat's event history.

    text is the group label: a single "HH.MM" time, or "HH.MM-HH.MM" when near-identical
    times were merged, see _group_slot_texts.
    """

    text: str
    total_picks: int
    event_pct: float  # fraction of answered_events in which this slot got >=1 pick


@dataclass
class StatisticsResult:
    """Computed chat-wide statistics, ready for formatting into a message."""

    event_count: int = 0
    answered_events: int = 0
    avg_participants: Optional[float] = None
    avg_per_slot: Optional[float] = None
    slot_stats: List[SlotStat] = field(default_factory=list)
    user_rows: List[UserStatRow] = field(default_factory=list)


@dataclass
class _Accumulator:
    """Mutable per-user/per-slot tallies built while iterating events in event_date order."""

    total_responses: Dict[int, int] = field(default_factory=dict)
    user_played_counts: Dict[int, int] = field(default_factory=dict)
    slot_text_counts: Dict[str, int] = field(default_factory=dict)
    per_event_slot_texts: List[Set[str]] = field(default_factory=list)
    slot_instances: int = 0  # slots offered across answered events, for avg picks per slot
    user_slot_totals: Dict[int, int] = field(default_factory=dict)
    no_op_counts: Dict[int, int] = field(default_factory=dict)
    maybe_counts: Dict[int, int] = field(default_factory=dict)
    user_by_id: Dict[int, User] = field(default_factory=dict)
    first_seen_index: Dict[int, int] = field(default_factory=dict)


class _EventTally(NamedTuple):
    """One event's headline counts: users who answered at all, and users who can play."""

    respondents: int
    players: int


def _tally_event(event: Event, index: int, acc: _Accumulator) -> _EventTally:
    """Tally one event's poll answers into acc; returns its respondent and player counts.

    index is this event's position in the ascending-by-date events list, used to record
    each user's first-appearance index (including a retracted-vote-only appearance).
    """
    respondents = 0
    players = 0
    slots_seen_this_event: Set[str] = set()
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
            players += 1
            acc.user_played_counts[user.id] = acc.user_played_counts.get(user.id, 0) + 1
    acc.per_event_slot_texts.append(slots_seen_this_event)
    if respondents > 0:
        acc.slot_instances += event.num_slots
    return _EventTally(respondents=respondents, players=players)


class _SlotGroup(NamedTuple):
    """One or more near-identical slot times reported together as a single slot."""

    label: str
    texts: Tuple[str, ...]


def _slot_minutes(text: str) -> Optional[int]:
    """Parse a slot option text ("HH.MM", see eventcreator._create_poll_options) into minutes since midnight."""
    try:
        parsed = datetime.strptime(text, "%H.%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def _group_slot_texts(texts: Iterable[str]) -> List[_SlotGroup]:
    """Merge near-identical slot times (e.g. 20.30 and 20.40) into groups, in chronological order.

    A new group starts when the gap to the previous time exceeds SLOT_GROUP_MAX_GAP_MINUTES,
    or when the time would stretch the group past SLOT_GROUP_MAX_SPAN_MINUTES. Texts that are
    not HH.MM (hand-made polls) are never merged and are reported last, sorted by text.
    """
    timed: List[Tuple[int, str]] = []
    untimed: List[str] = []
    for text in texts:
        minutes = _slot_minutes(text)
        if minutes is None:
            untimed.append(text)
        else:
            timed.append((minutes, text))

    grouped: List[List[Tuple[int, str]]] = []
    for minutes, text in sorted(timed):
        if (
            grouped
            and minutes - grouped[-1][-1][0] <= SLOT_GROUP_MAX_GAP_MINUTES
            and minutes - grouped[-1][0][0] <= SLOT_GROUP_MAX_SPAN_MINUTES
        ):
            grouped[-1].append((minutes, text))
        else:
            grouped.append([(minutes, text)])

    groups = [
        _SlotGroup(
            label=members[0][1] if len(members) == 1 else f"{members[0][1]}-{members[-1][1]}",
            texts=tuple(text for _, text in members),
        )
        for members in grouped
    ]
    groups += [_SlotGroup(label=text, texts=(text,)) for text in sorted(untimed)]
    return groups


def _build_slot_stats(acc: _Accumulator, answered_events: int) -> List[SlotStat]:
    """Build one SlotStat per group of near-identical slot times ever picked, in chronological order."""
    stats = []
    for group in _group_slot_texts(acc.slot_text_counts):
        if len(group.texts) > 1:
            _logger.debug("Grouped near-identical slot times %s into %s", list(group.texts), group.label)
        members = set(group.texts)
        # An event counts once for the group if any of its member times got >=1 pick there.
        event_count = sum(1 for seen in acc.per_event_slot_texts if seen & members)
        stats.append(
            SlotStat(
                text=group.label,
                total_picks=sum(acc.slot_text_counts[text] for text in group.texts),
                event_pct=(event_count / answered_events) if answered_events > 0 else 0.0,
            )
        )
    return stats


def _build_user_rows(
    acc: _Accumulator,
    num_events: int,
    streaks: Dict[int, int],
    played_streaks: Dict[int, int],
) -> List[UserStatRow]:
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
                response_streak=streaks.get(user_id, 0),
                played_streak=played_streaks.get(user_id, 0),
                slots_total=slots_total,
                slots_avg=(slots_total / played) if played > 0 else 0.0,
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
    user's first-appearance/eligibility but not toward their response count. Both streaks are
    read from the latest event's already-maintained maps: user_streaks counts consecutive
    most-recent events answered at all (No-op and Maybe Baby </3 included), user_played_streaks
    only those with an actual slot pick. A user absent from those maps did not vote in the
    latest event, so their streak is 0 either way. avg_participants counts
    only users who picked at least one slot (i.e. who can actually play, not everyone who
    answered), averaged over answered events only so zero-response events do not dilute
    it. avg_per_slot spreads all slot picks over every slot offered in those events.
    """
    events = sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date)
    if not events:
        return StatisticsResult()

    acc = _Accumulator()
    tallies = [_tally_event(event, index, acc) for index, event in enumerate(events)]

    latest_event = events[-1]
    answered_events = sum(1 for tally in tallies if tally.respondents > 0)
    avg_participants = (sum(t.players for t in tallies) / answered_events) if answered_events > 0 else None
    total_picks = sum(acc.slot_text_counts.values())
    avg_per_slot = (total_picks / acc.slot_instances) if acc.slot_instances > 0 else None
    slot_stats = _build_slot_stats(acc, answered_events)
    user_rows = _build_user_rows(
        acc,
        len(events),
        dict(latest_event.user_streaks),
        dict(latest_event.user_played_streaks),
    )

    _logger.debug(
        "Computed statistics for chat_id=%s: %s events, %s known users, %s slot groups from %s picks over %s slots",
        chat.chat_id,
        len(events),
        len(user_rows),
        len(slot_stats),
        total_picks,
        acc.slot_instances,
    )

    return StatisticsResult(
        event_count=len(events),
        answered_events=answered_events,
        avg_participants=avg_participants,
        avg_per_slot=avg_per_slot,
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


def _format_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


SORT_COLUMNS: List[_Column] = [
    _Column("responses", "Resp", 4, "Responses", lambda r: r.responses, lambda r: str(r.responses)),
    _Column("resp_rate", "Resp%", 5, "Response Rate", lambda r: r.response_pct, lambda r: _format_pct(r.response_pct)),
    _Column("resp_streak", "RStk", 4, "Response Streak", lambda r: r.response_streak, lambda r: str(r.response_streak)),
    _Column("played_streak", "PStk", 4, "Played Streak", lambda r: r.played_streak, lambda r: str(r.played_streak)),
    _Column("played", "Play", 4, "Played", lambda r: r.played, lambda r: str(r.played)),
    _Column("play_rate", "Play%", 5, "Played Rate", lambda r: r.play_pct, lambda r: _format_pct(r.play_pct)),
    _Column("slots", "Slot", 4, "Total Slots", lambda r: r.slots_total, lambda r: str(r.slots_total)),
    _Column("avg", " Avg", 4, "Avg Slots (played)", lambda r: r.slots_avg, lambda r: f"{r.slots_avg:.1f}"),
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


def _display_names(rows: List[UserStatRow]) -> Dict[int, str]:
    """Map user_id to table name: first name only, plus a last initial where first names collide."""
    first_name_counts: Dict[str, int] = {}
    for row in rows:
        first_name_counts[row.user.first_name] = first_name_counts.get(row.user.first_name, 0) + 1

    names: Dict[int, str] = {}
    for row in rows:
        name = row.user.first_name
        if first_name_counts[name] > 1 and row.user.last_name:
            name = f"{name} {row.user.last_name[0]}."
        names[row.user.id] = name
    return names


def _format_table(rows: List[UserStatRow], sort_by: str) -> str:
    column = _COLUMNS_BY_KEY.get(sort_by)
    if column is None:
        _logger.debug("Unknown sort_by=%s for statistics table; falling back to default=%s", sort_by, DEFAULT_SORT_KEY)
        column = _COLUMNS_BY_KEY[DEFAULT_SORT_KEY]
    # Names are disambiguated across all rows, before ranking, so they do not change with sort order.
    names = _display_names(rows)
    ranked = sorted(rows, key=column.value, reverse=True)[:MAX_TABLE_ROWS]

    header = "Name".ljust(NAME_WIDTH) + " " + " ".join(c.header for c in SORT_COLUMNS)
    lines = [header]
    for row in ranked:
        cells = " ".join(c.render(row).rjust(c.width) for c in SORT_COLUMNS)
        lines.append(f"{_format_name_cell(names[row.user.id])} {cells}")

    return "```\n" + "\n".join(lines) + "\n```"


AVG_PARTICIPANTS_LABEL = "Average number of Bangers per event"
AVG_PER_SLOT_LABEL = "Average number of Bangers per slot"
SLOT_ROW_PREFIX = "Slot picked - "


def _chat_stat_rows(result: StatisticsResult) -> List[Tuple[str, str, str]]:
    """Build (what, #, %) rows for the merged chat table: 4 summary rows, then one per slot."""
    answered_pct = _format_pct(result.answered_events / result.event_count) if result.event_count > 0 else "-"
    known_users = len(result.user_rows)

    def avg_cells(value: Optional[float]) -> Tuple[str, str]:
        """Render an average as its (value, share of known chat users) cell pair."""
        if value is None:
            return "-", "-"
        return f"{value:.1f}", (_format_pct(value / known_users) if known_users > 0 else "-")

    avg_event_value, avg_event_pct = avg_cells(result.avg_participants)
    avg_slot_value, avg_slot_pct = avg_cells(result.avg_per_slot)
    rows = [
        ("Total Events", str(result.event_count), _format_pct(1.0)),
        ("Answered Events", str(result.answered_events), answered_pct),
        (AVG_PARTICIPANTS_LABEL, avg_event_value, avg_event_pct),
        (AVG_PER_SLOT_LABEL, avg_slot_value, avg_slot_pct),
    ]
    for slot in result.slot_stats:
        rows.append((f"{SLOT_ROW_PREFIX}{slot.text}", str(slot.total_picks), _format_pct(slot.event_pct)))
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
