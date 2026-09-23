import unittest

from ongabot.quips import select_quip


class SelectQuipTest(unittest.TestCase):
    def test_returns_a_quip_from_the_given_list(self):
        quips = ["a", "b", "c"]

        result = select_quip(quips, poll_id="p1", user_id=42, option_index=1)

        self.assertIn(result, quips)

    def test_same_inputs_return_the_same_quip(self):
        quips = ["a", "b", "c", "d", "e", "f", "g", "h"]

        first = select_quip(quips, poll_id="p1", user_id=42, option_index=1)
        second = select_quip(quips, poll_id="p1", user_id=42, option_index=1)

        self.assertEqual(first, second)

    def test_different_users_can_get_different_quips(self):
        quips = [str(i) for i in range(50)]

        results = {select_quip(quips, poll_id="p1", user_id=user_id, option_index=1) for user_id in range(20)}

        self.assertGreater(len(results), 1)

    def test_different_option_index_can_get_different_quip_for_same_user(self):
        quips = [str(i) for i in range(50)]

        no_op = select_quip(quips, poll_id="p1", user_id=42, option_index=1)
        maybe_baby = select_quip(quips, poll_id="p1", user_id=42, option_index=2)

        self.assertNotEqual(no_op, maybe_baby)


if __name__ == "__main__":
    unittest.main()
