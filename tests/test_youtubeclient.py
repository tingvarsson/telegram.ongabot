import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx

from ongabot.youtube.client import BASE_URL, YouTubeClient, _parse_iso8601_duration

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as file:
        return json.load(file)


def _response(status_code, json_data=None, text=None):
    request = httpx.Request("GET", BASE_URL)
    if text is not None:
        return httpx.Response(status_code, text=text, request=request)
    return httpx.Response(status_code, json=json_data, request=request)


class ParseIso8601DurationTest(unittest.TestCase):
    def test_parses_seconds_only(self):
        self.assertEqual(_parse_iso8601_duration("PT47S"), 47)

    def test_parses_minutes_and_seconds(self):
        self.assertEqual(_parse_iso8601_duration("PT1M5S"), 65)

    def test_parses_hours_minutes_and_seconds(self):
        self.assertEqual(_parse_iso8601_duration("PT1H2M10S"), 3730)

    def test_zero_duration(self):
        self.assertEqual(_parse_iso8601_duration("PT0S"), 0)

    def test_malformed_duration_returns_none(self):
        self.assertIsNone(_parse_iso8601_duration("not-a-duration"))


class SearchShortsTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_search_results(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value=_fixture("youtube_search.json"))):
            results = await client.search_shorts("counter-strike")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].video_id, "abc123")
        self.assertEqual(results[0].title, "Insane CS2 Ace Clutch")
        self.assertEqual(results[1].video_id, "def456")

    async def test_returns_none_on_request_failure(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value=None)):
            self.assertIsNone(await client.search_shorts("counter-strike"))

    async def test_sends_query_and_key_as_params(self):
        seen = {}

        def handler(request):
            seen["params"] = dict(request.url.params)
            return _response(200, json_data={"items": []})

        client = YouTubeClient(api_key="secret-key")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                await client.search_shorts("linux", max_results=5)

        self.assertEqual(seen["params"]["q"], "linux")
        self.assertEqual(seen["params"]["key"], "secret-key")
        self.assertEqual(seen["params"]["maxResults"], "5")
        self.assertEqual(seen["params"]["type"], "video")
        self.assertEqual(seen["params"]["videoDuration"], "short")
        self.assertEqual(seen["params"]["safeSearch"], "strict")
        self.assertEqual(seen["params"]["order"], "viewCount")
        self.assertNotIn("publishedAfter", seen["params"])
        self.assertNotIn("videoCategoryId", seen["params"])

    async def _params_for(self, *args, **kwargs):
        seen = {}

        def handler(request):
            seen["params"] = dict(request.url.params)
            return _response(200, json_data={"items": []})

        client = YouTubeClient(api_key="key")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                await client.search_shorts(*args, **kwargs)
        return seen["params"]

    async def test_defaults_to_fifty_results_by_view_count(self):
        params = await self._params_for("linux")

        self.assertEqual(params["maxResults"], "50")
        self.assertEqual(params["order"], "viewCount")

    async def test_sends_order_published_after_and_category(self):
        params = await self._params_for(
            "#shorts",
            order="date",
            published_after=datetime(2026, 9, 22, 12, 30, 15, 123456, tzinfo=timezone.utc),
            category_id="20",
        )

        self.assertEqual(params["order"], "date")
        self.assertEqual(params["publishedAfter"], "2026-09-22T12:30:15Z")
        self.assertEqual(params["videoCategoryId"], "20")

    async def test_published_after_is_converted_to_utc(self):
        cest = timezone(timedelta(hours=2))
        params = await self._params_for("linux", published_after=datetime(2026, 9, 22, 14, 0, tzinfo=cest))

        self.assertEqual(params["publishedAfter"], "2026-09-22T12:00:00Z")

    async def test_naive_published_after_is_taken_as_utc(self):
        params = await self._params_for("linux", published_after=datetime(2026, 9, 22, 14, 0))

        self.assertEqual(params["publishedAfter"], "2026-09-22T14:00:00Z")

    async def test_empty_query_omits_q(self):
        params = await self._params_for("", category_id="20")

        self.assertNotIn("q", params)
        self.assertEqual(params["videoCategoryId"], "20")


