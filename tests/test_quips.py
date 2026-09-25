import unittest
from unittest.mock import AsyncMock

from ongabot import quips
from ongabot.quips import FALLBACK_QUIPS, MAX_QUIP_LENGTH, get_quip_pool, next_quip, refresh_quip_pool


class NextQuipTest(unittest.TestCase):
    """The quip is a one-off chat message, so it is picked at random on every vote rather
    than seeded on the voter - the same user toggling No-op on one poll must not get the
    same line back every time."""

    def setUp(self):
        quips._pool = []
        quips._last_quip = None

    def tearDown(self):
        quips._pool = []
        quips._last_quip = None

    def test_returns_a_quip_from_the_current_pool(self):
        quips._pool = ["a", "b", "c"]

        self.assertIn(next_quip(), ["a", "b", "c"])

    def test_returns_a_fallback_quip_before_the_first_refresh(self):
        self.assertIn(next_quip(), FALLBACK_QUIPS)

    def test_never_repeats_the_previous_quip(self):
        quips._pool = ["a", "b", "c"]

        picks = [next_quip() for _ in range(50)]

        for previous, current in zip(picks, picks[1:]):
            self.assertNotEqual(previous, current)

    def test_a_single_quip_pool_still_returns_that_quip(self):
        quips._pool = ["only"]

        self.assertEqual([next_quip(), next_quip()], ["only", "only"])


class QuipPoolTest(unittest.IsolatedAsyncioTestCase):
    """The pool is fetched dynamically from JokeAPI, not hard-coded - see refresh_quip_pool."""

    def setUp(self):
        quips._pool = []

    def tearDown(self):
        quips._pool = []

    def test_fallback_quips_fit_the_length_limit(self):
        for quip in FALLBACK_QUIPS:
            self.assertLessEqual(len(quip), MAX_QUIP_LENGTH, quip)

    async def test_refresh_drops_jokes_longer_than_the_limit(self):
        fits = ["a" * MAX_QUIP_LENGTH, "b" * MAX_QUIP_LENGTH, "c" * MAX_QUIP_LENGTH]
        too_long = "y" * (MAX_QUIP_LENGTH + 1)
        client = AsyncMock()
        client.fetch_jokes.return_value = fits + [too_long]

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), fits)

    async def test_refresh_tops_up_a_thin_pool_with_the_fallback_quips(self):
        client = AsyncMock()
        client.fetch_jokes.return_value = ["The one short joke.", "y" * (MAX_QUIP_LENGTH + 1)]

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["The one short joke."] + FALLBACK_QUIPS)

    async def test_refresh_keeps_the_existing_pool_when_every_joke_is_too_long(self):
        quips._pool = ["Previously fetched joke."]
        client = AsyncMock()
        client.fetch_jokes.return_value = ["y" * (MAX_QUIP_LENGTH + 1)]

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["Previously fetched joke."])

    def test_pool_falls_back_to_the_static_list_when_never_refreshed(self):
        self.assertEqual(get_quip_pool(), FALLBACK_QUIPS)

    async def test_refresh_replaces_the_pool_with_freshly_fetched_jokes(self):
        client = AsyncMock()
        client.fetch_jokes.return_value = ["Fresh joke one.", "Fresh joke two.", "Fresh joke three."]

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["Fresh joke one.", "Fresh joke two.", "Fresh joke three."])

    async def test_refresh_keeps_the_existing_pool_when_the_fetch_fails(self):
        quips._pool = ["Previously fetched joke."]
        client = AsyncMock()
        client.fetch_jokes.return_value = None

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["Previously fetched joke."])

    async def test_refresh_keeps_the_existing_pool_when_the_fetch_returns_nothing(self):
        quips._pool = ["Previously fetched joke."]
        client = AsyncMock()
        client.fetch_jokes.return_value = []

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["Previously fetched joke."])


if __name__ == "__main__":
    unittest.main()
