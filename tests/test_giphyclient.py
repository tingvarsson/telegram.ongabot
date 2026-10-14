"""The thin Giphy search client: request shape, parsing and never raising."""

import json
import os
import unittest
from unittest.mock import patch

import httpx

from ongabot.gifs.client import BASE_URL, MAX_MP4_BYTES, Gif, GiphyClient

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as file:
        return json.load(file)


async def _search(client: GiphyClient, handler, query="rage quit"):
    """Run client.search against a mock transport answering with handler."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with patch.object(client, "_client", http):
            return await client.search(query)


class GiphySearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_results_skipping_missing_and_oversized_mp4s(self):
        results = await _search(
            GiphyClient("key"), lambda _request: httpx.Response(200, json=_fixture("giphy_search.json"))
        )

        self.assertEqual(
            results,
            [
                Gif("l0HlBO7eyXzSZkJri", "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.mp4"),
                Gif("3o7TKSjRrfIPjeiVyM", "https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.mp4"),
            ],
        )

    async def test_sends_query_key_rating_and_limit(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url).split("?")[0]
            seen["params"] = dict(request.url.params)
            return httpx.Response(200, json={"data": []})

        await _search(GiphyClient("secret"), handler, "abandon ship")

        self.assertEqual(seen["url"], f"{BASE_URL}/search")
        self.assertEqual(seen["params"]["q"], "abandon ship")
        self.assertEqual(seen["params"]["api_key"], "secret")
        self.assertEqual(seen["params"]["rating"], "pg-13")
        self.assertEqual(seen["params"]["limit"], "25")

    async def test_no_results_is_an_empty_list(self):
        self.assertEqual(await _search(GiphyClient("key"), lambda _r: httpx.Response(200, json={"data": []})), [])

    async def test_without_a_key_nothing_is_requested(self):
        def handler(_request):
            raise AssertionError("no request expected without an API key")

        self.assertIsNone(await _search(GiphyClient(None), handler))

    async def test_http_error_status_is_none(self):
        with self.assertLogs("ongabot.gifs.client", level="WARNING"):
            self.assertIsNone(await _search(GiphyClient("key"), lambda _r: httpx.Response(429, json={})))

    async def test_transport_failure_is_none(self):
        def handler(request):
            raise httpx.ConnectTimeout("too slow", request=request)

        with self.assertLogs("ongabot.gifs.client", level="WARNING"):
            self.assertIsNone(await _search(GiphyClient("key"), handler))

    async def test_malformed_json_is_none(self):
        with self.assertLogs("ongabot.gifs.client", level="WARNING"):
            self.assertIsNone(await _search(GiphyClient("key"), lambda _r: httpx.Response(200, text="not json")))

    async def test_unexpected_shape_is_none(self):
        with self.assertLogs("ongabot.gifs.client", level="WARNING"):
            self.assertIsNone(await _search(GiphyClient("key"), lambda _r: httpx.Response(200, json={"data": "nope"})))

    async def test_unparseable_entries_are_skipped(self):
        payload = {"data": [{"id": "x"}, _fixture("giphy_search.json")["data"][0]]}
        results = await _search(GiphyClient("key"), lambda _r: httpx.Response(200, json=payload))
        self.assertEqual([gif.gif_id for gif in results], ["l0HlBO7eyXzSZkJri"])

    async def test_a_missing_size_is_kept(self):
        """Giphy usually sends mp4_size, but a GIF without one is not assumed to be too big."""
        entry = {"id": "nosize", "images": {"original": {"mp4": "https://media.giphy.com/nosize.mp4"}}}
        results = await _search(GiphyClient("key"), lambda _r: httpx.Response(200, json={"data": [entry]}))
        self.assertEqual(results, [Gif("nosize", "https://media.giphy.com/nosize.mp4")])

    def test_size_limit_is_telegrams_url_limit(self):
        self.assertEqual(MAX_MP4_BYTES, 20 * 1024 * 1024)

    async def test_aclose_releases_the_pool(self):
        client = GiphyClient("key")
        client._http()  # pylint: disable=protected-access
        await client.aclose()
        self.assertIsNone(client._client)  # pylint: disable=protected-access
