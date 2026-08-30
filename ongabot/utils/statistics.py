"""Utilities for computing and formatting chat-wide participation statistics."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from telegram import User
from telegram.helpers import escape_markdown

from chat import Chat
from event import Event

_logger = logging.getLogger(__name__)

# Option texts for the two non-slot poll options, see eventcreator._create_poll_options.
NO_OP_TEXT = "No-op"
MAYBE_TEXT = "Maybe Baby </3"

Leaderboard = List[Tuple[User, int]]


@dataclass
class StatisticsResult:
    """Computed chat-wide statistics, ready for formatting into a message."""

    event_count: int = 0
    participation_rate: Optional[float] = None
    most_active: Leaderboard = field(default_factory=list)
    streak_leaders: Leaderboard = field(default_factory=list)
    top_slot: Optional[Tuple[str, int]] = None
    most_no_op: Leaderboard = field(default_factory=list)
    most_maybe: Leaderboard = field(default_factory=list)


def _top_n(counts: Dict[int, int], user_by_id: Dict[int, User], n: int) -> Leaderboard:
    """Resolve the top n (user_id, count) pairs to (User, count), skipping unresolvable ids."""
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]
    resolved: Leaderboard = []
    for user_id, count in ranked:
        user = user_by_id.get(user_id)
        if user is None:
            _logger.warning("No User found for user_id=%s while building statistics leaderboard", user_id)
            continue
        resolved.append((user, count))
    return resolved


def _tally_event(
    event: Event,
    total_responses: Dict[int, int],
    slot_counts: Dict[str, int],
    no_op_counts: Dict[int, int],
    maybe_counts: Dict[int, int],
    user_by_id: Dict[int, User],
) -> int:
    """Tally one event's poll answers into the given accumulators; returns respondent count."""
    respondents = 0
    for user, answer in event.poll_answers.items():
        user_by_id[user.id] = user
        if not answer.option_ids:
            continue
        respondents += 1
        total_responses[user.id] = total_responses.get(user.id, 0) + 1
        for option_id in answer.option_ids:
            option_text = event.poll.options[option_id].text
            if option_id < event.num_slots:
                slot_counts[option_text] = slot_counts.get(option_text, 0) + 1
            elif option_text == NO_OP_TEXT:
                no_op_counts[user.id] = no_op_counts.get(user.id, 0) + 1
            elif option_text == MAYBE_TEXT:
                maybe_counts[user.id] = maybe_counts.get(user.id, 0) + 1
    return respondents


def _compute_participation_rate(respondent_counts: List[int], chat_member_count: int) -> Optional[float]:
    """Average respondents per event, divided by today's member count (excluding the bot itself)."""
    effective_member_count = chat_member_count - 1
    if effective_member_count <= 0:
        return None
    return (sum(respondent_counts) / len(respondent_counts)) / effective_member_count


def compute_statistics(chat: Chat, chat_member_count: int, top_n: int = 5) -> StatisticsResult:
    """Compute all-time, chat-wide participation statistics from a chat's event history.

    Cancelled events are excluded. Retracted votes (empty option_ids) are excluded from
    response/slot/No-op/Maybe counts. Streak leaders are read from the latest event's
    already-maintained user_streaks. Participation rate approximates historical chat
    membership with today's member count, since no historical snapshot exists.
    """
    events = sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date)
    if not events:
        return StatisticsResult()

    total_responses: Dict[int, int] = {}
    no_op_counts: Dict[int, int] = {}
    maybe_counts: Dict[int, int] = {}
    slot_counts: Dict[str, int] = {}
    user_by_id: Dict[int, User] = {}
    respondent_counts = [
        _tally_event(event, total_responses, slot_counts, no_op_counts, maybe_counts, user_by_id) for event in events
    ]

    latest_event = events[-1]
    top_slot = max(slot_counts.items(), key=lambda kv: kv[1]) if slot_counts else None

    return StatisticsResult(
        event_count=len(events),
        participation_rate=_compute_participation_rate(respondent_counts, chat_member_count),
        most_active=_top_n(total_responses, user_by_id, top_n),
        streak_leaders=_top_n(dict(latest_event.user_streaks), user_by_id, top_n),
        top_slot=top_slot,
        most_no_op=_top_n(no_op_counts, user_by_id, top_n),
        most_maybe=_top_n(maybe_counts, user_by_id, top_n),
    )


def _format_leaderboard(title: str, leaderboard: Leaderboard, suffix: str = "") -> str:
    if not leaderboard:
        return ""
    lines = [f"*{title}*"]
    for i, (user, count) in enumerate(leaderboard, start=1):
        lines.append(f"{i}\\. {user.mention_markdown_v2()} \\({count}{suffix}\\)")
    return "\n".join(lines)


def format_statistics(result: StatisticsResult) -> str:
    """Format a StatisticsResult into a MarkdownV2 message for /statistics."""
    if result.event_count == 0:
        return "No event history yet for this chat\\!"

    sections = [
        f"*__Chat Statistics__* \\(across {result.event_count} tracked events\\)",
    ]

    if result.participation_rate is not None:
        sections.append(f"Average participation: *{result.participation_rate * 100:.0f}%*")

    sections.append(_format_leaderboard("Most Active", result.most_active, " responses"))
    sections.append(_format_leaderboard("Streak Leaders", result.streak_leaders, " streak"))

    if result.top_slot is not None:
        slot_text, count = result.top_slot
        sections.append(f"*Most Popular Slot:* {escape_markdown(slot_text, version=2)} \\({count} picks\\)")

    sections.append(_format_leaderboard("Biggest Flakes \\(No\\-op\\)", result.most_no_op))
    sections.append(_format_leaderboard("Most Indecisive \\(Maybe Baby\\)", result.most_maybe))

    return "\n\n".join(section for section in sections if section)
