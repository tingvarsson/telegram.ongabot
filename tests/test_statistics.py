import unittest
from datetime import date
from unittest.mock import MagicMock

from telegram import InlineKeyboardMarkup

from ongabot.utils.statistics import (
    AVG_PARTICIPANTS_LABEL,
    CALLBACK_DATA_PREFIX,
    DEFAULT_SORT_KEY,
    MAX_TABLE_ROWS,
    NAME_WIDTH,
    NO_OP_TEXT,
    MAYBE_TEXT,
    SORT_COLUMNS,
    SlotStat,
    StatisticsResult,
    UserStatRow,
    build_sort_keyboard,
    compute_statistics,
    format_statistics,
    render_statistics_message,
)


def _make_user(user_id: int, name: str) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.full_name = name
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


def _row_for(result: StatisticsResult, user_id: int) -> UserStatRow:
    (row,) = (r for r in result.user_rows if r.user.id == user_id)
    return row


def _slot_for(result: StatisticsResult, text: str) -> SlotStat:
    (slot,) = (s for s in result.slot_stats if s.text == text)
    return slot


class ComputeStatisticsEmptyTest(unittest.TestCase):
    def test_no_events_returns_empty_result(self):
        chat = MagicMock()
        chat.events = {}

        result = compute_statistics(chat)

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

        result = compute_statistics(chat)

        self.assertEqual(result.event_count, 0)
        self.assertEqual(result.user_rows, [])


class ComputeStatisticsChatSummaryTest(unittest.TestCase):
    def test_answered_events_counts_events_with_at_least_one_response(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={alice: _make_answer([0])})
        e3 = _make_event(date(2026, 1, 15), num_slots=1, poll_answers={})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2, date(2026, 1, 15): e3}

        result = compute_statistics(chat)

        self.assertEqual(result.event_count, 3)
        self.assertEqual(result.answered_events, 2)

    def test_avg_participants_averages_over_answered_events_only(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        carol = _make_user(3, "Carol")
        dan = _make_user(4, "Dan")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0]), bob: _make_answer([0])})
        e2 = _make_event(
            date(2026, 1, 8),
            num_slots=1,
            poll_answers={
                alice: _make_answer([0]),
                bob: _make_answer([0]),
                carol: _make_answer([0]),
                dan: _make_answer([0]),
            },
        )
        e3 = _make_event(date(2026, 1, 15), num_slots=1, poll_answers={})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2, date(2026, 1, 15): e3}

        result = compute_statistics(chat)

        # (2 + 4) / 2 answered events = 3.0, not / 3 total events.
        self.assertAlmostEqual(result.avg_participants, 3.0)

    def test_avg_participants_none_when_no_events_answered(self):
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual(result.answered_events, 0)
        self.assertIsNone(result.avg_participants)


