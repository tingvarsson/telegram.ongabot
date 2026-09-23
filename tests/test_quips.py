import unittest
from unittest.mock import AsyncMock

from ongabot import quips
from ongabot.quips import FALLBACK_QUIPS, get_quip_pool, refresh_quip_pool, select_quip


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


class QuipPoolTest(unittest.IsolatedAsyncioTestCase):
    """The pool is fetched dynamically from JokeAPI, not hard-coded - see refresh_quip_pool."""

    def setUp(self):
        quips._pool = []

    def tearDown(self):
        quips._pool = []

    def test_pool_falls_back_to_the_static_list_when_never_refreshed(self):
        self.assertEqual(get_quip_pool(), FALLBACK_QUIPS)

    async def test_refresh_replaces_the_pool_with_freshly_fetched_jokes(self):
        client = AsyncMock()
        client.fetch_jokes.return_value = ["Fresh joke one.", "Fresh joke two."]

        await refresh_quip_pool(client)

        self.assertEqual(get_quip_pool(), ["Fresh joke one.", "Fresh joke two."])

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
