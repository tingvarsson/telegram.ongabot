"""/schedule and /deschedule: create and remove a chat's weekly poll schedule."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.chat import Chat
from ongabot.eventjob import EventJob
from ongabot.handler import deschedulecommandhandler, schedulecommandhandler

CHAT_ID = 42


def _context(chat: Chat, args=None, next_t=datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc), queued_jobs=None):
    context = MagicMock()
    context.args = args or []
    context.bot_data.get_chat.return_value = chat
    context.job_queue.run_daily.return_value.next_t = next_t
    context.job_queue.get_jobs_by_name.return_value = queued_jobs if queued_jobs is not None else []
    return context


def _update():
    update = MagicMock()
    update.effective_chat.id = CHAT_ID
    update.message.reply_text = AsyncMock()
    return update


class ScheduleCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.chat = Chat(CHAT_ID)
        self.update = _update()

    def _reply(self) -> str:
        self.update.message.reply_text.assert_awaited_once()
        return self.update.message.reply_text.await_args.args[0]

    async def test_stores_the_schedule(self):
        await schedulecommandhandler.callback(self.update, _context(self.chat))

        self.assertIsNotNone(self.chat.event_job)
        self.assertIn("Poll creation scheduled every sunday", self._reply())

    async def test_failed_schedule_is_not_stored_and_its_job_is_removed(self):
        job = MagicMock()
        context = _context(self.chat, next_t=None, queued_jobs=[job])

        await schedulecommandhandler.callback(self.update, context)

        self.assertIsNone(self.chat.event_job)
        job.schedule_removal.assert_called_once()
        self.assertEqual(self._reply(), "Failed to schedule job. Please try again.")

    async def test_a_retry_after_a_failed_schedule_succeeds(self):
        await schedulecommandhandler.callback(self.update, _context(self.chat, next_t=None))
        self.update = _update()

        await schedulecommandhandler.callback(self.update, _context(self.chat))

        self.assertIn("Poll creation scheduled", self._reply())

    async def test_duplicate_argument_is_rejected(self):
        await schedulecommandhandler.callback(self.update, _context(self.chat, ["day=monday", "day=tuesday"]))

        self.assertIsNone(self.chat.event_job)
        self.assertIn("Duplicate argument key: 'day'", self._reply())


class DeScheduleCommandTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chat = Chat(CHAT_ID)
        self.update = _update()

    def _reply(self) -> str:
        self.update.message.reply_text.assert_awaited_once()
        return self.update.message.reply_text.await_args.args[0]

    async def test_nothing_to_cancel(self):
        await deschedulecommandhandler.callback(self.update, _context(self.chat))

        self.assertEqual(self._reply(), "No jobs to cancel.")

    async def test_cancels_a_queued_schedule(self):
        self.chat.set_event_job(EventJob(CHAT_ID))
        job = MagicMock()

        await deschedulecommandhandler.callback(self.update, _context(self.chat, queued_jobs=[job]))

        self.assertIsNone(self.chat.event_job)
        job.schedule_removal.assert_called_once()
        self.assertIn("Job cancelled successfully.", self._reply())

    async def test_clearing_a_schedule_with_no_queued_job_reports_success(self):
        self.chat.set_event_job(EventJob(CHAT_ID))

        with self.assertLogs(level="WARNING") as logs:
            await deschedulecommandhandler.callback(self.update, _context(self.chat, queued_jobs=[]))

        self.assertTrue(any("had no queued job" in line for line in logs.output))

        self.assertIsNone(self.chat.event_job)
        self.assertIn("Job cancelled successfully.", self._reply())
