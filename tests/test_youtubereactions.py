import unittest

from telegram import ReactionTypeCustomEmoji, ReactionTypeEmoji
from telegram.constants import ReactionEmoji

from ongabot.youtube.reactions import reaction_score_delta
from ongabot.youtube.topics import REACTION_STEP


def _emoji(emoji: str) -> ReactionTypeEmoji:
    return ReactionTypeEmoji(emoji=emoji)


THUMBS_UP = _emoji(ReactionEmoji.THUMBS_UP)
THUMBS_DOWN = _emoji(ReactionEmoji.THUMBS_DOWN)
RED_HEART = _emoji(ReactionEmoji.RED_HEART)
FIRE = _emoji(ReactionEmoji.FIRE)
PILE_OF_POO = _emoji(ReactionEmoji.PILE_OF_POO)


class ReactionScoreDeltaTest(unittest.TestCase):
    def test_adding_a_positive_reaction_gives_a_positive_delta(self):
        self.assertEqual(reaction_score_delta((), (THUMBS_UP,)), REACTION_STEP)

    def test_adding_a_negative_reaction_gives_a_negative_delta(self):
        self.assertEqual(reaction_score_delta((), (THUMBS_DOWN,)), -REACTION_STEP)

    def test_removing_a_positive_reaction_undoes_its_earlier_boost(self):
        self.assertEqual(reaction_score_delta((THUMBS_UP,), ()), -REACTION_STEP)

    def test_removing_a_negative_reaction_undoes_its_earlier_penalty(self):
        self.assertEqual(reaction_score_delta((THUMBS_DOWN,), ()), REACTION_STEP)

    def test_swapping_positive_for_negative_nets_two_steps_down(self):
        self.assertEqual(reaction_score_delta((THUMBS_UP,), (THUMBS_DOWN,)), -2 * REACTION_STEP)

    def test_unmapped_emoji_contributes_nothing(self):
        clown = _emoji("\U0001f921")  # clown face - not in either sentiment bucket
        self.assertEqual(reaction_score_delta((), (clown,)), 0.0)

    def test_unchanged_reactions_contribute_nothing(self):
        self.assertEqual(reaction_score_delta((THUMBS_UP,), (THUMBS_UP,)), 0.0)

    def test_multiple_positive_emoji_added_at_once_stack(self):
        self.assertEqual(reaction_score_delta((), (RED_HEART, FIRE)), 2 * REACTION_STEP)

    def test_custom_emoji_reactions_are_ignored_not_crashing(self):
        custom = ReactionTypeCustomEmoji(custom_emoji_id="12345")
        self.assertEqual(reaction_score_delta((), (custom,)), 0.0)

    def test_poo_is_negative(self):
        self.assertEqual(reaction_score_delta((), (PILE_OF_POO,)), -REACTION_STEP)


if __name__ == "__main__":
    unittest.main()