class ComputeStatisticsSlotStatsTest(unittest.TestCase):
    def test_total_picks_vs_event_pct_differ_when_multiple_users_pick_same_slot(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        e1 = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([0]), bob: _make_answer([0])},
            slot_texts=["18.30", "19.10"],
        )
        e2 = _make_event(date(2026, 1, 8), num_slots=2, poll_answers={}, slot_texts=["18.30", "19.10"])
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat)
        slot = _slot_for(result, "18.30")

        self.assertEqual(result.answered_events, 1)
        self.assertEqual(slot.total_picks, 2)  # both alice and bob picked it
        self.assertAlmostEqual(slot.event_pct, 1.0)  # picked in 1 of 1 answered events

    def test_slot_stats_sorted_by_text(self):
        alice = _make_user(1, "Alice")
        event = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([0, 1])},
            slot_texts=["19.10", "18.30"],
        )
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual([s.text for s in result.slot_stats], ["18.30", "19.10"])

    def test_no_op_and_maybe_excluded_from_slot_stats(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([2])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual(result.slot_stats, [])

    def test_no_slot_picks_yields_empty_slot_stats(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual(result.slot_stats, [])


class ComputeStatisticsUserRowsTest(unittest.TestCase):
    def test_first_seen_scopes_eligible_events(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={alice: _make_answer([0])})
        e3 = _make_event(date(2026, 1, 15), num_slots=1, poll_answers={alice: _make_answer([])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2, date(2026, 1, 15): e3}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        # Eligible events = [e2, e3] (2), not all 3 - alice wasn't seen before e2.
        self.assertEqual(row.responses, 1)
        self.assertEqual(row.didnt_bother, 1)
        self.assertAlmostEqual(row.response_pct, 0.5)

    def test_didnt_bother_counts_missed_eligible_events(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={})
        e3 = _make_event(date(2026, 1, 15), num_slots=1, poll_answers={})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2, date(2026, 1, 15): e3}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.responses, 1)
        self.assertEqual(row.didnt_bother, 2)

    def test_response_pct_uses_eligible_events_denominator(self):
        alice = _make_user(1, "Alice")
        events = {
            date(2026, 1, 1): _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])}),
            date(2026, 1, 8): _make_event(date(2026, 1, 8), num_slots=1, poll_answers={}),
            date(2026, 1, 15): _make_event(date(2026, 1, 15), num_slots=1, poll_answers={}),
            date(2026, 1, 22): _make_event(date(2026, 1, 22), num_slots=1, poll_answers={}),
        }
        chat = MagicMock()
        chat.events = events

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertAlmostEqual(row.response_pct, 0.25)

    def test_retracted_only_appearance_still_yields_a_row(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.responses, 0)
        self.assertEqual(row.didnt_bother, 1)
        self.assertEqual(row.response_pct, 0.0)

    def test_cancelled_only_appearance_yields_no_row(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])}, cancelled=True)
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual(result.user_rows, [])

    def test_slots_total_and_avg_across_multiple_responses(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=3, poll_answers={alice: _make_answer([0, 1])})
        e2 = _make_event(date(2026, 1, 8), num_slots=2, poll_answers={alice: _make_answer([0])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.slots_total, 3)
        self.assertEqual(row.responses, 2)
        self.assertAlmostEqual(row.slots_avg, 1.5)

    def test_streak_comes_from_latest_event_reused_in_row(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])}, user_streaks={1: 1})
        e2 = _make_event(date(2026, 1, 8), num_slots=1, poll_answers={alice: _make_answer([0])}, user_streaks={1: 2})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.streak, 2)

    def test_no_op_and_maybe_still_tracked_per_row(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        event = _make_event(
            date(2026, 1, 1),
            num_slots=2,
            poll_answers={alice: _make_answer([2]), bob: _make_answer([3])},  # alice=No-op, bob=Maybe
        )
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)

        self.assertEqual(_row_for(result, 1).no_op, 1)
        self.assertEqual(_row_for(result, 2).maybe, 1)

    def test_played_counts_events_with_at_least_one_slot_pick(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=2, poll_answers={alice: _make_answer([2])})  # No-op only
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): e1, date(2026, 1, 8): e2}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.responses, 2)
        self.assertEqual(row.played, 1)

    def test_played_counts_once_per_event_even_with_multiple_slots(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=3, poll_answers={alice: _make_answer([0, 1])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        self.assertEqual(row.played, 1)

    def test_play_pct_uses_eligible_events_denominator(self):
        alice = _make_user(1, "Alice")
        e1 = _make_event(date(2026, 1, 1), num_slots=2, poll_answers={alice: _make_answer([0])})
        e2 = _make_event(date(2026, 1, 8), num_slots=2, poll_answers={alice: _make_answer([2])})  # No-op only
        e3 = _make_event(date(2026, 1, 15), num_slots=2, poll_answers={})
        e4 = _make_event(date(2026, 1, 22), num_slots=2, poll_answers={})
        chat = MagicMock()
        chat.events = {
            date(2026, 1, 1): e1,
            date(2026, 1, 8): e2,
            date(2026, 1, 15): e3,
            date(2026, 1, 22): e4,
        }

        result = compute_statistics(chat)
        row = _row_for(result, 1)

        # played=1 out of 4 eligible events (not out of 2 responses).
        self.assertEqual(row.played, 1)
        self.assertAlmostEqual(row.play_pct, 0.25)


class SortColumnsTest(unittest.TestCase):
    def test_maybe_ordered_before_noop(self):
        keys = [c.key for c in SORT_COLUMNS]
        self.assertLess(keys.index("maybe"), keys.index("noop"))

    def test_slots_button_label_is_total_slots(self):
        column = next(c for c in SORT_COLUMNS if c.key == "slots")
        self.assertEqual(column.button_label, "Total Slots")

    def test_bother_button_label_is_didnt_bother_answer(self):
        column = next(c for c in SORT_COLUMNS if c.key == "bother")
        self.assertEqual(column.button_label, "Didn't Bother Answer")

    def test_played_column_exists(self):
        column = next(c for c in SORT_COLUMNS if c.key == "played")
        self.assertEqual(column.button_label, "Played")

    def test_resp_rate_button_label_is_response_rate(self):
        column = next(c for c in SORT_COLUMNS if c.key == "resp_rate")
        self.assertEqual(column.button_label, "Response Rate")
        self.assertEqual(column.header, "Resp%")

    def test_play_rate_column_exists(self):
        column = next(c for c in SORT_COLUMNS if c.key == "play_rate")
        self.assertEqual(column.button_label, "Played Rate")
        self.assertEqual(column.header, "Play%")

    def test_column_order_starts_resp_resprate_streak_play_playrate(self):
        keys = [c.key for c in SORT_COLUMNS]
        self.assertEqual(keys[:5], ["responses", "resp_rate", "streak", "played", "play_rate"])


class FormatStatisticsTableTest(unittest.TestCase):
    def test_no_events_message(self):
        text = format_statistics(StatisticsResult())
        self.assertIn("No event history", text)

    def test_chat_table_merges_summary_and_slot_rows(self):
        result = StatisticsResult(
            event_count=3,
            answered_events=2,
            avg_participants=2.5,
            slot_stats=[SlotStat(text="18.30", total_picks=3, event_pct=1.0)],
            user_rows=[UserStatRow(user=_make_user(1, "Alice"), responses=1)],
        )

        text = format_statistics(result)

        self.assertIn("Chat Statistics", text)
        self.assertIn("Total Events", text)
        self.assertIn("Answered Events", text)
        self.assertIn("Average number of Bangers per event", text)
        self.assertIn("2.5", text)
        self.assertIn("Slot picked - 18.30", text)
        self.assertIn("100%", text)

    def test_chat_table_has_no_header_row(self):
        result = StatisticsResult(
            event_count=3,
            answered_events=2,
            avg_participants=2.5,
            slot_stats=[SlotStat(text="18.30", total_picks=3, event_pct=1.0)],
        )

        text = format_statistics(result)

        chat_table = text.split("```")[1]
        lines = chat_table.strip("\n").splitlines()
        # 3 summary rows + 1 slot row, no header line.
        self.assertEqual(len(lines), 4)

    def test_chat_table_rows_are_column_aligned(self):
        result = StatisticsResult(event_count=3, answered_events=2, avg_participants=2.0)

        text = format_statistics(result)

        chat_table = text.split("```")[1]
        lines = chat_table.strip("\n").splitlines()
        what_width = len(AVG_PARTICIPANTS_LABEL)
        for line in lines:
            self.assertEqual(line[what_width], " ")

    def test_answered_events_shows_percentage_of_total(self):
        result = StatisticsResult(event_count=4, answered_events=3, avg_participants=2.0)

        text = format_statistics(result)

        self.assertIn("75%", text)

    def test_total_events_percentage_is_always_100(self):
        result = StatisticsResult(event_count=5, answered_events=2, avg_participants=1.0)

        text = format_statistics(result)

        chat_table = text.split("```")[1]
        total_events_line = next(line for line in chat_table.splitlines() if line.startswith("Total Events"))
        self.assertTrue(total_events_line.rstrip().endswith("100%"))

    def test_avg_bangers_percentage_of_known_users(self):
        result = StatisticsResult(
            event_count=2,
            answered_events=2,
            avg_participants=2.0,
            user_rows=[
                UserStatRow(user=_make_user(1, "Alice"), responses=2),
                UserStatRow(user=_make_user(2, "Bob"), responses=2),
                UserStatRow(user=_make_user(3, "Carol"), responses=0),
                UserStatRow(user=_make_user(4, "Dan"), responses=0),
            ],
        )

        text = format_statistics(result)

        chat_table = text.split("```")[1]
        bangers_line = next(line for line in chat_table.splitlines() if AVG_PARTICIPANTS_LABEL in line)
        # avg_participants=2.0 out of 4 known users -> 50%.
        self.assertTrue(bangers_line.rstrip().endswith("50%"))

    def test_avg_bangers_dash_when_no_answers(self):
        result = StatisticsResult(event_count=1, answered_events=0, avg_participants=None)

        text = format_statistics(result)

        chat_table = text.split("```")[1]
        bangers_line = next(line for line in chat_table.splitlines() if AVG_PARTICIPANTS_LABEL in line)
        tokens = bangers_line.split()
        self.assertEqual(tokens[-2], "-")
        self.assertEqual(tokens[-1], "-")

    def test_empty_user_rows_shows_no_participation_message(self):
        text = format_statistics(StatisticsResult(event_count=1))
        self.assertIn("No participation data", text)

    def test_user_statistics_header_and_sort_caption_present(self):
        result = StatisticsResult(event_count=1, user_rows=[UserStatRow(user=_make_user(1, "Alice"), responses=1)])

        text = format_statistics(result)

        self.assertIn("User Statistics", text)
        self.assertIn("sort", text.lower())
        sort_index = text.lower().index("sort")
        self.assertIn("User Statistics", text[sort_index:])

    def test_table_wrapped_in_fenced_code_block(self):
        result = StatisticsResult(event_count=1, user_rows=[UserStatRow(user=_make_user(1, "Alice"), responses=1)])
        text = format_statistics(result)
        self.assertGreaterEqual(text.count("```"), 2)

    def test_default_sort_is_by_responses_descending(self):
        alice = UserStatRow(user=_make_user(1, "Alice"), responses=2, streak=1)
        bob = UserStatRow(user=_make_user(2, "Bob"), responses=5, streak=0)
        result = StatisticsResult(event_count=1, user_rows=[alice, bob])

        text = format_statistics(result)

        self.assertLess(text.index("Bob"), text.index("Alice"))

    def test_sort_by_param_changes_row_order(self):
        alice = UserStatRow(user=_make_user(1, "Alice"), responses=2, streak=5)
        bob = UserStatRow(user=_make_user(2, "Bob"), responses=5, streak=0)
        result = StatisticsResult(event_count=1, user_rows=[alice, bob])

        text = format_statistics(result, sort_by="streak")

        self.assertLess(text.index("Alice"), text.index("Bob"))

    def test_unknown_sort_by_falls_back_to_default(self):
        alice = UserStatRow(user=_make_user(1, "Alice"), responses=2, streak=5)
        bob = UserStatRow(user=_make_user(2, "Bob"), responses=5, streak=0)
        result = StatisticsResult(event_count=1, user_rows=[alice, bob])

        text = format_statistics(result, sort_by="not_a_real_column")

        self.assertLess(text.index("Bob"), text.index("Alice"))

    def test_table_capped_to_max_rows(self):
        rows = [UserStatRow(user=_make_user(i, f"U{i}"), responses=i) for i in range(MAX_TABLE_ROWS + 5)]
        result = StatisticsResult(event_count=1, user_rows=rows)

        text = format_statistics(result)

        user_table = text.split("```")[-2]
        data_lines = user_table.strip("\n").splitlines()[1:]  # drop header line
        self.assertEqual(len(data_lines), MAX_TABLE_ROWS)

    def test_long_name_is_truncated_with_dot_marker(self):
        long_name = "A" * (NAME_WIDTH + 5)
        result = StatisticsResult(event_count=1, user_rows=[UserStatRow(user=_make_user(1, long_name), responses=1)])

        text = format_statistics(result)

        expected_cell = "A" * (NAME_WIDTH - 1) + "."
        self.assertIn(expected_cell, text)
        self.assertNotIn(long_name, text)

    def test_short_name_is_padded_to_column_width(self):
        result = StatisticsResult(event_count=1, user_rows=[UserStatRow(user=_make_user(1, "Bo"), responses=1)])

        text = format_statistics(result)

        self.assertIn("Bo".ljust(NAME_WIDTH) + " ", text)

    def test_name_with_backtick_and_backslash_is_escaped(self):
        result = StatisticsResult(event_count=1, user_rows=[UserStatRow(user=_make_user(1, "A`B\\C"), responses=1)])

        text = format_statistics(result)

        self.assertIn("A\\`B\\\\C", text)


class RenderStatisticsMessageTest(unittest.TestCase):
    def test_returns_text_and_keyboard(self):
        alice = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), num_slots=1, poll_answers={alice: _make_answer([0])})
        chat = MagicMock()
        chat.events = {date(2026, 1, 1): event}

        text, keyboard = render_statistics_message(chat)

        self.assertIn("Chat Statistics", text)
        self.assertIsInstance(keyboard, InlineKeyboardMarkup)


class BuildSortKeyboardTest(unittest.TestCase):
    def _all_buttons(self):
        keyboard = build_sort_keyboard()
        return [button for row in keyboard.inline_keyboard for button in row]

    def test_one_button_per_column(self):
        self.assertEqual(len(self._all_buttons()), len(SORT_COLUMNS))

    def test_callback_data_uses_prefix_and_key(self):
        streak_button = next(b for b in self._all_buttons() if b.callback_data == f"{CALLBACK_DATA_PREFIX}:streak")
        self.assertIsNotNone(streak_button)

    def test_all_callback_data_under_64_bytes(self):
        for button in self._all_buttons():
            self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


class DefaultSortKeyIsValidColumnTest(unittest.TestCase):
    def test_default_sort_key_is_a_real_column(self):
        self.assertIn(DEFAULT_SORT_KEY, [c.key for c in SORT_COLUMNS])


if __name__ == "__main__":
    unittest.main()
