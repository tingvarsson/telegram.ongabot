import unittest
from unittest.mock import AsyncMock, patch

import httpx

from ongabot.jokes import BASE_URL, JokeApiClient, get_client


def _response(status_code, json_data=None, text=None):
    """Build a real httpx.Response so status/JSON handling is exercised, not mocked away."""
    request = httpx.Request("GET", BASE_URL)
    if text is not None:
        return httpx.Response(status_code, text=text, request=request)
    return httpx.Response(status_code, json=json_data, request=request)


def _joke(text, safe=True):
    return {
        "category": "Misc",
        "type": "single",
        "joke": text,
        "flags": {"nsfw": False, "religious": False, "political": False, "racist": False, "sexist": False},
        "safe": safe,
        "lang": "en",
    }


class JokeApiParsesResponseTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_the_joke_texts(self):
        client = JokeApiClient()
        payload = {
            "error": False,
            "amount": 2,
            "jokes": [_joke("Why did the chicken cross the road?"), _joke("Never date a baker.")],
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            jokes = await client.fetch_jokes(amount=2)

        self.assertEqual(jokes, ["Why did the chicken cross the road?", "Never date a baker."])

    async def test_collapses_multiline_jokes_into_a_single_line(self):
        client = JokeApiClient()
        payload = {"error": False, "amount": 1, "jokes": [_joke("Setup line.\nPunchline here.")]}
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            jokes = await client.fetch_jokes(amount=1)

        self.assertEqual(jokes, ["Setup line. Punchline here."])

    async def test_filters_out_jokes_not_marked_safe(self):
        client = JokeApiClient()
        payload = {
            "error": False,
            "amount": 2,
            "jokes": [_joke("A safe one.", safe=True), _joke("An unsafe one.", safe=False)],
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            jokes = await client.fetch_jokes(amount=2)

        self.assertEqual(jokes, ["A safe one."])

    async def test_returns_none_when_the_api_reports_an_error(self):
        client = JokeApiClient()
        payload = {"error": True, "message": "No matching joke found"}
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            self.assertIsNone(await client.fetch_jokes(amount=2))

    async def test_returns_none_when_the_payload_has_no_jokes_field(self):
        client = JokeApiClient()
        with patch.object(client, "_get", AsyncMock(return_value={"error": False})):
            self.assertIsNone(await client.fetch_jokes(amount=2))


class JokeApiFailureIsolationTest(unittest.IsolatedAsyncioTestCase):
    """A JokeAPI outage must never raise into the refresh job - every failure returns None."""

    async def _fetch_through(self, handler):
        client = JokeApiClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                return await client.fetch_jokes(amount=2)

    async def test_server_error_returns_none(self):
        self.assertIsNone(await self._fetch_through(lambda request: _response(500, text="boom")))

    async def test_malformed_json_returns_none(self):
        self.assertIsNone(await self._fetch_through(lambda request: _response(200, text="not json{")))

    async def test_timeout_returns_none(self):
        def handler(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        self.assertIsNone(await self._fetch_through(handler))


class JokeApiLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_creates_one_shared_http_client_and_closes_it(self):
        client = JokeApiClient()

        first = client._http()  # pylint: disable=protected-access
        self.assertIs(client._http(), first)  # pylint: disable=protected-access

        await client.aclose()
        self.assertTrue(first.is_closed)

    async def test_aclose_is_harmless_when_nothing_was_opened(self):
        await JokeApiClient().aclose()


class GetClientTest(unittest.TestCase):
    def test_returns_the_same_instance_every_call(self):
        get_client.cache_clear()
        try:
            self.assertIs(get_client(), get_client())
        finally:
            get_client.cache_clear()


if __name__ == "__main__":
    unittest.main()
