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


if __name__ == "__main__":
    unittest.main()
