import unittest
from itertools import product
from unittest.mock import patch

from ongabot import quips
from ongabot.quips import (
    BANTER_BY_PATH,
    HEADLINES,
    HEADLINES_PER_PATH,
    MAX_HEADLINE_LENGTH,
    MAX_LINE_LENGTH,
    POOL_SIZE,
    POOLS,
    Answer,
    Banter,
    build_retraction_reply,
    build_vote_reply,
    categorize,
    next_banter,
    next_headline,
    slot_count,
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


class SlotCountTest(unittest.TestCase):
    def test_counts_only_time_slots(self):
        self.assertEqual(slot_count((0, 2, NO_OP, MAYBE), NUM_SLOTS), 2)

    def test_every_slot(self):
        self.assertEqual(slot_count(range(NUM_SLOTS), NUM_SLOTS), NUM_SLOTS)

    def test_no_slot(self):
        self.assertEqual(slot_count((NO_OP,), NUM_SLOTS), 0)


class HeadlinesTest(unittest.TestCase):
    """The headlines are hand-written per path, so guard the shape of the data."""

    def test_every_banter_path_has_its_headlines(self):
        self.assertEqual(set(HEADLINES), set(BANTER_BY_PATH))

    def test_every_path_has_the_full_set_of_unique_headlines(self):
        for path, templates in HEADLINES.items():
            with self.subTest(path=path):
                self.assertEqual(len(templates), HEADLINES_PER_PATH)
                self.assertEqual(len(set(templates)), HEADLINES_PER_PATH, "duplicate headline")

    def test_every_headline_names_the_voter_and_both_ends(self):
        # The reply has always said what was answered or switched, from what to what.
        for (previous, new), templates in HEADLINES.items():
            for template in templates:
                with self.subTest(template=template):
                    self.assertIn("{name}", template)
                    self.assertEqual("{previous}" in template, previous is not None)
                    self.assertEqual("{new}" in template, new is not None)

    def test_every_headline_fits_the_length_limit(self):
        for (previous, new), templates in HEADLINES.items():
            for template in templates:
                headline = template.format(
                    name="", previous=previous.value if previous else "", new=new.value if new else ""
                )
                with self.subTest(template=template):
                    self.assertLessEqual(len(headline), MAX_HEADLINE_LENGTH)

    def test_next_headline_rotates_without_back_to_back_repeats(self):
        quips._bags.clear()
        quips._last.clear()
        self.addCleanup(quips._bags.clear)
        self.addCleanup(quips._last.clear)
        path = (Answer.GAME, Answer.NO_OP)
        dealt = [next_headline(path) for _ in range(HEADLINES_PER_PATH * 10)]

        self.assertCountEqual(dealt[:HEADLINES_PER_PATH], HEADLINES[path])
        for previous, current in zip(dealt, dealt[1:]):
            self.assertNotEqual(previous, current)


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
        # UNVERIFIED is picked by who votes, and ALL_SLOTS/SOME_SLOTS by how many slots, not by
        # the path, see build_vote_reply. POKE is the morning poke, not a vote reply at all.
        off_path = (Banter.UNVERIFIED, Banter.POKE, Banter.ALL_SLOTS, Banter.SOME_SLOTS)
        path_kinds = [kind for kind in Banter if kind not in off_path]
        self.assertCountEqual(BANTER_BY_PATH.values(), path_kinds)

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


def _patch_randomness(test: unittest.TestCase) -> None:
    """Swap the random banter for its pool name and the random headline for a template that
    shows what it was filled in with, so a reply shows exactly where each part came from."""
    for target, fake in (
        ("ongabot.quips.next_banter", lambda kind: f"<{kind.name}>"),
        ("ongabot.quips.next_headline", lambda path: "<{name}|{previous}|{new}>"),
    ):
        patcher = patch(target, side_effect=fake)
        test.addCleanup(patcher.stop)
        patcher.start()


class BuildVoteReplyTest(unittest.TestCase):
    def setUp(self):
        _patch_randomness(self)

    def test_first_vote_for_every_slot_is_praised(self):
        self.assertEqual(
            build_vote_reply("Alice", None, Answer.GAME, slots=5, num_slots=5),
            "👑 Alice votes ALL 5 slots!\n— <ALL_SLOTS>",
        )

    def test_first_vote_for_some_slots_is_shamed(self):
        self.assertEqual(
            build_vote_reply("Alice", None, Answer.GAME, slots=2, num_slots=5),
            "🤨 Alice votes 2 of 5 slots\n— <SOME_SLOTS>",
        )

    def test_first_game_vote_on_a_single_slot_poll_gets_the_classic_praise(self):
        self.assertEqual(
            build_vote_reply("Alice", None, Answer.GAME, slots=1, num_slots=1),
            "🎉 Wow Alice, what a great job answering that poll!",
        )

    def test_first_game_vote_without_slot_counts_gets_the_classic_praise(self):
        self.assertEqual(
            build_vote_reply("Alice", None, Answer.GAME), "🎉 Wow Alice, what a great job answering that poll!"
        )

    def test_first_maybe_vote(self):
        self.assertEqual(build_vote_reply("Alice", None, Answer.MAYBE), "<Alice||Maybe>\n— <FIRST_MAYBE>")

    def test_first_no_op_vote(self):
        self.assertEqual(build_vote_reply("Alice", None, Answer.NO_OP), "<Alice||No-op>\n— <FIRST_NO_OP>")

    def test_same_category_change_gets_the_suspicious_line(self):
        for answer in Answer:
            with self.subTest(answer=answer):
                self.assertEqual(
                    build_vote_reply("Alice", answer, answer, slots=2, previous_slots=3, num_slots=5),
                    "🕵️ Hmm, suspicious... Alice changed their vote",
                )

    def test_moving_up_to_every_slot_is_praised(self):
        self.assertEqual(
            build_vote_reply("Alice", Answer.GAME, Answer.GAME, slots=5, previous_slots=2, num_slots=5),
            "👑 Alice went from 2 to ALL 5 slots!\n— <ALL_SLOTS>",
        )

    def test_dropping_from_every_slot_is_shamed(self):
        self.assertEqual(
            build_vote_reply("Alice", Answer.GAME, Answer.GAME, slots=3, previous_slots=5, num_slots=5),
            "📉 Alice went from all 5 to 3 of 5 slots\n— <SOME_SLOTS>",
        )

    def test_every_change_names_both_ends_and_uses_its_own_pool(self):
        expected = {
            (Answer.GAME, Answer.MAYBE): "<Alice|game|Maybe>\n— <GAME_TO_MAYBE>",
            (Answer.GAME, Answer.NO_OP): "<Alice|game|No-op>\n— <GAME_TO_NO_OP>",
            (Answer.MAYBE, Answer.NO_OP): "<Alice|Maybe|No-op>\n— <MAYBE_TO_NO_OP>",
            (Answer.NO_OP, Answer.MAYBE): "<Alice|No-op|Maybe>\n— <NO_OP_TO_MAYBE>",
            (Answer.MAYBE, Answer.GAME): "<Alice|Maybe|game>\n— <MAYBE_TO_GAME>",
            (Answer.NO_OP, Answer.GAME): "<Alice|No-op|game>\n— <NO_OP_TO_GAME>",
        }
        for (previous, new), reply in expected.items():
            with self.subTest(previous=previous, new=new):
                self.assertEqual(build_vote_reply("Alice", previous, new), reply)

    def test_switching_to_some_slots_adds_the_shame(self):
        self.assertEqual(
            build_vote_reply("Alice", Answer.MAYBE, Answer.GAME, slots=1, num_slots=5),
            "<Alice|Maybe|game>\n— <MAYBE_TO_GAME>\n🤨 Only 1 of 5 slots though — <SOME_SLOTS>",
        )

    def test_switching_to_every_slot_adds_the_praise(self):
        self.assertEqual(
            build_vote_reply("Alice", Answer.NO_OP, Answer.GAME, slots=5, num_slots=5),
            "<Alice|No-op|game>\n— <NO_OP_TO_GAME>\n👑 ALL 5 slots, too — <ALL_SLOTS>",
        )

    def test_switching_to_game_on_a_single_slot_poll_has_no_verdict(self):
        self.assertEqual(
            build_vote_reply("Alice", Answer.NO_OP, Answer.GAME, slots=1, num_slots=1),
            "<Alice|No-op|game>\n— <NO_OP_TO_GAME>",
        )

    def test_unverified_voter_is_roasted_on_every_path(self):
        # Even the paths that normally keep a fixed line get the UNVERIFIED pool, and the slot
        # verdict is left out so the roast stays the point.
        expected = {
            (None, Answer.GAME): "Will votes game — <UNVERIFIED>",
            (None, Answer.NO_OP): "Will votes No-op — <UNVERIFIED>",
            (Answer.GAME, Answer.GAME): "Will changed their vote — <UNVERIFIED>",
            (Answer.GAME, Answer.MAYBE): "Will went from game to Maybe — <UNVERIFIED>",
            (Answer.MAYBE, Answer.GAME): "Will went from Maybe to game — <UNVERIFIED>",
        }
        for (previous, new), reply in expected.items():
            with self.subTest(previous=previous, new=new):
                self.assertEqual(
                    build_vote_reply("Will", previous, new, unverified=True, slots=5, previous_slots=2, num_slots=5),
                    reply,
                )


class BuildRetractionReplyTest(unittest.TestCase):
    def setUp(self):
        _patch_randomness(self)

    def test_each_retracted_answer_uses_its_own_pool(self):
        expected = {
            Answer.GAME: "<Alice|game|>\n— <RETRACTED_GAME>",
            Answer.MAYBE: "<Alice|Maybe|>\n— <RETRACTED_MAYBE>",
            Answer.NO_OP: "<Alice|No-op|>\n— <RETRACTED_NO_OP>",
        }
        for previous, reply in expected.items():
            with self.subTest(previous=previous):
                self.assertEqual(build_retraction_reply("Alice", previous), reply)

    def test_unverified_retraction_is_roasted(self):
        self.assertEqual(
            build_retraction_reply("Will", Answer.GAME, unverified=True), "Will pulled their game vote — <UNVERIFIED>"
        )


if __name__ == "__main__":
    unittest.main()
