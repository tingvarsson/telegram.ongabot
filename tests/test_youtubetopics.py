import random
import unittest

from ongabot.youtube.topics import (
    MAX_TOPICS_PER_VIDEO,
    MAX_TRACKED_TOPICS,
    MAX_SCORE,
    MIN_SCORE,
    NEUTRAL_SCORE,
    SEED_TOPICS,
    apply_reaction,
    choose_topic,
    decay_topic_scores,
    extract_topics,
    register_topics,
    seed_topic_scores,
)


class SeedTopicScoresTest(unittest.TestCase):
    def test_seeds_counter_strike_and_linux(self):
        scores = seed_topic_scores()

        self.assertEqual(set(scores), {"counter-strike", "linux"})
        self.assertTrue(all(v > NEUTRAL_SCORE for v in scores.values()))

    def test_returns_a_fresh_copy_each_call(self):
        first = seed_topic_scores()
        first["counter-strike"] = 999.0

        self.assertEqual(seed_topic_scores()["counter-strike"], SEED_TOPICS["counter-strike"])


class ExtractTopicsTest(unittest.TestCase):
    def test_tags_are_lowercased_and_deduplicated(self):
        topics = extract_topics("", ["Linux", "linux", "Gaming"])

        self.assertEqual(topics, ("linux", "gaming"))

    def test_title_is_tokenized_with_stopwords_removed(self):
        topics = extract_topics("The Best Linux Setup for Gaming", [])

        self.assertNotIn("the", topics)
        self.assertNotIn("for", topics)
        self.assertIn("linux", topics)
        self.assertIn("setup", topics)
        self.assertIn("gaming", topics)

    def test_short_tokens_and_numbers_are_dropped(self):
        topics = extract_topics("CS 2 pro ace 2026", [])

        self.assertNotIn("cs", topics)
        self.assertNotIn("2", topics)
        self.assertNotIn("2026", topics)
        self.assertIn("pro", topics)
        self.assertIn("ace", topics)

    def test_result_is_capped_at_max_topics_per_video(self):
        title = "alpha bravo charlie delta echo foxtrot golf hotel"

        topics = extract_topics(title, [])

        self.assertLessEqual(len(topics), MAX_TOPICS_PER_VIDEO)

    def test_tags_take_priority_over_title_tokens_when_capped(self):
        tags = ["alpha", "bravo", "charlie", "delta", "echo"]
        topics = extract_topics("foxtrot golf hotel", tags)

        self.assertEqual(set(topics), set(tags))


class ChooseTopicTest(unittest.TestCase):
    def test_raises_when_no_topics_tracked(self):
        with self.assertRaises(ValueError):
            choose_topic({})

    def test_returns_one_of_the_tracked_topics(self):
        scores = {"counter-strike": 3.0, "linux": 1.0}

        chosen = choose_topic(scores, rng=random.Random(1))

        self.assertIn(chosen, scores)

    def test_works_with_the_default_random_module_when_no_rng_given(self):
        scores = {"a": 5.0, "b": 5.0}

        results = {choose_topic(scores) for _ in range(50)}

        self.assertTrue(results.issubset({"a", "b"}))

    def test_higher_scored_topic_wins_more_often_over_many_trials(self):
        scores = {"favorite": 9.0, "neutral": 1.0}
        rng = random.Random(42)

        counts = {"favorite": 0, "neutral": 0}
        for _ in range(2000):
            counts[choose_topic(scores, rng=rng)] += 1

        self.assertGreater(counts["favorite"], counts["neutral"])

    def test_every_topic_is_reachable_even_the_low_scoring_one(self):
        scores = {"favorite": 9.0, "rarely_liked": MIN_SCORE}
        rng = random.Random(7)

        seen = {choose_topic(scores, rng=rng) for _ in range(500)}

        self.assertEqual(seen, {"favorite", "rarely_liked"})


class ApplyReactionTest(unittest.TestCase):
    def test_adds_delta_to_each_topic(self):
        scores = {"linux": 1.0}

        apply_reaction(scores, ["linux"], 0.5)

        self.assertEqual(scores["linux"], 1.5)

    def test_creates_a_neutral_baseline_for_an_untracked_topic(self):
        scores = {}

        apply_reaction(scores, ["speedrun"], 0.5)

        self.assertEqual(scores["speedrun"], NEUTRAL_SCORE + 0.5)

    def test_clamps_at_max_score(self):
        scores = {"linux": MAX_SCORE}

        apply_reaction(scores, ["linux"], 5.0)

        self.assertEqual(scores["linux"], MAX_SCORE)

    def test_clamps_at_min_score_so_nothing_is_permanently_killed(self):
        scores = {"linux": MIN_SCORE}

        apply_reaction(scores, ["linux"], -5.0)

        self.assertEqual(scores["linux"], MIN_SCORE)


class RegisterTopicsTest(unittest.TestCase):
    def test_adds_new_topics_at_neutral_score(self):
        scores = {}

        register_topics(scores, ["speedrun"])

        self.assertEqual(scores["speedrun"], NEUTRAL_SCORE)

    def test_does_not_overwrite_an_already_tracked_score(self):
        scores = {"linux": 4.0}

        register_topics(scores, ["linux"])

        self.assertEqual(scores["linux"], 4.0)


class DecayTopicScoresTest(unittest.TestCase):
    def test_pulls_scores_toward_neutral(self):
        scores = {"linux": MAX_SCORE}

        decay_topic_scores(scores)

        self.assertLess(scores["linux"], MAX_SCORE)
        self.assertGreater(scores["linux"], NEUTRAL_SCORE)

    def test_prunes_down_to_max_tracked_topics_keeping_seed_topics(self):
        scores = {f"topic{i}": NEUTRAL_SCORE + (i * 0.01) for i in range(MAX_TRACKED_TOPICS + 10)}
        scores.update(seed_topic_scores())

        decay_topic_scores(scores)

        self.assertLessEqual(len(scores), MAX_TRACKED_TOPICS)
        self.assertIn("counter-strike", scores)
        self.assertIn("linux", scores)

    def test_prunes_the_topics_closest_to_neutral_first(self):
        scores = {"barely_signal": NEUTRAL_SCORE + 0.0001, "strong_signal": NEUTRAL_SCORE + 5.0}
        scores.update({f"filler{i}": NEUTRAL_SCORE + 0.01 for i in range(MAX_TRACKED_TOPICS)})

        decay_topic_scores(scores)

        self.assertIn("strong_signal", scores)
        self.assertNotIn("barely_signal", scores)


if __name__ == "__main__":
    unittest.main()
