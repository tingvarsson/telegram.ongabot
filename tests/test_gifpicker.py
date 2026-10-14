"""Picking a GIF for a mood: phrase dealing, the search cache and the per-chat no-repeat."""

import importlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.gifs import moods, picker
from ongabot.gifs.client import Gif
from ongabot.gifs.moods import Mood

CHAT_ID = 42


def _gifs(*ids):
    return [Gif(gif_id, f"https://media.giphy.com/{gif_id}.mp4") for gif_id in ids]


def _client(results):
    client = MagicMock()
    client.search = AsyncMock(return_value=results)
    return client


class MoodPhrasesTest(unittest.TestCase):
    def test_every_mood_has_a_pool_of_distinct_phrases(self):
        for mood in Mood:
            with self.subTest(mood=mood):
                phrases = moods.PHRASES[mood]
                self.assertEqual(len(phrases), moods.PHRASES_PER_MOOD)
                self.assertEqual(len(set(phrases)), len(phrases))
                self.assertTrue(all(phrase and phrase == phrase.strip() for phrase in phrases))

    def test_phrases_are_dealt_without_repeats(self):
        # The decks live in the top-level quips module the bot's code shares (pythonpath is
        # ongabot/), so a test elsewhere may have dealt from this one already: start afresh.
        importlib.import_module("quips")._bags.pop(Mood.BAIL.value, None)  # pylint: disable=protected-access
        dealt = [moods.next_phrase(Mood.BAIL) for _ in range(moods.PHRASES_PER_MOOD)]
        self.assertCountEqual(dealt, moods.PHRASES[Mood.BAIL])


class PickGifTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        picker.reset()
        self.addCleanup(picker.reset)
        self.now = 1000.0
        clock = patch.object(picker, "_clock", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        phrase = patch.object(picker, "next_phrase", return_value="rage quit")
        self.next_phrase = phrase.start()
        self.addCleanup(phrase.stop)

    async def test_picks_one_of_the_results_for_a_dealt_phrase(self):
        client = _client(_gifs("a", "b", "c"))

        picked = await picker.pick_gif(CHAT_ID, Mood.BAIL, client)

        self.next_phrase.assert_called_once_with(Mood.BAIL)
        client.search.assert_awaited_once_with("rage quit")
        self.assertEqual(picked.phrase, "rage quit")
        self.assertIn(picked.gif.gif_id, {"a", "b", "c"})

    async def test_results_are_cached_per_phrase(self):
        client = _client(_gifs("a", "b", "c"))

        await picker.pick_gif(CHAT_ID, Mood.BAIL, client)
        self.now += picker.CACHE_TTL_SECONDS - 1
        await picker.pick_gif(CHAT_ID, Mood.BAIL, client)

        client.search.assert_awaited_once()

    async def test_the_cache_expires(self):
        client = _client(_gifs("a", "b", "c"))

        await picker.pick_gif(CHAT_ID, Mood.BAIL, client)
        self.now += picker.CACHE_TTL_SECONDS
        await picker.pick_gif(CHAT_ID, Mood.BAIL, client)

        self.assertEqual(client.search.await_count, 2)

    async def test_a_chat_is_not_sent_the_same_gif_twice(self):
        client = _client(_gifs("a", "b", "c"))

        picked = {(await picker.pick_gif(CHAT_ID, Mood.BAIL, client)).gif.gif_id for _ in range(3)}

        self.assertEqual(picked, {"a", "b", "c"})
        # Every result has been sent to this chat now, so there is nothing left to pick.
        self.assertIsNone(await picker.pick_gif(CHAT_ID, Mood.BAIL, client))

    async def test_no_repeat_is_per_chat(self):
        client = _client(_gifs("a"))

        self.assertEqual((await picker.pick_gif(CHAT_ID, Mood.BAIL, client)).gif.gif_id, "a")
        self.assertEqual((await picker.pick_gif(CHAT_ID + 1, Mood.BAIL, client)).gif.gif_id, "a")

    async def test_only_the_latest_gifs_are_remembered(self):
        ids = [str(i) for i in range(picker.RECENT_PER_CHAT + 1)]
        client = _client(_gifs(*ids))

        sent = [(await picker.pick_gif(CHAT_ID, Mood.BAIL, client)).gif.gif_id for _ in ids]
        self.assertCountEqual(sent, ids)

        # The first GIF sent has dropped out of the window, and is the only one left to pick.
        self.assertEqual((await picker.pick_gif(CHAT_ID, Mood.BAIL, client)).gif.gif_id, sent[0])

    async def test_no_results_is_none_and_cached(self):
        client = _client([])

        self.assertIsNone(await picker.pick_gif(CHAT_ID, Mood.BAIL, client))
        self.assertIsNone(await picker.pick_gif(CHAT_ID, Mood.BAIL, client))

        client.search.assert_awaited_once()

    async def test_a_failed_search_is_none_and_not_cached(self):
        client = _client(None)

        self.assertIsNone(await picker.pick_gif(CHAT_ID, Mood.BAIL, client))
        self.assertIsNone(await picker.pick_gif(CHAT_ID, Mood.BAIL, client))

        self.assertEqual(client.search.await_count, 2)

    async def test_uses_the_shared_client_by_default(self):
        client = _client(_gifs("a"))
        with patch.object(picker, "get_client", return_value=client):
            picked = await picker.pick_gif(CHAT_ID, Mood.POKE)
        self.assertEqual(picked.gif.gif_id, "a")
