import unittest
from datetime import date

from ongabot.userdata import UserData


class UserDataCalculateStreakTest(unittest.TestCase):
    def setUp(self):
        self.ud = UserData()

    def test_empty_poll_id_to_date_returns_zero(self):
        self.assertEqual(self.ud.calculate_streak({}), 0)

    def test_no_votes_returns_zero(self):
        self.assertEqual(self.ud.calculate_streak({"p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}), 0)

    def test_single_event_voted_returns_one(self):
        self.ud.set_poll_answer("p1", (0,))
        self.assertEqual(self.ud.calculate_streak({"p1": date(2026, 1, 1)}), 1)

    def test_single_event_not_voted_returns_zero(self):
        self.assertEqual(self.ud.calculate_streak({"p1": date(2026, 1, 1)}), 0)

    def test_voted_all_events_returns_full_count(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (1,))
        self.ud.set_poll_answer("p3", (2,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8), "p3": date(2026, 1, 15)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 3)

    def test_voted_recent_two_not_oldest(self):
        self.ud.set_poll_answer("p2", (0,))
        self.ud.set_poll_answer("p3", (0,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8), "p3": date(2026, 1, 15)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 2)

    def test_gap_at_most_recent_returns_zero(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (0,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8), "p3": date(2026, 1, 15)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 0)

    def test_gap_in_middle_counts_only_from_most_recent(self):
        # voted D1, D2, D4 — missed D3 — streak is 1 (only D4)
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (0,))
        self.ud.set_poll_answer("p4", (0,))
        poll_id_to_date = {
            "p1": date(2026, 1, 1),
            "p2": date(2026, 1, 8),
            "p3": date(2026, 1, 15),
            "p4": date(2026, 1, 22),
        }
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 1)

    def test_retraction_stored_as_empty_tuple_does_not_count(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", ())  # retraction
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 0)

    def test_unsorted_input_gives_correct_result(self):
        self.ud.set_poll_answer("p3", (0,))
        self.ud.set_poll_answer("p2", (0,))
        # p1 not voted — streak from most recent is p3, p2 → 2, stops at p1
        poll_id_to_date = {"p3": date(2026, 1, 15), "p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 2)

    def test_absent_poll_id_does_not_break_streak(self):
        # Simulates a cancelled event being excluded from poll_id_to_date at the call site.
        # p2 (cancelled) is absent; streak across p1 and p3 should be 2.
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p3", (0,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p3": date(2026, 1, 15)}
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 2)


class UserDataCalculatePlayedStreakTest(unittest.TestCase):
    """Played streak counts only events where the user picked an actual time slot.

    Slot options are always poll options 0..num_slots-1; No-op and Maybe Baby </3 are
    appended after them (see eventcreator._create_poll_options), so option ids >= num_slots
    are non-slot answers that respond to the poll without playing.
    """

    def setUp(self):
        self.ud = UserData()

    def test_empty_poll_id_to_date_returns_zero(self):
        self.assertEqual(self.ud.calculate_played_streak({}, {}), 0)

    def test_single_event_slot_picked_returns_one(self):
        self.ud.set_poll_answer("p1", (0,))
        self.assertEqual(self.ud.calculate_played_streak({"p1": date(2026, 1, 1)}, {"p1": 5}), 1)

    def test_no_op_only_answer_does_not_count_as_played(self):
        # 5 slots means option ids 0-4 are slots, 5 is No-op
        self.ud.set_poll_answer("p1", (5,))
        self.assertEqual(self.ud.calculate_played_streak({"p1": date(2026, 1, 1)}, {"p1": 5}), 0)

    def test_maybe_only_answer_does_not_count_as_played(self):
        # 5 slots means option id 6 is Maybe Baby </3
        self.ud.set_poll_answer("p1", (6,))
        self.assertEqual(self.ud.calculate_played_streak({"p1": date(2026, 1, 1)}, {"p1": 5}), 0)

    def test_slot_plus_no_op_answer_counts_as_played(self):
        self.ud.set_poll_answer("p1", (2, 5))
        self.assertEqual(self.ud.calculate_played_streak({"p1": date(2026, 1, 1)}, {"p1": 5}), 1)

    def test_played_all_events_returns_full_count(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (1,))
        self.ud.set_poll_answer("p3", (2,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8), "p3": date(2026, 1, 15)}
        num_slots = {"p1": 5, "p2": 5, "p3": 5}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, num_slots), 3)

    def test_no_op_at_most_recent_breaks_streak_but_not_response_streak(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (5,))  # No-op: responded, did not play
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        num_slots = {"p1": 5, "p2": 5}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, num_slots), 0)
        self.assertEqual(self.ud.calculate_streak(poll_id_to_date), 2)

    def test_no_op_in_middle_counts_only_from_most_recent(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", (5,))  # No-op
        self.ud.set_poll_answer("p3", (0,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8), "p3": date(2026, 1, 15)}
        num_slots = {"p1": 5, "p2": 5, "p3": 5}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, num_slots), 1)

    def test_retraction_stored_as_empty_tuple_does_not_count(self):
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p2", ())  # retraction
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, {"p1": 5, "p2": 5}), 0)

    def test_unsorted_input_gives_correct_result(self):
        self.ud.set_poll_answer("p3", (0,))
        self.ud.set_poll_answer("p2", (0,))
        poll_id_to_date = {"p3": date(2026, 1, 15), "p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        num_slots = {"p1": 5, "p2": 5, "p3": 5}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, num_slots), 2)

    def test_absent_poll_id_does_not_break_streak(self):
        # Simulates a cancelled event being excluded from poll_id_to_date at the call site.
        self.ud.set_poll_answer("p1", (0,))
        self.ud.set_poll_answer("p3", (0,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p3": date(2026, 1, 15)}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, {"p1": 5, "p3": 5}), 2)

    def test_poll_id_missing_from_num_slots_breaks_streak(self):
        # Defensive: without slot info nothing can be confirmed as a slot pick.
        self.ud.set_poll_answer("p1", (0,))
        self.assertEqual(self.ud.calculate_played_streak({"p1": date(2026, 1, 1)}, {}), 0)

    def test_varying_num_slots_per_event(self):
        # p1 had 3 slots (option 3 is No-op), p2 had 5 (option 3 is a slot)
        self.ud.set_poll_answer("p1", (3,))
        self.ud.set_poll_answer("p2", (3,))
        poll_id_to_date = {"p1": date(2026, 1, 1), "p2": date(2026, 1, 8)}
        self.assertEqual(self.ud.calculate_played_streak(poll_id_to_date, {"p1": 3, "p2": 5}), 1)


if __name__ == "__main__":
    unittest.main()
