import unittest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot.botdata import BotData
from ongabot.cs2.steamnews import SteamNewsItem
from ongabot.handler.cs2patchescommandhandler import Cs2PatchesCommandHandler, callback
from ongabot.utils.commands import CS2PATCHES

MODULE = "ongabot.handler.cs2patchescommandhandler"
CHAT_ID = 123


def _item(gid: str, title: str, date: int) -> SteamNewsItem:
    return SteamNewsItem(
        gid=gid, title=title, url=f"https://example.com/{gid}", contents="[p]x[/p]", date=date, tags=()
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
    """Runs the callback with the Steam client and the HTML sender patched out."""

    async def _run(self, args: Optional[List[str]], fetched: Optional[List[SteamNewsItem]] = None, send_error=None):
        update, context = _make(args)
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(return_value=fetched)
        send = AsyncMock(side_effect=send_error)
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)
        return update, context, client, send


class TurnOnTest(_HandlerTestCase):
    async def test_subscribes_the_chat_and_confirms(self) -> None:
        update, context, _client, _send = await self._run(["on"], fetched=[])
        self.assertTrue(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))
        self.assertEqual(len(_replies(update)), 1)

    async def test_posts_the_latest_patch_note_to_this_chat(self) -> None:
        older = _item("1", "Older patch", 1_000)
        newer = _item("2", "Newer patch", 2_000)
        # Deliberately not newest-first: the latest is chosen by date, not by position.
        _update, _context, _client, send = await self._run(["on"], fetched=[older, newer])
        self.assertTrue(send.await_args_list)
        for call in send.await_args_list:
            self.assertEqual(call.args[1], CHAT_ID)
        posted = "".join(call.args[2] for call in send.await_args_list)
        self.assertIn("Newer patch", posted)
        self.assertNotIn("Older patch", posted)

    async def test_does_not_touch_the_sweep_bookkeeping(self) -> None:
        _update, context, _client, _send = await self._run(["on"], fetched=[_item("1", "Patch", 1_000)])
        self.assertIsNone(context.bot_data.cs2_patchnotes_seen_gids)

    async def test_leaves_a_patch_the_sweep_has_not_announced_yet_to_the_sweep(self) -> None:
        # Posting it here too would give this chat the same patch twice once the sweep runs.
        update, context = _make(["on"])
        context.bot_data.cs2_patchnotes_seen_gids = {"1"}
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(
            return_value=[_item("2", "Unannounced", 2_000), _item("1", "Old", 1_000)]
        )
        send = AsyncMock()
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)
        send.assert_not_awaited()
        self.assertTrue(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))
        self.assertEqual(context.bot_data.cs2_patchnotes_seen_gids, {"1"})

    async def test_posts_a_latest_patch_the_sweep_already_announced(self) -> None:
        update, context = _make(["on"])
        context.bot_data.cs2_patchnotes_seen_gids = {"1", "2"}
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(return_value=[_item("2", "Announced", 2_000), _item("1", "Old", 1_000)])
        send = AsyncMock()
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)
        self.assertIn("Announced", "".join(call.args[2] for call in send.await_args_list))

    async def test_skips_a_patch_the_sweep_marks_seen_while_the_fetch_is_in_flight(self) -> None:
        # The sweep marks it seen and snapshots recipients in one step - after this chat
        # subscribed - so the sweep's broadcast includes this chat; posting here would duplicate.
        update, context = _make(["on"])
        context.bot_data.cs2_patchnotes_seen_gids = {"1"}
        items = [_item("2", "Fresh", 2_000), _item("1", "Old", 1_000)]

        async def fetch():
            context.bot_data.cs2_patchnotes_seen_gids.add("2")
            return items

        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(side_effect=fetch)
        send = AsyncMock()
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)
        send.assert_not_awaited()

    async def test_already_on_says_so_and_posts_nothing(self) -> None:
        update, context = _make(["on"])
        context.bot_data.subscribe_to_cs2_patchnotes(CHAT_ID)
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock(return_value=[_item("1", "Patch", 1_000)])
        send = AsyncMock()
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)
        (reply,) = _replies(update)
        self.assertIn("already on", reply)
        client.get_cs2_patch_notes.assert_not_awaited()
        send.assert_not_awaited()

    async def test_steam_unreachable_still_subscribes_and_posts_nothing(self) -> None:
        update, context, _client, send = await self._run(["on"], fetched=None)
        self.assertTrue(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))
        self.assertEqual(len(_replies(update)), 1)
        send.assert_not_awaited()

    async def test_no_patch_notes_in_feed_posts_nothing(self) -> None:
        _update, _context, _client, send = await self._run(["on"], fetched=[])
        send.assert_not_awaited()

    async def test_a_failed_post_does_not_undo_the_subscription(self) -> None:
        _update, context, _client, _send = await self._run(
            ["on"], fetched=[_item("1", "Patch", 1_000)], send_error=TelegramError("forbidden")
        )
        self.assertTrue(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))

    async def test_argument_is_case_insensitive(self) -> None:
        _update, context, _client, _send = await self._run(["ON"], fetched=[])
        self.assertTrue(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))


class TurnOffTest(_HandlerTestCase):
    async def test_unsubscribes_confirms_and_never_fetches(self) -> None:
        update, context = _make(["off"])
        context.bot_data.subscribe_to_cs2_patchnotes(CHAT_ID)
        client = MagicMock()
        client.get_cs2_patch_notes = AsyncMock()
        send = AsyncMock()
        with patch(f"{MODULE}.get_steam_news_client", return_value=client), patch(
            f"{MODULE}.send_html_with_fallback", send
        ):
            await callback(update, context)

        self.assertFalse(context.bot_data.is_subscribed_to_cs2_patchnotes(CHAT_ID))
        self.assertEqual(len(_replies(update)), 1)
        client.get_cs2_patch_notes.assert_not_awaited()
        send.assert_not_awaited()

    async def test_already_off_says_so(self) -> None:
        update, _context, _client, _send = await self._run(["off"])
        (reply,) = _replies(update)
        self.assertIn("already off", reply)


class RegistrationTest(unittest.TestCase):
    def test_handler_does_not_block_other_updates_while_steam_is_slow(self) -> None:
        self.assertFalse(Cs2PatchesCommandHandler().block)


class BadInputTest(_HandlerTestCase):
    async def _assert_usage_and_no_change(self, args: Optional[List[str]]) -> None:
        update, context, client, _send = await self._run(args)
        self.assertEqual(_replies(update), [CS2PATCHES.usage])
        self.assertEqual(context.bot_data.cs2_patchnotes_subscribers, set())
        client.get_cs2_patch_notes.assert_not_awaited()

    async def test_missing_argument_shows_usage(self) -> None:
        await self._assert_usage_and_no_change(None)

    async def test_unknown_argument_shows_usage(self) -> None:
        await self._assert_usage_and_no_change(["maybe"])

    async def test_extra_arguments_show_usage(self) -> None:
        await self._assert_usage_and_no_change(["on", "please"])

    async def test_does_nothing_without_a_message(self) -> None:
        update, context = _make(["on"])
        update.message = None
        await callback(update, context)
        self.assertEqual(context.bot_data.cs2_patchnotes_subscribers, set())


if __name__ == "__main__":
    unittest.main()
