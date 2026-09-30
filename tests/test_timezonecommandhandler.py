"""/timezone: show, set and reset the zone a chat's times are in."""

import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from ongabot.chat import Chat
from ongabot.eventjob import EventJob
from ongabot.handler.timezonecommandhandler import callback
from ongabot.utils.commands import TIMEZONE

CHAT_ID = 42
TOKYO = ZoneInfo("Asia/Tokyo")


def _context(chat: Chat, args):
    context = MagicMock()
    context.args = args
    context.bot_data.get_chat.return_value = chat
    context.job_queue.get_jobs_by_name.return_value = []
    context.job_queue.run_daily.return_value.next_t = datetime(2026, 10, 4, 20, 0, tzinfo=TOKYO)
    return context


def _update():
    update = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.message.reply_text = AsyncMock()
    return update


class TimezoneCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.chat = Chat(CHAT_ID)
        self.update = _update()

    def _reply(self) -> str:
        self.update.message.reply_text.assert_awaited_once()
        return self.update.message.reply_text.await_args.args[0]

    async def test_shows_the_bot_default_when_unset(self):
        await callback(self.update, _context(self.chat, []))

        reply = self._reply()
        self.assertIn("Timezone: UTC (bot default)", reply)
        self.assertIn("Local time:", reply)

    async def test_sets_a_zone_ignoring_case(self):
        await callback(self.update, _context(self.chat, ["asia/tokyo"]))

        self.assertEqual(self.chat.timezone_name, "Asia/Tokyo")
        self.assertIn("Timezone: Asia/Tokyo\n", self._reply())

    async def test_default_clears_the_chat_zone(self):
        self.chat.set_timezone("Asia/Tokyo")

        await callback(self.update, _context(self.chat, ["default"]))

        self.assertIsNone(self.chat.timezone_name)
        self.assertIn("(bot default)", self._reply())

    async def test_rejects_an_unknown_zone_and_keeps_the_old_one(self):
        self.chat.set_timezone("Asia/Tokyo")

        await callback(self.update, _context(self.chat, ["Mars/Base"]))

        self.assertEqual(self.chat.timezone_name, "Asia/Tokyo")
        reply = self._reply()
        self.assertIn("Unknown timezone", reply)
        self.assertIn(TIMEZONE.usage, reply)

    async def test_too_many_args_show_the_usage(self):
        await callback(self.update, _context(self.chat, ["Europe/Stockholm", "now"]))

        self.assertEqual(self._reply(), TIMEZONE.usage)
        self.assertIsNone(self.chat.timezone_name)

    async def test_moves_the_weekly_poll_to_the_new_zone(self):
        self.chat.set_event_job(EventJob(CHAT_ID))
        context = _context(self.chat, ["Asia/Tokyo"])
        old_job = MagicMock()
        context.job_queue.get_jobs_by_name.return_value = [old_job]

        await callback(self.update, context)

        old_job.schedule_removal.assert_called_once()
        self.assertEqual(context.job_queue.run_daily.call_args.kwargs["time"].tzinfo, TOKYO)
        self.assertIn("Next weekly poll: 2026-10-04 20:00 (Asia/Tokyo)", self._reply())

    async def test_no_poll_line_without_a_schedule(self):
        context = _context(self.chat, ["Asia/Tokyo"])

        await callback(self.update, context)

        context.job_queue.run_daily.assert_not_called()
        self.assertNotIn("Next weekly poll", self._reply())


if __name__ == "__main__":
    unittest.main()
