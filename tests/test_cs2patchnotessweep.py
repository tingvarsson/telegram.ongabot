import datetime
import os
import unittest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot import ongabot
from ongabot.botdata import BotData
from ongabot.cs2.steamnews import SteamNewsItem


def _item(gid: str, title: Optional[str] = None, date: int = 1_000) -> SteamNewsItem:
    return SteamNewsItem(
        gid=gid,
        title=title or f"Patch {gid}",
        url=f"https://example.com/{gid}",
        contents="[p]x[/p]",
        date=date,
        tags=(),
    )


def _sent_text(send: AsyncMock) -> str:
    return "\n".join(call.args[2] for call in send.await_args_list)


def _sent_chats(send: AsyncMock) -> set:
    return {call.args[1] for call in send.await_args_list}


class PollIntervalTest(unittest.TestCase):
    def test_defaults_to_twenty_minutes(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ongabot.cs2_patchnotes_poll_interval(), datetime.timedelta(minutes=20))

    def test_env_var_overrides_the_default(self) -> None:
        with patch.dict(os.environ, {"CS2_PATCHNOTES_POLL_MINUTES": "15"}):
            self.assertEqual(ongabot.cs2_patchnotes_poll_interval(), datetime.timedelta(minutes=15))

    def test_malformed_value_falls_back_with_a_warning(self) -> None:
        with patch.dict(os.environ, {"CS2_PATCHNOTES_POLL_MINUTES": "soon"}):
            with self.assertLogs(ongabot.logger, level="WARNING"):
                self.assertEqual(ongabot.cs2_patchnotes_poll_interval(), datetime.timedelta(minutes=20))

    def test_non_positive_value_falls_back(self) -> None:
        with patch.dict(os.environ, {"CS2_PATCHNOTES_POLL_MINUTES": "0"}):
            with self.assertLogs(ongabot.logger, level="WARNING"):
                self.assertEqual(ongabot.cs2_patchnotes_poll_interval(), datetime.timedelta(minutes=20))


class AnnounceCs2PatchNotesTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_to_every_subscriber(self) -> None:
        bot_data = BotData()
        bot_data.cs2_patchnotes_subscribers = {101, 202}
        send = AsyncMock()
        with patch("ongabot.ongabot.send_html_with_fallback", send):
            await ongabot._announce_cs2_patch_notes(AsyncMock(), bot_data, [_item("1")])
        self.assertEqual(_sent_chats(send), {101, 202})

    async def test_one_failing_chat_does_not_stop_the_others(self) -> None:
        bot_data = BotData()
        bot_data.cs2_patchnotes_subscribers = {101, 202}

        async def send(_bot, chat_id, _text):
            if chat_id == 101:
                raise TelegramError("bot was kicked")

        sender = AsyncMock(side_effect=send)
        with patch("ongabot.ongabot.send_html_with_fallback", sender):
            await ongabot._announce_cs2_patch_notes(AsyncMock(), bot_data, [_item("1")])
        self.assertIn(202, _sent_chats(sender))

    async def test_a_subscription_change_mid_broadcast_does_not_break_it(self) -> None:
        # /cs2patches can run while the job awaits a send; the set must not change under the loop.
        bot_data = BotData()
        bot_data.cs2_patchnotes_subscribers = {101, 202}

        async def send(_bot, _chat_id, _text):
            bot_data.subscribe_to_cs2_patchnotes(303)

        sender = AsyncMock(side_effect=send)
        with patch("ongabot.ongabot.send_html_with_fallback", sender):
            await ongabot._announce_cs2_patch_notes(AsyncMock(), bot_data, [_item("1")])
        self.assertEqual(_sent_chats(sender), {101, 202})


