import unittest
from unittest.mock import AsyncMock

from ongabot.youtube.client import SearchResult, VideoDetail
from ongabot.youtube.selection import pick_short


class FakeChat:
    def __init__(self, recently_posted=()):
        self._recently_posted = set(recently_posted)

    def is_recently_posted(self, video_id):
        return video_id in self._recently_posted


class FakeClient:
    def __init__(self, search_results=None, details=None):
        self.search_shorts = AsyncMock(return_value=search_results)
        self.get_video_details = AsyncMock(return_value=details)


def _result(video_id, title="A Short"):
    return SearchResult(video_id=video_id, title=title)


def _detail(video_id, title="A Short", tags=(), duration_seconds=30):
    return VideoDetail(video_id=video_id, title=title, tags=tuple(tags), duration_seconds=duration_seconds)


class PickShortTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_none_when_search_yields_no_results(self):
        client = FakeClient(search_results=[])

        self.assertIsNone(await pick_short(client, FakeChat(), "linux"))

    async def test_returns_none_when_search_fails(self):
        client = FakeClient(search_results=None)

        self.assertIsNone(await pick_short(client, FakeChat(), "linux"))

    async def test_skips_recently_posted_video_ids(self):
        client = FakeClient(
            search_results=[_result("old"), _result("fresh")],
            details={"fresh": _detail("fresh", title="Fresh One")},
        )
        chat = FakeChat(recently_posted={"old"})

        video = await pick_short(client, chat, "linux")

        self.assertEqual(video.video_id, "fresh")
        client.get_video_details.assert_awaited_once_with(["fresh"])

    async def test_returns_none_when_all_candidates_already_posted(self):
        client = FakeClient(search_results=[_result("old")])
        chat = FakeChat(recently_posted={"old"})

        self.assertIsNone(await pick_short(client, chat, "linux"))
        client.get_video_details.assert_not_awaited()

    async def test_skips_videos_over_60_seconds(self):
        client = FakeClient(
            search_results=[_result("long"), _result("short")],
            details={"long": _detail("long", duration_seconds=90), "short": _detail("short", duration_seconds=45)},
        )

        video = await pick_short(client, FakeChat(), "linux")

        self.assertEqual(video.video_id, "short")

    async def test_returns_first_eligible_candidate_in_search_order(self):
        client = FakeClient(
            search_results=[_result("first"), _result("second")],
            details={"first": _detail("first", duration_seconds=20), "second": _detail("second", duration_seconds=20)},
        )

        video = await pick_short(client, FakeChat(), "linux")

        self.assertEqual(video.video_id, "first")

    async def test_returns_none_when_video_details_unavailable(self):
        client = FakeClient(search_results=[_result("abc")], details=None)

        self.assertIsNone(await pick_short(client, FakeChat(), "linux"))

    async def test_extracted_topics_and_url_populated_on_result(self):
        client = FakeClient(
            search_results=[_result("abc")],
            details={"abc": _detail("abc", title="Linux Ricing Tips", tags=["linux", "ricing"], duration_seconds=30)},
        )

        video = await pick_short(client, FakeChat(), "linux")

        self.assertIn("linux", video.topics)
        self.assertIn("ricing", video.topics)
        self.assertEqual(video.url, "https://www.youtube.com/shorts/abc")

    async def test_returns_none_when_no_candidate_is_short_enough(self):
        client = FakeClient(
            search_results=[_result("too_long")],
            details={"too_long": _detail("too_long", duration_seconds=120)},
        )

        self.assertIsNone(await pick_short(client, FakeChat(), "linux"))


if __name__ == "__main__":
    unittest.main()
