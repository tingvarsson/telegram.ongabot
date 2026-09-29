import pickle
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from ongabot.youtube import selection
from ongabot.youtube.client import SearchResult, VideoDetail
from ongabot.youtube.selection import (
    CACHE_MAX_ENTRIES,
    GAMING_CATEGORY_ID,
    MAX_SHORT_SECONDS,
    WEEKLY_QUERY,
    PostedShort,
    Window,
    clear_cache,
    fetch_ranked,
    pick_short,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


class FakeChat:
    def __init__(self, recently_posted=()):
        self._recently_posted = set(recently_posted)

    def is_recently_posted(self, video_id):
        return video_id in self._recently_posted


def _detail(video_id, views=100, duration_seconds=30, live=False, title=None):
    return VideoDetail(
        video_id=video_id,
        title=title or f"Short {video_id}",
        tags=(),
        duration_seconds=duration_seconds,
        view_count=views,
        live=live,
    )


class FakeClient:
    """Serves search results per publish window, keyed on Window.days (None = all time).

    by_window maps days -> list of VideoDetail (the search hits, in search order) or None for
    a failed search. details_fail makes videos.list fail instead.
    """

    def __init__(self, by_window=None, details_fail=False):
        self.by_window = by_window or {}
        self.details_fail = details_fail
        self._details = {}
        for hits in self.by_window.values():
            for detail in hits or ():
                self._details[detail.video_id] = detail
        self.search_shorts = AsyncMock(side_effect=self._search)
        self.get_video_details = AsyncMock(side_effect=self._get_details)

    async def _search(self, query, *, published_after=None, category_id=None, **_kwargs):
        days = None if published_after is None else (NOW - published_after).days
        hits = self.by_window.get(days, [])
        if hits is None:
            return None
        return [SearchResult(video_id=detail.video_id, title=detail.title) for detail in hits]

    async def _get_details(self, video_ids):
        if self.details_fail:
            return None
        return {video_id: self._details[video_id] for video_id in video_ids if video_id in self._details}

    def searched_windows(self):
        return [call.kwargs["published_after"] for call in self.search_shorts.await_args_list]


class SelectionTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_cache()
        self.addCleanup(clear_cache)
        self.now = NOW
        patcher = patch.object(selection, "_now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)


class WindowTest(unittest.TestCase):
    def test_days_and_labels(self):
        self.assertEqual((Window.WEEK.days, Window.WEEK.label), (7, "this week"))
        self.assertEqual((Window.MONTH.days, Window.MONTH.label), (30, "in the past month"))
        self.assertEqual((Window.ALL_TIME.days, Window.ALL_TIME.label), (None, "of all time"))


class PostedShortCompatTest(unittest.TestCase):
    def test_legacy_record_still_round_trips_through_pickle(self):
        record = PostedShort(video_id="abc", topics=("linux",), posted_at=NOW)

        self.assertEqual(pickle.loads(pickle.dumps(record)), record)


class FetchRankedTest(SelectionTestCase):
    async def test_drops_long_and_live_videos_and_sorts_by_views(self):
        client = FakeClient(
            {
                7: [
                    _detail("low", views=10),
                    _detail("long", views=10_000, duration_seconds=MAX_SHORT_SECONDS + 1),
                    _detail("live", views=20_000, live=True),
                    _detail("edge", views=500, duration_seconds=MAX_SHORT_SECONDS),
                    _detail("high", views=9_000),
                ]
            }
        )

        ranked = await fetch_ranked(client, "linux", Window.WEEK)

        self.assertEqual([short.video_id for short in ranked], ["high", "edge", "low"])
        self.assertEqual(ranked[0].view_count, 9_000)
        self.assertEqual(ranked[0].url, "https://www.youtube.com/shorts/high")
        self.assertEqual(ranked[0].title, "Short high")

    async def test_equal_views_keep_search_order(self):
        client = FakeClient({7: [_detail("first", views=5), _detail("second", views=5)]})

        ranked = await fetch_ranked(client, "linux", Window.WEEK)

        self.assertEqual([short.video_id for short in ranked], ["first", "second"])

    async def test_duplicate_search_hits_are_detailed_once(self):
        client = FakeClient({7: [_detail("a"), _detail("a"), _detail("b")]})

        ranked = await fetch_ranked(client, "linux", Window.WEEK)

        self.assertEqual([short.video_id for short in ranked], ["a", "b"])
        client.get_video_details.assert_awaited_once_with(["a", "b"])

    async def test_ids_without_details_are_dropped(self):
        client = FakeClient({7: [_detail("a")]})
        client.search_shorts = AsyncMock(return_value=[SearchResult("gone", "x"), SearchResult("a", "y")])

        ranked = await fetch_ranked(client, "linux", Window.WEEK)

        self.assertEqual([short.video_id for short in ranked], ["a"])

    async def test_window_sets_published_after_and_category_is_passed_through(self):
        client = FakeClient()

        await fetch_ranked(client, "#shorts", Window.WEEK, "20")
        await fetch_ranked(client, "linux", Window.MONTH)
        await fetch_ranked(client, "linux", Window.ALL_TIME)

        calls = client.search_shorts.await_args_list
        self.assertEqual(calls[0].args, ("#shorts",))
        self.assertEqual(calls[0].kwargs, {"published_after": NOW - timedelta(days=7), "category_id": "20"})
        self.assertEqual(calls[1].kwargs, {"published_after": NOW - timedelta(days=30), "category_id": None})
        self.assertEqual(calls[2].kwargs, {"published_after": None, "category_id": None})

    async def test_search_failure_returns_none_and_is_not_cached(self):
        client = FakeClient({7: None})

        self.assertIsNone(await fetch_ranked(client, "linux", Window.WEEK))
        self.assertIsNone(await fetch_ranked(client, "linux", Window.WEEK))

        self.assertEqual(client.search_shorts.await_count, 2)
        client.get_video_details.assert_not_awaited()

    async def test_details_failure_returns_none_and_is_not_cached(self):
        client = FakeClient({7: [_detail("a")]}, details_fail=True)

        self.assertIsNone(await fetch_ranked(client, "linux", Window.WEEK))
        self.assertIsNone(await fetch_ranked(client, "linux", Window.WEEK))

        self.assertEqual(client.search_shorts.await_count, 2)

    async def test_empty_result_is_cached(self):
        client = FakeClient({7: []})

        self.assertEqual(await fetch_ranked(client, "linux", Window.WEEK), [])
        self.assertEqual(await fetch_ranked(client, "linux", Window.WEEK), [])

        client.search_shorts.assert_awaited_once()


class FetchRankedCacheTest(SelectionTestCase):
    async def test_second_call_is_served_from_cache(self):
        client = FakeClient({7: [_detail("a")]})

        first = await fetch_ranked(client, "linux", Window.WEEK)
        second = await fetch_ranked(client, "linux", Window.WEEK)

        self.assertEqual(first, second)
        client.search_shorts.assert_awaited_once()
        client.get_video_details.assert_awaited_once()

    async def test_query_window_and_category_are_separate_entries(self):
        client = FakeClient({7: [_detail("a")], 30: [_detail("b")]})

        await fetch_ranked(client, "linux", Window.WEEK)
        await fetch_ranked(client, "linux", Window.MONTH)
        await fetch_ranked(client, "rust", Window.WEEK)
        await fetch_ranked(client, "linux", Window.WEEK, "20")

        self.assertEqual(client.search_shorts.await_count, 4)

    async def test_entry_expires_after_ttl(self):
        client = FakeClient({7: [_detail("a")]})

        await fetch_ranked(client, "linux", Window.WEEK)
        self.now = NOW + selection.CACHE_TTL - timedelta(seconds=1)
        await fetch_ranked(client, "linux", Window.WEEK)
        self.assertEqual(client.search_shorts.await_count, 1)

        self.now = NOW + selection.CACHE_TTL
        await fetch_ranked(client, "linux", Window.WEEK)
        self.assertEqual(client.search_shorts.await_count, 2)

    async def test_oldest_entry_is_evicted_when_full(self):
        client = FakeClient({7: [_detail("a")]})

        for index in range(CACHE_MAX_ENTRIES + 1):
            await fetch_ranked(client, f"q{index}", Window.WEEK)
        self.assertEqual(client.search_shorts.await_count, CACHE_MAX_ENTRIES + 1)

        # q1 survived (hit), q0 was the oldest and was evicted (miss).
        await fetch_ranked(client, "q1", Window.WEEK)
        self.assertEqual(client.search_shorts.await_count, CACHE_MAX_ENTRIES + 1)
        await fetch_ranked(client, "q0", Window.WEEK)
        self.assertEqual(client.search_shorts.await_count, CACHE_MAX_ENTRIES + 2)

    async def test_cached_list_is_not_shared_with_callers(self):
        client = FakeClient({7: [_detail("a")]})

        first = await fetch_ranked(client, "linux", Window.WEEK)
        first.clear()

        self.assertEqual(len(await fetch_ranked(client, "linux", Window.WEEK)), 1)


class PickShortWeeklyTest(SelectionTestCase):
    async def test_no_topics_picks_top_gaming_short_of_the_week(self):
        client = FakeClient({7: [_detail("second", views=5), _detail("top", views=50)]})

        result = await pick_short(client, FakeChat(), [])

        self.assertFalse(result.unavailable)
        self.assertFalse(result.exhausted)
        video = result.video
        self.assertEqual(video.video_id, "top")
        self.assertEqual(video.rank, 1)
        self.assertEqual(video.window, Window.WEEK)
        self.assertEqual(video.view_count, 50)
        self.assertEqual(video.topics, ())
        self.assertEqual(video.url, "https://www.youtube.com/shorts/top")
        client.search_shorts.assert_awaited_once_with(
            WEEKLY_QUERY, published_after=NOW - timedelta(days=7), category_id=GAMING_CATEGORY_ID
        )

    async def test_rank_counts_already_seen_shorts(self):
        client = FakeClient({7: [_detail("one", views=3), _detail("two", views=2), _detail("three", views=1)]})

        result = await pick_short(client, FakeChat(recently_posted={"one", "two"}), [])

        self.assertEqual(result.video.video_id, "three")
        self.assertEqual(result.video.rank, 3)

    async def test_no_topics_never_widens(self):
        client = FakeClient({7: [_detail("seen")], 30: [_detail("fresh")], None: [_detail("fresh")]})

        result = await pick_short(client, FakeChat(recently_posted={"seen"}), [])

        self.assertTrue(result.exhausted)
        self.assertIsNone(result.video)
        self.assertFalse(result.unavailable)
        client.search_shorts.assert_awaited_once()

    async def test_no_topics_search_failure_is_unavailable(self):
        client = FakeClient({7: None})

        result = await pick_short(client, FakeChat(), [])

        self.assertTrue(result.unavailable)
        self.assertFalse(result.exhausted)
        self.assertIsNone(result.video)

    async def test_repeated_calls_walk_down_the_cached_chart(self):
        client = FakeClient({7: [_detail("one", views=3), _detail("two", views=2)]})
        chat = FakeChat()

        first = await pick_short(client, chat, [])
        chat._recently_posted.add(first.video.video_id)  # pylint: disable=protected-access
        second = await pick_short(client, chat, [])

        self.assertEqual((first.video.rank, second.video.rank), (1, 2))
        client.search_shorts.assert_awaited_once()


class PickShortTopicsTest(SelectionTestCase):
    async def test_topics_search_all_categories_with_joined_query(self):
        client = FakeClient({7: [_detail("cs")]})

        result = await pick_short(client, FakeChat(), ["counter", "strike"])

        self.assertEqual(result.video.video_id, "cs")
        self.assertEqual(result.video.topics, ("counter", "strike"))
        self.assertEqual(result.video.window, Window.WEEK)
        client.search_shorts.assert_awaited_once_with(
            "counter strike", published_after=NOW - timedelta(days=7), category_id=None
        )

    async def test_blank_topics_are_dropped(self):
        client = FakeClient({7: [_detail("cs")]})

        result = await pick_short(client, FakeChat(), [" counter ", "", "  ", "strike"])

        self.assertEqual(result.video.topics, ("counter", "strike"))
        self.assertEqual(client.search_shorts.await_args.args, ("counter strike",))

    async def test_only_blank_topics_fall_back_to_the_weekly_chart(self):
        client = FakeClient({7: [_detail("top")]})

        await pick_short(client, FakeChat(), ["", " "])

        self.assertEqual(client.search_shorts.await_args.args, (WEEKLY_QUERY,))
        self.assertEqual(client.search_shorts.await_args.kwargs["category_id"], GAMING_CATEGORY_ID)

    async def test_widens_to_month_when_week_is_all_seen(self):
        client = FakeClient(
            {7: [_detail("seen")], 30: [_detail("seen", views=9), _detail("month", views=1)], None: [_detail("x")]}
        )

        result = await pick_short(client, FakeChat(recently_posted={"seen"}), ["linux"])

        self.assertEqual(result.video.video_id, "month")
        self.assertEqual(result.video.window, Window.MONTH)
        self.assertEqual(result.video.rank, 2)
        self.assertEqual(client.searched_windows(), [NOW - timedelta(days=7), NOW - timedelta(days=30)])

    async def test_widens_to_all_time_when_week_and_month_are_empty(self):
        client = FakeClient({7: [], 30: [], None: [_detail("classic")]})

        result = await pick_short(client, FakeChat(), ["linux"])

        self.assertEqual(result.video.video_id, "classic")
        self.assertEqual(result.video.window, Window.ALL_TIME)
        self.assertEqual(result.video.rank, 1)
        self.assertEqual(len(client.searched_windows()), 3)

    async def test_failed_window_widens_instead_of_giving_up(self):
        client = FakeClient({7: None, 30: [_detail("month")]})

        result = await pick_short(client, FakeChat(), ["linux"])

        self.assertEqual(result.video.video_id, "month")
        self.assertEqual(result.video.window, Window.MONTH)

    async def test_every_window_failing_is_unavailable(self):
        client = FakeClient({7: None, 30: None, None: None})

        result = await pick_short(client, FakeChat(), ["linux"])

        self.assertTrue(result.unavailable)
        self.assertFalse(result.exhausted)
        self.assertIsNone(result.video)
        self.assertEqual(client.search_shorts.await_count, 3)

    async def test_everything_seen_is_exhausted(self):
        client = FakeClient({7: [_detail("a")], 30: [_detail("a")], None: [_detail("a"), _detail("b")]})

        result = await pick_short(client, FakeChat(recently_posted={"a", "b"}), ["linux"])

        self.assertTrue(result.exhausted)
        self.assertFalse(result.unavailable)
        self.assertIsNone(result.video)

    async def test_nothing_found_with_any_window_failing_is_unavailable(self):
        # The failed windows may have had something unseen, so "try again" beats "try other topics".
        client = FakeClient({7: [_detail("a")], 30: None, None: []})

        result = await pick_short(client, FakeChat(recently_posted={"a"}), ["linux"])

        self.assertTrue(result.unavailable)
        self.assertFalse(result.exhausted)
        self.assertIsNone(result.video)


if __name__ == "__main__":
    unittest.main()
