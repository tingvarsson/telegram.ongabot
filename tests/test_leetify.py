import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from ongabot.cs2.leetify import BASE_URL, LeetifyClient

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as file:
        return json.load(file)


def _response(status_code, json_data=None, text=None):
    """Build a real httpx.Response so status/JSON handling is exercised, not mocked away."""
    request = httpx.Request("GET", BASE_URL)
    if text is not None:
        return httpx.Response(status_code, text=text, request=request)
    return httpx.Response(status_code, json=json_data, request=request)


class LeetifyMatchHistoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_match_summaries_from_history(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value=_fixture("leetify_match_history.json"))):
            matches = await client.get_match_history("76561198034202275")

        self.assertEqual(len(matches), 3)
        first = matches[0]
        self.assertEqual(first.id, "2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b")
        self.assertEqual(first.finished_at, "2026-08-30T19:02:30.000Z")
        self.assertEqual(first.data_source, "matchmaking_competitive")
        self.assertEqual(first.map_name, "de_cache")

    async def test_returns_none_when_player_has_no_leetify_account(self):
        client = LeetifyClient()
        transport = httpx.MockTransport(lambda request: _response(404, text="Not Found"))
        async with httpx.AsyncClient(transport=transport) as http:
            with patch.object(client, "_client", http):
                self.assertIsNone(await client.get_match_history("76561198000000000"))


class LeetifyMatchDetailTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_all_ten_players_from_match_detail(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value=_fixture("leetify_match_detail.json"))):
            match = await client.get_match("2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b")

        self.assertEqual(match.map_name, "de_cache")
        self.assertEqual(len(match.players), 10)
        scout = next(p for p in match.players if p.steam64_id == "76561198034202275")
        self.assertEqual(scout.name, "Akkaman")
        self.assertEqual(scout.total_kills, 23)
        self.assertEqual(scout.total_deaths, 15)
        self.assertEqual(scout.kd_ratio, 1.53)
        self.assertEqual(scout.mvps, 2)
        self.assertEqual(scout.initial_team_number, 2)

    async def test_parses_team_scores(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value=_fixture("leetify_match_detail.json"))):
            match = await client.get_match("2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b")

        self.assertEqual(match.team_scores, {2: 2, 3: 13})


class LeetifyFailureIsolationTest(unittest.IsolatedAsyncioTestCase):
    """A Leetify outage must never raise into a job or handler - every failure returns None."""

    async def _get_history_through(self, handler):
        client = LeetifyClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                return await client.get_match_history("76561198034202275")

    async def test_server_error_returns_none(self):
        self.assertIsNone(await self._get_history_through(lambda request: _response(500, text="boom")))

    async def test_malformed_json_returns_none(self):
        self.assertIsNone(await self._get_history_through(lambda request: _response(200, text="not json{")))

    async def test_unexpected_payload_shape_returns_none(self):
        self.assertIsNone(await self._get_history_through(lambda request: _response(200, json_data={"oops": True})))

    async def test_timeout_returns_none(self):
        def handler(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        self.assertIsNone(await self._get_history_through(handler))

    async def test_connection_error_returns_none(self):
        def handler(request):
            raise httpx.ConnectError("unreachable", request=request)

        self.assertIsNone(await self._get_history_through(handler))


class LeetifyRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_api_key_as_bearer_token_when_configured(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("authorization")
            seen["url"] = str(request.url)
            return _response(200, json_data=[])

        client = LeetifyClient(api_key="secret-key")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                await client.get_match_history("76561198034202275")

        self.assertEqual(seen["auth"], "Bearer secret-key")
        self.assertIn("steam64_id=76561198034202275", seen["url"])

    async def test_sends_no_authorization_header_without_api_key(self):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("authorization")
            return _response(200, json_data=[])

        client = LeetifyClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                await client.get_match_history("76561198034202275")

        self.assertIsNone(seen["auth"])


class LeetifySchemaDriftTest(unittest.IsolatedAsyncioTestCase):
    """Leetify can add or rename fields; a surprise must degrade to None, not crash a job."""

    async def test_history_entry_missing_a_required_field_returns_none(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value=[{"id": "m1", "map_name": "de_dust2"}])):
            self.assertIsNone(await client.get_match_history("76561198034202275"))

    async def test_match_detail_missing_a_required_field_returns_none(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value={"map_name": "de_dust2"})):
            self.assertIsNone(await client.get_match("m1"))

    async def test_match_detail_with_a_non_numeric_score_returns_none(self):
        client = LeetifyClient()
        payload = {
            "id": "m1",
            "finished_at": "2026-09-02T19:00:00.000Z",
            "team_scores": [{"team_number": 2, "score": "many"}],
            "stats": [],
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            self.assertIsNone(await client.get_match("m1"))

    async def test_match_detail_response_that_is_a_list_returns_none(self):
        client = LeetifyClient()
        with patch.object(client, "_get", AsyncMock(return_value=[])):
            self.assertIsNone(await client.get_match("m1"))


class LeetifyLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_creates_one_shared_http_client_and_closes_it(self):
        client = LeetifyClient()

        first = client._http()  # pylint: disable=protected-access
        self.assertIs(client._http(), first)  # pylint: disable=protected-access

        await client.aclose()
        self.assertTrue(first.is_closed)

    async def test_aclose_is_harmless_when_nothing_was_opened(self):
        await LeetifyClient().aclose()


if __name__ == "__main__":
    unittest.main()