class GetVideoDetailsTest(unittest.IsolatedAsyncioTestCase):
    async def test_parses_video_details_keyed_by_id(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value=_fixture("youtube_videos.json"))):
            details = await client.get_video_details(["abc123", "def456"])

        self.assertEqual(set(details), {"abc123", "def456"})
        short = details["abc123"]
        self.assertEqual(short.title, "Insane CS2 Ace Clutch")
        self.assertEqual(short.tags, ("cs2", "clutch", "counter-strike"))
        self.assertEqual(short.duration_seconds, 47)

        longer = details["def456"]
        self.assertEqual(longer.duration_seconds, 65)

    async def test_parses_view_count_from_statistics(self):
        client = YouTubeClient(api_key="key")
        payload = {
            "items": [
                {
                    "id": "abc123",
                    "snippet": {"title": "x", "liveBroadcastContent": "none"},
                    "contentDetails": {"duration": "PT30S"},
                    "statistics": {"viewCount": "1234567", "likeCount": "42"},
                }
            ]
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            details = await client.get_video_details(["abc123"])

        self.assertEqual(details["abc123"].view_count, 1234567)
        self.assertFalse(details["abc123"].live)

    async def test_requests_statistics_part_and_batched_ids(self):
        seen = {}

        def handler(request):
            seen["params"] = dict(request.url.params)
            return _response(200, json_data={"items": []})

        client = YouTubeClient(api_key="key")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                await client.get_video_details(["abc123", "def456"])

        self.assertEqual(seen["params"]["part"], "snippet,contentDetails,statistics")
        self.assertEqual(seen["params"]["id"], "abc123,def456")

    async def test_missing_statistics_gives_zero_views(self):
        client = YouTubeClient(api_key="key")
        payload = {"items": [{"id": "abc123", "snippet": {"title": "x"}, "contentDetails": {"duration": "PT30S"}}]}
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            details = await client.get_video_details(["abc123"])

        self.assertEqual(details["abc123"].view_count, 0)
        self.assertFalse(details["abc123"].live)

    async def test_hidden_or_malformed_view_count_gives_zero_views(self):
        client = YouTubeClient(api_key="key")
        payload = {
            "items": [
                {"id": "hidden", "contentDetails": {"duration": "PT30S"}, "statistics": {"likeCount": "5"}},
                {"id": "garbled", "contentDetails": {"duration": "PT30S"}, "statistics": {"viewCount": "lots"}},
            ]
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            details = await client.get_video_details(["hidden", "garbled"])

        self.assertEqual(details["hidden"].view_count, 0)
        self.assertEqual(details["garbled"].view_count, 0)

    async def test_live_and_upcoming_broadcasts_are_flagged_live(self):
        client = YouTubeClient(api_key="key")
        payload = {
            "items": [
                {
                    "id": video_id,
                    "snippet": {"title": "x", "liveBroadcastContent": state},
                    "contentDetails": {"duration": "PT30S"},
                }
                for video_id, state in (("live", "live"), ("upcoming", "upcoming"), ("done", "none"))
            ]
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            details = await client.get_video_details(["live", "upcoming", "done"])

        self.assertTrue(details["live"].live)
        self.assertTrue(details["upcoming"].live)
        self.assertFalse(details["done"].live)

    async def test_returns_none_on_request_failure(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value=None)):
            self.assertIsNone(await client.get_video_details(["abc123"]))

    async def test_video_missing_duration_is_parsed_with_zero_tags(self):
        client = YouTubeClient(api_key="key")
        payload = {
            "items": [{"id": "abc123", "snippet": {"title": "No tags here"}, "contentDetails": {"duration": "PT30S"}}]
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            details = await client.get_video_details(["abc123"])

        self.assertEqual(details["abc123"].tags, ())

    async def test_returns_empty_dict_when_no_ids_given(self):
        client = YouTubeClient(api_key="key")
        self.assertEqual(await client.get_video_details([]), {})

    async def test_unparseable_duration_returns_none(self):
        client = YouTubeClient(api_key="key")
        payload = {
            "items": [{"id": "abc123", "snippet": {"title": "x"}, "contentDetails": {"duration": "not-a-duration"}}]
        }
        with patch.object(client, "_get", AsyncMock(return_value=payload)):
            self.assertIsNone(await client.get_video_details(["abc123"]))


class YouTubeFailureIsolationTest(unittest.IsolatedAsyncioTestCase):
    """A YouTube API outage must never raise into the /short handler - every failure returns None."""

    async def _search_through(self, handler):
        client = YouTubeClient(api_key="key")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with patch.object(client, "_client", http):
                return await client.search_shorts("linux")

    async def test_server_error_returns_none(self):
        self.assertIsNone(await self._search_through(lambda request: _response(500, text="boom")))

    async def test_malformed_json_returns_none(self):
        self.assertIsNone(await self._search_through(lambda request: _response(200, text="not json{")))

    async def test_timeout_returns_none(self):
        def handler(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        self.assertIsNone(await self._search_through(handler))

    async def test_bad_request_without_api_key_returns_none(self):
        self.assertIsNone(await self._search_through(lambda request: _response(400, text="API key missing")))


class YouTubeSchemaDriftTest(unittest.IsolatedAsyncioTestCase):
    async def test_search_item_missing_video_id_returns_none(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value={"items": [{"snippet": {"title": "x"}}]})):
            self.assertIsNone(await client.search_shorts("linux"))

    async def test_search_response_that_is_a_list_returns_none(self):
        client = YouTubeClient(api_key="key")
        with patch.object(client, "_get", AsyncMock(return_value=[])):
            self.assertIsNone(await client.search_shorts("linux"))


class YouTubeLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_creates_one_shared_http_client_and_closes_it(self):
        client = YouTubeClient(api_key="key")

        first = client._http()  # pylint: disable=protected-access
        self.assertIs(client._http(), first)  # pylint: disable=protected-access

        await client.aclose()
        self.assertTrue(first.is_closed)

    async def test_aclose_is_harmless_when_nothing_was_opened(self):
        await YouTubeClient(api_key="key").aclose()


if __name__ == "__main__":
    unittest.main()
