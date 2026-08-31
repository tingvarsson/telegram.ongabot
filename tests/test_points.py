import math
import unittest
from datetime import date
from unittest.mock import MagicMock

from ongabot.utils.points import (
    FORM_EVENT_COUNT,
    MAX_LEADERBOARD_ROWS,
    MAX_RECAP_ROWS,
    POINTS_ANSWERED,
    POINTS_BOOTED,
    POINTS_CLUTCH,
    POINTS_FLEX,
    POINTS_NO_OP,
    POINTS_RARITY,
    POINTS_RESCUE,
    POINTS_TRAILBLAZER,
    QUORUM,
    EventScore,
    PointsResult,
    compute_event_outcome,
    compute_points,
    format_event_recap,
    format_leaderboard,
    render_event_recap_message,
    render_leaderboard_message,
    score_event,
    _slot_rarity,
)
from ongabot.utils.statistics import MAYBE_TEXT, NO_OP_TEXT

# Timed slot texts, so tests exercise the same near-identical-time grouping /statistics uses.
SLOTS = ["18.30", "19.10", "19.50", "20.30", "21.10"]


def _make_user(user_id: int, name: str, last_name: str = "") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.first_name = name
    user.last_name = last_name
    return user


def _make_answer(option_ids) -> MagicMock:
    answer = MagicMock()
    answer.option_ids = tuple(option_ids)
    return answer


def _make_event(
    event_date: date,
    num_slots: int,
    poll_answers,
    cancelled: bool = False,
    slot_texts=None,
    first_answer=None,
):
    """Build an event mock with num_slots time slots followed by No-op / Maybe Baby options."""
    event = MagicMock()
    event.event_date = event_date
    event.num_slots = num_slots
    event.cancelled = cancelled
    event.poll_answers = poll_answers
    event.first_answer = first_answer
    texts = list(slot_texts or SLOTS[:num_slots])
    poll = MagicMock()
    poll.options = [MagicMock(text=text) for text in texts + [NO_OP_TEXT, MAYBE_TEXT]]
    event.poll = poll
    return event


def _make_chat(events):
    chat = MagicMock()
    chat.chat_id = 42
    chat.events = {event.event_date: event for event in events}
    return chat


def _no_rarity(num_slots: int = 5):
    """label_of / rarity pair that scores no rarity, for isolating the other components."""
    return {text: text for text in SLOTS[:num_slots]}, {}


class ComputeEventOutcomeTest(unittest.TestCase):
    def test_counts_picks_per_slot(self):
        event = _make_event(
            date(2026, 1, 1),
            num_slots=3,
            poll_answers={
                _make_user(1, "Alice"): _make_answer([0, 1]),
                _make_user(2, "Bob"): _make_answer([1]),
            },
        )

        outcome = compute_event_outcome(event)

        self.assertEqual(outcome.slot_counts, (1, 2, 0))
        self.assertEqual(outcome.winning_slot, 1)
        self.assertEqual(outcome.winning_text, "19.10")
        self.assertEqual(outcome.votes, 2)

    def test_ties_go_to_the_earliest_slot(self):
        event = _make_event(
            date(2026, 1, 1),
            num_slots=3,
            poll_answers={_make_user(1, "Alice"): _make_answer([1, 2])},
        )

        outcome = compute_event_outcome(event)

        self.assertEqual(outcome.slot_counts, (0, 1, 1))
        self.assertEqual(outcome.winning_slot, 1)

    def test_non_slot_options_are_not_slots(self):
        # Option ids 3 and 4 are No-op / Maybe Baby for a 3-slot event.
        event = _make_event(
            date(2026, 1, 1),
            num_slots=3,
            poll_answers={_make_user(1, "Alice"): _make_answer([3, 4])},
        )

        outcome = compute_event_outcome(event)

        self.assertEqual(outcome.slot_counts, (0, 0, 0))
        self.assertIsNone(outcome.winning_slot)
        self.assertIsNone(outcome.winning_text)
        self.assertEqual(outcome.votes, 0)
        self.assertFalse(outcome.went_ahead)

    def test_no_answers_has_no_winner(self):
        outcome = compute_event_outcome(_make_event(date(2026, 1, 1), num_slots=3, poll_answers={}))

        self.assertIsNone(outcome.winning_slot)
        self.assertFalse(outcome.went_ahead)

    def _outcome_with_votes(self, votes: int):
        answers = {_make_user(i, f"U{i}"): _make_answer([0]) for i in range(votes)}
        return compute_event_outcome(_make_event(date(2026, 1, 1), num_slots=2, poll_answers=answers))

    def test_went_ahead_exactly_at_quorum(self):
        outcome = self._outcome_with_votes(QUORUM)

        self.assertEqual(outcome.votes, QUORUM)
        self.assertTrue(outcome.went_ahead)

    def test_did_not_go_ahead_one_below_quorum(self):
        self.assertFalse(self._outcome_with_votes(QUORUM - 1).went_ahead)

    def test_went_ahead_one_above_quorum(self):
        self.assertTrue(self._outcome_with_votes(QUORUM + 1).went_ahead)


