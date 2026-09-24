import json
import os
import unittest
from typing import Any, Dict, List

import httpx

from ongabot.cs2 import steamnews
from ongabot.cs2.steamnews import APPID_CS2, BASE_URL, SteamNewsClient, SteamNewsItem

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# The patchnotes-tagged items in tests/fixtures/steam_news_cs2.json, newest first.
FIXTURE_PATCH_GIDS = ["1844751498219795", "1840944183775194", "1838407329258098", "1833334318567523"]


def _fixture() -> Dict[str, Any]:
    with open(os.path.join(FIXTURES, "steam_news_cs2.json"), encoding="utf-8") as file:
        return json.load(file)


def _response(status_code: int, json_data: Any = None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("GET", BASE_URL)
    if text is not None:
        return httpx.Response(status_code, text=text, request=request)
    return httpx.Response(status_code, json=json_data, request=request)


def _payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"appnews": {"appid": APPID_CS2, "newsitems": items, "count": len(items)}}


def _item(gid: str, **overrides: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "gid": gid,
        "title": "Counter-Strike 2 Update",
        "url": f"https://example.com/{gid}",
        "author": "Valve",
        "contents": "[p]x[/p]",
        "date": 1_790_000_000,
        "feedname": "steam_community_announcements",
        "tags": ["patchnotes"],
    }
    item.update(overrides)
    return item


class _ClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def _fetch(self, handler) -> List[SteamNewsItem] | None:
        client = SteamNewsClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client._client = http  # pylint: disable=protected-access
            return await client.get_cs2_patch_notes()

    async def _fetch_payload(self, payload: Any) -> List[SteamNewsItem] | None:
        return await self._fetch(lambda request: _response(200, json_data=payload))


class ParseTest(_ClientTestCase):
    async def test_returns_only_patch_note_items_from_real_payload(self) -> None:
        items = await self._fetch_payload(_fixture())
        self.assertEqual([item.gid for item in items], FIXTURE_PATCH_GIDS)

    async def test_parses_item_fields(self) -> None:
        items = await self._fetch_payload(_fixture())
        first = items[0]
        self.assertEqual(first.gid, "1844751498219795")
        self.assertEqual(first.title, "Counter-Strike 2 Update")
        self.assertEqual(first.date, 1790204844)
        self.assertTrue(first.url.startswith("https://"))
        self.assertIn("[list]", first.contents)
        self.assertIn("patchnotes", first.tags)

    async def test_empty_news_list_is_an_empty_result_not_a_failure(self) -> None:
        self.assertEqual(await self._fetch_payload(_payload([])), [])

    async def test_requests_cs2_news_as_json(self) -> None:
        seen: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _response(200, json_data=_payload([]))

        await self._fetch(handler)
        (request,) = seen
        self.assertEqual(request.url.path, "/ISteamNews/GetNewsForApp/v2/")
        self.assertEqual(request.url.params["appid"], str(APPID_CS2))
        self.assertEqual(request.url.params["format"], "json")
        self.assertEqual(request.url.params["count"], str(steamnews.DEFAULT_COUNT))


class ClassificationTest(_ClientTestCase):
    async def test_patchnotes_tag_matches_case_insensitively(self) -> None:
        items = await self._fetch_payload(_payload([_item("1", tags=["PatchNotes"])]))
        self.assertEqual([item.gid for item in items], ["1"])

    async def test_untagged_valve_update_post_matches_by_title(self) -> None:
        items = await self._fetch_payload(_payload([_item("1", tags=None)]))
        self.assertEqual([item.gid for item in items], ["1"])

    async def test_third_party_post_with_an_update_title_does_not_match(self) -> None:
        items = await self._fetch_payload(_payload([_item("1", tags=None, feedname="PC Gamer")]))
        self.assertEqual(items, [])

    async def test_untagged_valve_post_with_another_title_does_not_match(self) -> None:
        items = await self._fetch_payload(_payload([_item("1", tags=None, title="Rush Hour")]))
        self.assertEqual(items, [])


class FailureIsolationTest(_ClientTestCase):
    """A Steam outage must never raise into the sweep job - every failure returns None."""

    async def test_server_error_returns_none(self) -> None:
        self.assertIsNone(await self._fetch(lambda request: _response(500, text="boom")))

    async def test_malformed_json_returns_none(self) -> None:
        self.assertIsNone(await self._fetch(lambda request: _response(200, text="not json{")))

    async def test_unexpected_payload_shape_returns_none(self) -> None:
        self.assertIsNone(await self._fetch_payload({"oops": True}))

    async def test_newsitems_not_a_list_returns_none(self) -> None:
        self.assertIsNone(await self._fetch_payload({"appnews": {"newsitems": "nope"}}))

    async def test_timeout_returns_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        self.assertIsNone(await self._fetch(handler))

    async def test_connection_error_returns_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable", request=request)

        self.assertIsNone(await self._fetch(handler))

    async def test_a_malformed_item_is_skipped_not_fatal(self) -> None:
        # One bad item must not block every other patch note until it scrolls off the feed.
        broken = _item("1")
        del broken["gid"]
        items = await self._fetch_payload(_payload([broken, _item("2")]))
        self.assertEqual([item.gid for item in items], ["2"])

    async def test_retries_once_after_a_transient_failure(self) -> None:
        responses = [_response(503, text="busy"), _response(200, json_data=_payload([_item("1")]))]
        items = await self._fetch(lambda request: responses.pop(0))
        self.assertEqual([item.gid for item in items], ["1"])


class LifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_creates_one_shared_http_client_and_closes_it(self) -> None:
        client = SteamNewsClient()
        http = client._http()  # pylint: disable=protected-access
        self.assertIs(client._http(), http)  # pylint: disable=protected-access
        await client.aclose()
        self.assertTrue(http.is_closed)

    def test_get_client_returns_one_shared_instance(self) -> None:
        self.assertIs(steamnews.get_client(), steamnews.get_client())


if __name__ == "__main__":
    unittest.main()