class Cs2PatchNotesSweepTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot_data = BotData()
        self.bot_data.cs2_patchnotes_subscribers = {101}

    async def _sweep(self, fetched: Optional[List[SteamNewsItem]]) -> AsyncMock:
        context = MagicMock()
        context.bot = AsyncMock()
        context.bot_data = self.bot_data
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(return_value=fetched)
        send = AsyncMock()
        with patch("ongabot.ongabot.get_steam_news_client", return_value=client), patch(
            "ongabot.ongabot.send_html_with_fallback", send
        ):
            await ongabot.cs2_patchnotes_sweep_callback(context)
        return send

    async def test_first_fetch_records_the_feed_without_announcing(self) -> None:
        send = await self._sweep([_item("b", date=2), _item("a", date=1)])
        send.assert_not_awaited()
        self.assertEqual(self.bot_data.cs2_patchnotes_seen_gids, {"a", "b"})

    async def test_an_empty_first_fetch_does_not_prime(self) -> None:
        # Priming on an empty feed would make the next non-empty fetch announce everything.
        await self._sweep([])
        self.assertIsNone(self.bot_data.cs2_patchnotes_seen_gids)

    async def test_unreachable_feed_changes_nothing(self) -> None:
        self.bot_data.cs2_patchnotes_seen_gids = {"a"}
        send = await self._sweep(None)
        send.assert_not_awaited()
        self.assertEqual(self.bot_data.cs2_patchnotes_seen_gids, {"a"})

    async def test_a_new_patch_is_announced_and_recorded(self) -> None:
        self.bot_data.cs2_patchnotes_seen_gids = {"a"}
        send = await self._sweep([_item("b", title="Fresh patch", date=2), _item("a", date=1)])
        self.assertEqual(_sent_chats(send), {101})
        self.assertIn("Fresh patch", _sent_text(send))
        self.assertEqual(self.bot_data.cs2_patchnotes_seen_gids, {"a", "b"})

    async def test_an_already_seen_patch_is_not_announced_again(self) -> None:
        self.bot_data.cs2_patchnotes_seen_gids = {"a", "b"}
        send = await self._sweep([_item("b", date=2), _item("a", date=1)])
        send.assert_not_awaited()

    async def test_several_new_patches_are_announced_oldest_first(self) -> None:
        self.bot_data.cs2_patchnotes_seen_gids = {"a"}
        # Steam lists newest first.
        send = await self._sweep(
            [_item("c", title="Third", date=3), _item("b", title="Second", date=2), _item("a", date=1)]
        )
        text = _sent_text(send)
        self.assertLess(text.index("Second"), text.index("Third"))

    async def test_new_patches_are_recorded_even_with_no_subscribers(self) -> None:
        self.bot_data.cs2_patchnotes_subscribers = set()
        self.bot_data.cs2_patchnotes_seen_gids = {"a"}
        send = await self._sweep([_item("b", date=2), _item("a", date=1)])
        send.assert_not_awaited()
        self.assertEqual(self.bot_data.cs2_patchnotes_seen_gids, {"a", "b"})

    async def test_a_patch_that_left_the_feed_stays_remembered(self) -> None:
        # So it is never re-announced should Steam's page shrink and bring it back.
        self.bot_data.cs2_patchnotes_seen_gids = {"a", "b"}
        await self._sweep([_item("c", date=3), _item("b", date=2)])
        self.assertEqual(self.bot_data.cs2_patchnotes_seen_gids, {"a", "b", "c"})


class PostInitRegistersPatchNotesSweepTest(unittest.IsolatedAsyncioTestCase):
    async def test_polls_on_the_configured_interval(self) -> None:
        application = MagicMock()
        application.bot = AsyncMock()
        application.bot_data.schedule_all_event_jobs.return_value = None
        application.job_queue = MagicMock()

        with patch.dict(os.environ, {"CS2_PATCHNOTES_POLL_MINUTES": "25"}):
            await ongabot.post_init(application)

        (call,) = [
            call
            for call in application.job_queue.run_repeating.call_args_list
            if call.kwargs["name"] == "cs2_patchnotes_sweep"
        ]
        self.assertIs(call.args[0], ongabot.cs2_patchnotes_sweep_callback)
        self.assertEqual(call.kwargs["interval"], datetime.timedelta(minutes=25))


if __name__ == "__main__":
    unittest.main()