class SlotRarityTest(unittest.TestCase):
    def test_least_popular_slot_earns_full_rarity_and_most_popular_none(self):
        # slot 0 picked once, slot 1 picked twice, slot 2 three times.
        events = [
            _make_event(
                date(2026, 1, 1),
                num_slots=3,
                poll_answers={
                    _make_user(1, "Alice"): _make_answer([0, 1, 2]),
                    _make_user(2, "Bob"): _make_answer([1, 2]),
                    _make_user(3, "Cara"): _make_answer([2]),
                },
            )
        ]

        _label_of, rarity = _slot_rarity(events)

        self.assertAlmostEqual(rarity["18.30"], POINTS_RARITY)
        self.assertAlmostEqual(rarity["19.50"], 0.0)
        self.assertAlmostEqual(rarity["19.10"], POINTS_RARITY * 0.5)

    def test_equally_popular_slots_earn_no_rarity(self):
        events = [
            _make_event(
                date(2026, 1, 1),
                num_slots=3,
                poll_answers={_make_user(1, "Alice"): _make_answer([0, 1, 2])},
            )
        ]

        _label_of, rarity = _slot_rarity(events)

        self.assertEqual(set(rarity.values()), {0.0})

    def test_near_identical_times_share_one_rarity_group(self):
        # 20.30 and 20.40 are the same slot spelled differently across events.
        events = [
            _make_event(
                date(2026, 1, 1),
                num_slots=2,
                slot_texts=["18.30", "20.30"],
                poll_answers={_make_user(1, "Alice"): _make_answer([0, 1])},
            ),
            _make_event(
                date(2026, 1, 8),
                num_slots=2,
                slot_texts=["18.30", "20.40"],
                poll_answers={_make_user(1, "Alice"): _make_answer([1])},
            ),
        ]

        label_of, rarity = _slot_rarity(events)

        self.assertEqual(label_of["20.30"], label_of["20.40"])
        self.assertIn("20.30-20.40", rarity)
        # The group has 3 picks against 18.30's 2, so 18.30 is the rare one.
        self.assertAlmostEqual(rarity["18.30"], POINTS_RARITY)
        self.assertAlmostEqual(rarity["20.30-20.40"], 0.0)

    def test_no_picks_yields_no_rarity(self):
        _label_of, rarity = _slot_rarity([_make_event(date(2026, 1, 1), num_slots=2, poll_answers={})])

        self.assertEqual(rarity, {})


