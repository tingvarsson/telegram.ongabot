import unittest
from itertools import product
from unittest.mock import patch

from ongabot import quips
from ongabot.quips import (
    BANTER_BY_PATH,
    MAX_LINE_LENGTH,
    POOL_SIZE,
    POOLS,
    Answer,
    Banter,
    build_retraction_reply,
    build_vote_reply,
    categorize,
    next_banter,
)

# 5 time slots, so option 5 is No-op and option 6 is Maybe Baby.
NUM_SLOTS = 5
NO_OP = 5
MAYBE = 6


class CategorizeTest(unittest.TestCase):
    def test_a_slot_is_game(self):
        self.assertIs(categorize((0,), NUM_SLOTS), Answer.GAME)

    def test_a_slot_plus_maybe_is_still_game(self):
        self.assertIs(categorize((2, MAYBE), NUM_SLOTS), Answer.GAME)

    def test_a_slot_plus_no_op_is_still_game(self):
        self.assertIs(categorize((4, NO_OP), NUM_SLOTS), Answer.GAME)

    def test_maybe_alone_is_maybe(self):
        self.assertIs(categorize((MAYBE,), NUM_SLOTS), Answer.MAYBE)

    def test_no_op_plus_maybe_is_maybe(self):
        self.assertIs(categorize((NO_OP, MAYBE), NUM_SLOTS), Answer.MAYBE)

    def test_no_op_alone_is_no_op(self):
        self.assertIs(categorize((NO_OP,), NUM_SLOTS), Answer.NO_OP)

    def test_respects_the_events_own_slot_count(self):
        # With 3 slots, option 3 is No-op and option 4 is Maybe Baby.
        self.assertIs(categorize((3,), 3), Answer.NO_OP)
        self.assertIs(categorize((4,), 3), Answer.MAYBE)


class PoolsTest(unittest.TestCase):
    """The banter is hand-written per path, so guard the shape of the data."""

    def test_every_banter_kind_has_a_pool(self):
        self.assertEqual(set(POOLS), set(Banter))

    def test_every_pool_has_the_full_set_of_unique_lines(self):
        for kind, lines in POOLS.items():
            with self.subTest(kind=kind):
                self.assertEqual(len(lines), POOL_SIZE)
                self.assertEqual(len(set(lines)), POOL_SIZE, "duplicate line in pool")

    def test_every_line_fits_the_length_limit(self):
        for kind, lines in POOLS.items():
            for line in lines:
                with self.subTest(kind=kind, line=line):
                    self.assertLessEqual(len(line), MAX_LINE_LENGTH)

    def test_no_line_is_shared_between_pools(self):
        all_lines = [line for lines in POOLS.values() for line in lines]
        self.assertEqual(len(all_lines), len(set(all_lines)))

    def test_lines_are_single_line_and_trimmed(self):
        for lines in POOLS.values():
            for line in lines:
                with self.subTest(line=line):
                    self.assertNotIn("\n", line)
                    self.assertEqual(line, line.strip())


class BanterByPathTest(unittest.TestCase):
    def test_every_banter_kind_is_reachable_from_exactly_one_path(self):
        self.assertCountEqual(BANTER_BY_PATH.values(), list(Banter))

    def test_covers_every_path_that_gets_banter(self):
        # First answers (None -> x) and retractions (x -> None) get banter except a first game
        # vote; changes get banter only when the category actually changes.
        expected = {(None, Answer.MAYBE), (None, Answer.NO_OP)}
        expected |= {(previous, None) for previous in Answer}
        expected |= {(previous, new) for previous, new in product(Answer, Answer) if previous is not new}
        self.assertEqual(set(BANTER_BY_PATH), expected)


class NextBanterTest(unittest.TestCase):
    """Lines are dealt from a shuffled deck, so a whole pool is used before anything repeats."""

    def setUp(self):
        quips._bags.clear()
        quips._last.clear()

    def tearDown(self):
        quips._bags.clear()
        quips._last.clear()

    def test_deals_every_line_once_before_repeating(self):
        dealt = [next_banter(Banter.FIRST_NO_OP) for _ in range(POOL_SIZE)]

        self.assertCountEqual(dealt, POOLS[Banter.FIRST_NO_OP])

    def test_never_repeats_back_to_back_across_reshuffles(self):
        dealt = [next_banter(Banter.GAME_TO_NO_OP) for _ in range(POOL_SIZE * 20)]

        for previous, current in zip(dealt, dealt[1:]):
            self.assertNotEqual(previous, current)

    def test_pools_are_dealt_independently(self):
        next_banter(Banter.FIRST_MAYBE)

        self.assertNotIn(Banter.FIRST_NO_OP, quips._bags)


class BuildVoteReplyTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("ongabot.quips.next_banter", side_effect=lambda kind: f"<{kind.name}>")
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_first_game_vote_keeps_the_classic_praise(self):
        self.assertEqual(
            build_vote_reply("Alice", None, Answer.GAME), "Wow Alice, what a great job answering that poll!"
        )

    def test_first_maybe_vote(self):
        self.assertEqual(build_vote_reply("Alice", None, Answer.MAYBE), "Alice votes Maybe — <FIRST_MAYBE>")

    def test_first_no_op_vote(self):
        self.assertEqual(build_vote_reply("Alice", None, Answer.NO_OP), "Alice votes No-op — <FIRST_NO_OP>")

    def test_same_category_change_keeps_the_suspicious_line(self):
        for answer in Answer:
            with self.subTest(answer=answer):
                self.assertEqual(
                    build_vote_reply("Alice", answer, answer),
                    "Hmm suspicious, looks like Alice changed their vote...",
                )

    def test_every_change_names_both_ends_and_uses_its_own_pool(self):
        expected = {
            (Answer.GAME, Answer.MAYBE): "Alice went from game to Maybe — <GAME_TO_MAYBE>",
            (Answer.GAME, Answer.NO_OP): "Alice went from game to No-op — <GAME_TO_NO_OP>",
            (Answer.MAYBE, Answer.NO_OP): "Alice went from Maybe to No-op — <MAYBE_TO_NO_OP>",
            (Answer.NO_OP, Answer.MAYBE): "Alice went from No-op to Maybe — <NO_OP_TO_MAYBE>",
            (Answer.MAYBE, Answer.GAME): "Alice went from Maybe to game — <MAYBE_TO_GAME>",
            (Answer.NO_OP, Answer.GAME): "Alice went from No-op to game — <NO_OP_TO_GAME>",
        }
        for (previous, new), reply in expected.items():
            with self.subTest(previous=previous, new=new):
                self.assertEqual(build_vote_reply("Alice", previous, new), reply)


class BuildRetractionReplyTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("ongabot.quips.next_banter", side_effect=lambda kind: f"<{kind.name}>")
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_each_retracted_answer_uses_its_own_pool(self):
        expected = {
            Answer.GAME: "Alice pulled their game vote — <RETRACTED_GAME>",
            Answer.MAYBE: "Alice pulled their Maybe vote — <RETRACTED_MAYBE>",
            Answer.NO_OP: "Alice pulled their No-op vote — <RETRACTED_NO_OP>",
        }
        for previous, reply in expected.items():
            with self.subTest(previous=previous):
                self.assertEqual(build_retraction_reply("Alice", previous), reply)


if __name__ == "__main__":
    unittest.main()
