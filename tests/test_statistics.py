import unittest
from datetime import date
from unittest.mock import MagicMock

from ongabot.utils.statistics import NO_OP_TEXT, MAYBE_TEXT, StatisticsResult, compute_statistics, format_statistics


def _make_user(user_id: int, name: str) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.name = name
    user.mention_markdown_v2.return_value = f"[{name}](tg://user?id={user_id})"
    return user


def _make_answer(option_ids) -> MagicMock:
    answer = MagicMock()
    answer.option_ids = tuple(option_ids)
    return answer


def _make_poll(option_texts):
    poll = MagicMock()
    poll.options = [MagicMock(text=text) for text in option_texts]
    return poll


def _make_event(
    event_date: date,
    num_slots: int,
    poll_answers,
    user_streaks=None,
    cancelled: bool = False,
    slot_texts=None,
):
    """Build an event mock with num_slots time slots followed by No-op / Maybe Baby options."""
    event = MagicMock()
    event.event_date = event_date
    event.num_slots = num_slots
    event.cancelled = cancelled
    event.poll_answers = poll_answers
    event.user_streaks = user_streaks or {}
    slot_texts = slot_texts or [f"slot{i}" for i in range(num_slots)]
    event.poll = _make_poll(slot_texts + [NO_OP_TEXT, MAYBE_TEXT])
    return event


class ComputeStatisticsEmptyTest(unittest.TestCase):
    def test_no_events_returns_empty_result(self):
        chat = MagicMock()
        chat.events = {}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result, StatisticsResult())

    def test_only_cancelled_events_returns_empty_result(self):
        alice = _make_user(1, "Alice")
        event = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([0])},
            cancelled=True,
        )
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.event_count, 0)


class ComputeStatisticsMostActiveTest(unittest.TestCase):
    def test_counts_one_response_per_event_regardless_of_options_picked(self):
        alice = _make_user(1, "Alice")
        # Alice picks two slots in the same event - still one response.
        event = _make_event(date(2026, 1, 1), num_slots=3, poll_answers={alice: _make_answer([0, 1])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.most_active, [(alice, 1)])

    def test_aggregates_across_multiple_events(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        e1 = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([0]), bob: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=2, poll_answers={alice: _make_answer([1])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.most_active, [(alice, 2), (bob, 1)])

    def test_retracted_vote_does_not_count_as_response(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.most_active, [])

    def test_leaderboard_limited_to_top_n(self):
        users = [_make_user(i, f"U{i}") for i in range(7)]
        poll_answers = {u: _make_answer([0]) for u in users}
        event = _make_event(date(2026, 1, 1), num_slots=2, poll_answers=poll_answers)
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10, top_n=5)

        self.assertEqual(len(result.most_active), 5)


class ComputeStatisticsSlotAndOptionTest(unittest.TestCase):
    def test_most_popular_slot_excludes_no_op_and_maybe(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        event = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([0]), bob: _make_answer([2])},  # bob picks No-op
            slot_texts=["18.30", "19.10"],
        )
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.top_slot, ("18.30", 1))

    def test_no_op_and_maybe_tracked_per_user(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        event = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([2]), bob: _make_answer([3])},  # alice=No-op, bob=Maybe
        )
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.most_no_op, [(alice, 1)])
        self.assertEqual(result.most_maybe, [(bob, 1)])

    def test_no_slot_votes_yields_none_top_slot(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([2])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertIsNone(result.top_slot)


class ComputeStatisticsStreaksTest(unittest.TestCase):
    def test_streak_leaders_come_from_latest_event(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])}, user_streaks={1: 1})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={alice: _make_answer([0])}, user_streaks={1: 2})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.streak_leaders, [(alice, 2)])

    def test_streak_entry_without_matching_user_is_skipped(self):
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={}, user_streaks={999: 3})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=10)

        self.assertEqual(result.streak_leaders, [])


class ComputeStatisticsParticipationRateTest(unittest.TestCase):
    def test_participation_rate_averages_respondents_over_effective_member_count(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        # event 1: 2 respondents, event 2: 0 respondents -> avg 1
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0]), bob: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        # chat_member_count=11 -> effective member count (excluding bot) = 10 -> rate = 1/10
        result = compute_statistics(chat, chat_member_count=11)

        self.assertAlmostEqual(result.participation_rate, 0.1)

    def test_participation_rate_none_when_effective_member_count_not_positive(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat, chat_member_count=1)

        self.assertIsNone(result.participation_rate)


class FormatStatisticsTest(unittest.TestCase):
    def test_no_events_message(self):
        text = format_statistics(StatisticsResult())
        self.assertIn("No event history", text)

    def test_empty_leaderboard_section_omitted(self):
        result = StatisticsResult(event_count=1, most_no_op=[])

        text = format_statistics(result)

        self.assertNotIn("Biggest Flakes", text)

    def test_includes_event_count_and_leaderboards(self):
        alice = _make_user(1, "Alice")
        result = StatisticsResult(
            event_count=3,
            participation_rate=0.5,
            most_active=[(alice, 3)],
            streak_leaders=[(alice, 3)],
            top_slot=("18.30", 2),
            most_no_op=[(alice, 1)],
            most_maybe=[(alice, 1)],
        )

        text = format_statistics(result)

        self.assertIn("3", text)
        self.assertIn(alice.mention_markdown_v2(), text)
        self.assertIn("18", text)


if __name__ == "__main__":
    unittest.main()