class ScoreEventComponentsTest(unittest.TestCase):
    """Each Banger Points component in isolation; rarity is zeroed unless under test."""

    def _score(self, option_ids, num_slots=5, first_answer=None, extra_answers=None):
        user = _make_user(1, "Alice")
        answers = {user: _make_answer(option_ids)}
        answers.update(extra_answers or {})
        event = _make_event(date(2026, 1, 1), num_slots, answers, first_answer=first_answer)
        outcome = compute_event_outcome(event)
        label_of, rarity = _no_rarity(num_slots)
        return score_event(event, outcome, label_of, rarity)[1]

    def test_retracted_vote_scores_nothing(self):
        user = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), 5, {user: _make_answer([])})
        label_of, rarity = _no_rarity()

        scores = score_event(event, compute_event_outcome(event), label_of, rarity)

        self.assertEqual(scores, {})

    def test_maybe_only_scores_the_answer_point(self):
        score = self._score([6])  # option 6 is Maybe Baby for a 5-slot event

        self.assertEqual(score.total, POINTS_ANSWERED)
        self.assertEqual(score.no_op, 0.0)
        self.assertEqual(score.slots, 0)

    def test_honest_no_op_beats_ghosting(self):
        score = self._score([5])  # option 5 is No-op for a 5-slot event

        self.assertEqual(score.answered, POINTS_ANSWERED)
        self.assertEqual(score.no_op, POINTS_NO_OP)
        self.assertEqual(score.total, POINTS_ANSWERED + POINTS_NO_OP)

    def test_booting_up_scores_answered_plus_booted(self):
        score = self._score([0])

        self.assertEqual(score.answered, POINTS_ANSWERED)
        self.assertEqual(score.booted, POINTS_BOOTED)
        self.assertEqual(score.flex, 0.0)  # one slot is the baseline, no flex yet
        self.assertEqual(score.slots, 1)

    def test_flex_curve_has_diminishing_returns(self):
        for slots in range(1, 6):
            with self.subTest(slots=slots):
                score = self._score(list(range(slots)))

                self.assertAlmostEqual(score.flex, POINTS_FLEX * (math.sqrt(slots) - 1))
                self.assertEqual(score.slots, slots)

        # Picking all five is worth far less than five times picking one.
        self.assertLess(self._score([0, 1, 2, 3, 4]).flex, POINTS_FLEX * 4)

    def test_rarity_scores_per_picked_slot(self):
        user = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), 5, {user: _make_answer([0, 1])})
        rarity = {"18.30": POINTS_RARITY, "19.10": 0.5}
        label_of = {text: text for text in SLOTS}

        score = score_event(event, compute_event_outcome(event), label_of, rarity)[1]

        self.assertAlmostEqual(score.rarity, POINTS_RARITY + 0.5)

    def test_trailblazer_scores_for_the_first_answer_only(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        event = _make_event(
            date(2026, 1, 1),
            5,
            {alice: _make_answer([0]), bob: _make_answer([0])},
            first_answer=alice,
        )
        label_of, rarity = _no_rarity()

        scores = score_event(event, compute_event_outcome(event), label_of, rarity)

        self.assertEqual(scores[1].trailblazer, POINTS_TRAILBLAZER)
        self.assertEqual(scores[2].trailblazer, 0.0)


class ScoreEventClutchTest(unittest.TestCase):
    """Clutch and rescue: the bonuses that make a decisive vote worth more than a redundant one."""

    def _scores_for_winning_slot_votes(self, votes: int, num_slots: int = 5):
        answers = {_make_user(i, f"U{i}"): _make_answer([0]) for i in range(votes)}
        event = _make_event(date(2026, 1, 1), num_slots, answers)
        outcome = compute_event_outcome(event)
        label_of, rarity = _no_rarity(num_slots)
        return score_event(event, outcome, label_of, rarity), outcome

    def test_bare_quorum_pays_full_clutch_and_rescue(self):
        scores, outcome = self._scores_for_winning_slot_votes(QUORUM)

        self.assertTrue(outcome.went_ahead)
        for score in scores.values():
            self.assertAlmostEqual(score.clutch, POINTS_CLUTCH)
            self.assertAlmostEqual(score.rescue, POINTS_RESCUE)

    def test_double_quorum_halves_clutch_and_pays_no_rescue(self):
        scores, _outcome = self._scores_for_winning_slot_votes(QUORUM * 2)

        for score in scores.values():
            self.assertAlmostEqual(score.clutch, POINTS_CLUTCH / 2)
            self.assertEqual(score.rescue, 0.0)

    def test_rescue_fires_only_at_exact_quorum(self):
        for votes in (QUORUM - 1, QUORUM, QUORUM + 1):
            with self.subTest(votes=votes):
                scores, _outcome = self._scores_for_winning_slot_votes(votes)
                rescued = any(s.rescue > 0 for s in scores.values())

                self.assertEqual(rescued, votes == QUORUM)

    def test_below_quorum_pays_no_clutch(self):
        scores, outcome = self._scores_for_winning_slot_votes(QUORUM - 1)

        self.assertFalse(outcome.went_ahead)
        for score in scores.values():
            self.assertEqual(score.clutch, 0.0)
            self.assertEqual(score.rescue, 0.0)

    def test_missing_the_winning_slot_pays_no_clutch(self):
        # QUORUM users take slot 0; one straggler takes only slot 1.
        answers = {_make_user(i, f"U{i}"): _make_answer([0]) for i in range(QUORUM)}
        straggler = _make_user(99, "Zed")
        answers[straggler] = _make_answer([1])
        event = _make_event(date(2026, 1, 1), 5, answers)
        label_of, rarity = _no_rarity()

        scores = score_event(event, compute_event_outcome(event), label_of, rarity)

        self.assertAlmostEqual(scores[0].clutch, POINTS_CLUTCH)
        self.assertEqual(scores[99].clutch, 0.0)
        self.assertEqual(scores[99].rescue, 0.0)


class EventScoreTagsTest(unittest.TestCase):
    """The short reasons the recap prints, so people can see what actually pays."""

    def test_rescue_supersedes_clutch(self):
        score = EventScore(clutch=POINTS_CLUTCH, rescue=POINTS_RESCUE)

        self.assertEqual(score.tags, ["rescue"])

    def test_clutch_alone_is_tagged_clutch(self):
        self.assertEqual(EventScore(clutch=POINTS_CLUTCH / 2).tags, ["clutch"])

    def test_rare_slots_tagged_at_a_full_rarity_pick(self):
        self.assertEqual(EventScore(rarity=POINTS_RARITY).tags, ["rare slots"])
        self.assertEqual(EventScore(rarity=POINTS_RARITY - 0.1).tags, [])

    def test_trailblazer_is_tagged_first_in(self):
        self.assertEqual(EventScore(trailblazer=POINTS_TRAILBLAZER).tags, ["first in"])

    def test_tags_combine_in_reading_order(self):
        score = EventScore(
            rescue=POINTS_RESCUE,
            clutch=POINTS_CLUTCH,
            rarity=POINTS_RARITY,
            trailblazer=POINTS_TRAILBLAZER,
        )

        self.assertEqual(score.tags, ["rescue", "rare slots", "first in"])

    def test_a_plain_showing_up_has_no_tags(self):
        self.assertEqual(EventScore(answered=POINTS_ANSWERED, booted=POINTS_BOOTED).tags, [])


class ComputePointsTest(unittest.TestCase):
    def _event_on(self, day: int, users, cancelled=False):
        return _make_event(
            date(2026, 1, day),
            num_slots=5,
            poll_answers={user: _make_answer([0]) for user in users},
            cancelled=cancelled,
        )

    def test_empty_chat_returns_empty_result(self):
        result = compute_points(_make_chat([]))

        self.assertEqual(result, PointsResult())

    def test_only_cancelled_events_returns_empty_result(self):
        alice = _make_user(1, "Alice")

        result = compute_points(_make_chat([self._event_on(1, [alice], cancelled=True)]))

        self.assertEqual(result, PointsResult())

    def test_cancelled_events_are_excluded_from_scoring(self):
        alice = _make_user(1, "Alice")
        chat = _make_chat([self._event_on(1, [alice]), self._event_on(2, [alice], cancelled=True)])

        result = compute_points(chat)

        self.assertEqual(len(result.outcomes), 1)
        (row,) = result.rows
        # One event scored: answered + booted, with no flex, rarity, clutch or trailblazer.
        self.assertAlmostEqual(row.all_time, POINTS_ANSWERED + POINTS_BOOTED)

    def test_form_equals_all_time_when_history_is_short(self):
        alice = _make_user(1, "Alice")
        chat = _make_chat([self._event_on(day, [alice]) for day in range(1, 4)])

        result = compute_points(chat)
        (row,) = result.rows

        self.assertEqual(result.form_event_count, 3)
        self.assertAlmostEqual(row.form, row.all_time)

    def test_form_window_covers_only_the_most_recent_events(self):
        alice = _make_user(1, "Alice")
        # One more event than the window, so exactly one event falls outside Form.
        chat = _make_chat([self._event_on(day, [alice]) for day in range(1, FORM_EVENT_COUNT + 2)])

        result = compute_points(chat)
        (row,) = result.rows
        per_event = POINTS_ANSWERED + POINTS_BOOTED

        self.assertEqual(result.form_event_count, FORM_EVENT_COUNT)
        self.assertAlmostEqual(row.all_time, per_event * (FORM_EVENT_COUNT + 1))
        self.assertAlmostEqual(row.form, per_event * FORM_EVENT_COUNT)

    def test_ghosting_an_event_scores_nothing_for_it(self):
        alice = _make_user(1, "Alice")
        bob = _make_user(2, "Bob")
        chat = _make_chat([self._event_on(1, [alice, bob]), self._event_on(2, [alice])])

        result = compute_points(chat)
        rows = {row.user.id: row for row in result.rows}

        self.assertGreater(rows[1].all_time, rows[2].all_time)

    def test_scores_are_keyed_by_event_date(self):
        alice = _make_user(1, "Alice")

        result = compute_points(_make_chat([self._event_on(1, [alice])]))

        self.assertIn(date(2026, 1, 1), result.scores_by_date)
        self.assertIn(1, result.scores_by_date[date(2026, 1, 1)])


class FormatLeaderboardTest(unittest.TestCase):
    def _chat_with(self, user_count: int, events: int = 1):
        users = [_make_user(i, f"User{i}") for i in range(user_count)]
        return _make_chat(
            [
                _make_event(
                    date(2026, 1, day + 1),
                    num_slots=5,
                    poll_answers={user: _make_answer([0]) for user in users},
                )
                for day in range(events)
            ]
        )

    def test_no_events_reports_no_history(self):
        self.assertEqual(format_leaderboard(PointsResult()), "No event history yet for this chat\\!")

    def test_events_without_any_answers_report_no_participation(self):
        chat = _make_chat([_make_event(date(2026, 1, 1), num_slots=5, poll_answers={})])

        self.assertEqual(render_leaderboard_message(chat), "No participation data yet\\.")

    def test_table_has_a_header_and_one_row_per_user(self):
        text = render_leaderboard_message(self._chat_with(3))
        table = text.split("```")[1].strip().split("\n")

        self.assertIn("Form", table[0])
        self.assertIn("All", table[0])
        self.assertEqual(len(table), 4)  # header plus three users

    def test_table_is_truncated_to_the_row_cap(self):
        text = render_leaderboard_message(self._chat_with(MAX_LEADERBOARD_ROWS + 5))
        table = text.split("```")[1].strip().split("\n")

        self.assertEqual(len(table), MAX_LEADERBOARD_ROWS + 1)

    def test_rows_are_ordered_by_form_descending(self):
        keen = _make_user(1, "Keen")
        casual = _make_user(2, "Casual")
        chat = _make_chat(
            [
                _make_event(date(2026, 1, 1), 5, {keen: _make_answer([0]), casual: _make_answer([0])}),
                _make_event(date(2026, 1, 8), 5, {keen: _make_answer([0])}),
            ]
        )

        table = render_leaderboard_message(chat).split("```")[1].strip().split("\n")

        self.assertTrue(table[1].startswith("Keen"))
        self.assertTrue(table[2].startswith("Casual"))

    def test_footer_reports_the_form_window_and_is_escaped(self):
        text = render_leaderboard_message(self._chat_with(2, events=3))

        self.assertIn("Form covers the last 3 events\\.", text)


class FormatEventRecapTest(unittest.TestCase):
    def _chat_and_event(self, votes: int, num_slots: int = 5, first_answer=None):
        users = [_make_user(i, f"User{i}") for i in range(votes)]
        event = _make_event(
            date(2026, 1, 1),
            num_slots,
            {user: _make_answer([0]) for user in users},
            first_answer=first_answer,
        )
        return _make_chat([event]), event

    def test_headline_reports_quorum_met(self):
        chat, event = self._chat_and_event(QUORUM)

        text = render_event_recap_message(chat, event)

        self.assertIn("quorum met", text)
        self.assertIn("18\\.30", text)  # the winning slot time, MarkdownV2-escaped

    def test_headline_reports_quorum_missed(self):
        chat, event = self._chat_and_event(QUORUM - 1)

        text = render_event_recap_message(chat, event)

        self.assertIn("no game", text)
        self.assertIn(f"{QUORUM} needed", text)

    def test_headline_reports_nobody_picked_a_slot(self):
        user = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), 5, {user: _make_answer([5])})  # No-op only

        text = render_event_recap_message(_make_chat([event]), event)

        self.assertIn("Nobody picked a slot", text)

    def test_lists_scorers_with_reason_tags(self):
        chat, event = self._chat_and_event(QUORUM)

        text = render_event_recap_message(chat, event)
        scorers = text.split("```")[1]

        self.assertIn("rescue", scorers)
        self.assertEqual(len(scorers.strip().split("\n")), QUORUM)

    def test_form_table_is_truncated_to_the_recap_cap(self):
        chat, event = self._chat_and_event(MAX_RECAP_ROWS + 3)

        text = render_event_recap_message(chat, event)
        form_table = text.split("```")[3]

        self.assertEqual(len(form_table.strip().split("\n")), MAX_RECAP_ROWS)
        self.assertTrue(form_table.strip().startswith("1."))

    def test_unknown_event_renders_nothing(self):
        chat, _event = self._chat_and_event(2)
        stranger = _make_event(date(2030, 5, 5), 5, {})

        self.assertEqual(format_event_recap(compute_points(chat), stranger), "")

    def test_cancelled_event_renders_nothing(self):
        user = _make_user(1, "Alice")
        event = _make_event(date(2026, 1, 1), 5, {user: _make_answer([0])}, cancelled=True)

        self.assertEqual(render_event_recap_message(_make_chat([event]), event), "")


if __name__ == "__main__":
    unittest.main()
