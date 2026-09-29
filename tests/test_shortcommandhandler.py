import unittest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot.botdata import BotData
from ongabot.handler.shortcommandhandler import (
    MAX_TOPICS_LENGTH,
    UNAVAILABLE_TEXT,
    ShortCommandHandler,
    callback,
    format_views,
    render_exhausted_message,
    render_short_message,
)
from ongabot.utils.commands import SHORT
from ongabot.youtube.selection import PickResult, SelectedVideo, Window

MODULE = "ongabot.handler.shortcommandhandler"
CHAT_ID = 123


def _video(rank: int = 3, window: Window = Window.WEEK, views: int = 12_400_000, topics=()) -> SelectedVideo:
    return SelectedVideo(
        video_id="abc123",
        title="Clutch",
        url="https://www.youtube.com/shorts/abc123",
        view_count=views,
        rank=rank,
        window=window,
        topics=tuple(topics),
    )


def _make(args: Optional[List[str]]):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = CHAT_ID
    context = MagicMock()
    context.args = args
    context.bot_data = BotData()
    return update, context


def _replies(update) -> List[str]:
    return [call.args[0] for call in update.message.reply_text.await_args_list]


class _HandlerTestCase(unittest.IsolatedAsyncioTestCase):
    """Runs the callback with the YouTube client and pick_short patched out."""

    async def _run(self, args: Optional[List[str]], result: PickResult, send_error=None):
        update, context = _make(args)
        if send_error is not None:
            update.message.reply_text.side_effect = send_error
        client = MagicMock()
        pick = AsyncMock(return_value=result)
        with patch(f"{MODULE}.get_client", return_value=client), patch(f"{MODULE}.selection.pick_short", pick):
            await callback(update, context)
        return update, context, client, pick


class PostTest(_HandlerTestCase):
    async def test_posts_the_weekly_short_without_quoting_and_records_it(self) -> None:
        update, context, client, pick = await self._run(None, PickResult(video=_video()))

        chat = context.bot_data.get_chat(CHAT_ID)
        pick.assert_awaited_once_with(client, chat, [])
        update.message.reply_text.assert_awaited_once_with(
            "#3 this week · 12.4M views\nhttps://www.youtube.com/shorts/abc123", do_quote=False
        )
        self.assertTrue(chat.is_recently_posted("abc123"))

    async def test_topics_are_lowercased_stripped_and_named_in_the_header(self) -> None:
        video = _video(rank=1, window=Window.MONTH, views=3_100_000, topics=("counter", "strike"))
        update, context, client, pick = await self._run(["Counter", " STRIKE ", "  "], PickResult(video=video))

        pick.assert_awaited_once_with(client, context.bot_data.get_chat(CHAT_ID), ["counter", "strike"])
        self.assertEqual(
            _replies(update),
            ["#1 for counter strike in the past month · 3.1M views\nhttps://www.youtube.com/shorts/abc123"],
        )

    async def test_send_failure_records_nothing(self) -> None:
        _update, context, _client, _pick = await self._run(
            None, PickResult(video=_video()), send_error=TelegramError("boom")
        )

        self.assertFalse(context.bot_data.get_chat(CHAT_ID).is_recently_posted("abc123"))

    async def test_short_is_recorded_before_the_send_completes(self) -> None:
        # A second /short handled while this send is in flight must already see the Short as
        # posted, or both would post it.
        seen_during_send = []

        async def send(*_args, **_kwargs):
            seen_during_send.append(context.bot_data.get_chat(CHAT_ID).is_recently_posted("abc123"))

        update, context = _make(None)
        update.message.reply_text = AsyncMock(side_effect=send)
        with patch(f"{MODULE}.get_client"), patch(
            f"{MODULE}.selection.pick_short", AsyncMock(return_value=PickResult(video=_video()))
        ):
            await callback(update, context)

        self.assertEqual(seen_during_send, [True])

    async def test_topics_over_the_length_cap_get_the_usage(self) -> None:
        update, _context, _client, pick = await self._run(["x" * (MAX_TOPICS_LENGTH + 1)], PickResult(exhausted=True))

        pick.assert_not_awaited()
        self.assertEqual(_replies(update), [SHORT.usage])

    async def test_topics_at_the_length_cap_are_searched(self) -> None:
        _update, _context, _client, pick = await self._run(["x" * MAX_TOPICS_LENGTH], PickResult(exhausted=True))

        pick.assert_awaited_once()


class NoShortTest(_HandlerTestCase):
    async def test_unavailable_asks_to_try_again(self) -> None:
        update, context, _client, _pick = await self._run(None, PickResult(unavailable=True))

        self.assertEqual(_replies(update), [UNAVAILABLE_TEXT])
        self.assertEqual(context.bot_data.get_chat(CHAT_ID).recent_video_ids, {})

    async def test_exhausted_weekly_list_suggests_topics(self) -> None:
        update, _context, _client, _pick = await self._run([], PickResult(exhausted=True))

        self.assertEqual(
            _replies(update),
            ["You've already had every top Short I could find for this week's gaming list - try some topics."],
        )

    async def test_exhausted_topics_suggests_other_topics(self) -> None:
        update, _context, _client, _pick = await self._run(["Linux"], PickResult(exhausted=True))

        self.assertEqual(
            _replies(update), ["You've already had every top Short I could find for linux - try other topics."]
        )


class CallbackGuardTest(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_update_without_message(self) -> None:
        update, context = _make(None)
        update.message = None
        pick = AsyncMock()
        with patch(f"{MODULE}.selection.pick_short", pick):
            await callback(update, context)
        pick.assert_not_awaited()


class HandlerTest(unittest.TestCase):
    def test_is_non_blocking(self) -> None:
        self.assertFalse(ShortCommandHandler().block)

    def test_handles_short_command(self) -> None:
        self.assertEqual(ShortCommandHandler().commands, frozenset({"short"}))


class RenderTest(unittest.TestCase):
    def test_weekly_header(self) -> None:
        self.assertEqual(
            render_short_message(_video(), []), "#3 this week · 12.4M views\nhttps://www.youtube.com/shorts/abc123"
        )

    def test_topic_header_all_time(self) -> None:
        text = render_short_message(_video(rank=2, window=Window.ALL_TIME, views=950), ["linux"])
        self.assertEqual(text.splitlines()[0], "#2 for linux of all time · 950 views")

    def test_single_view_is_singular(self) -> None:
        self.assertEqual(render_short_message(_video(views=1), []).splitlines()[0], "#3 this week · 1 view")

    def test_exhausted_messages(self) -> None:
        self.assertIn("this week's gaming list", render_exhausted_message([]))
        self.assertIn("for counter strike -", render_exhausted_message(["counter", "strike"]))


class FormatViewsTest(unittest.TestCase):
    def test_compact_counts(self) -> None:
        cases = {
            0: "0",
            999: "999",
            1_000: "1K",
            1_234: "1.2K",
            12_400_000: "12.4M",
            3_000_000_000: "3B",
            # Rounding up to 1000 of a unit rolls over to the next one.
            999_960: "1M",
            999_960_000: "1B",
            1_250_000_000_000: "1250B",
        }
        for count, expected in cases.items():
            with self.subTest(count=count):
                self.assertEqual(format_views(count), expected)


if __name__ == "__main__":
    unittest.main()
