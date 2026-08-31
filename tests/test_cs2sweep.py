"""The job that posts CS2 results as a follow-up to the midnight Banger Points recap.

Leetify only has a match once its demo is processed, which is usually after the recap has
already gone out - hence a repeating sweep that waits for the night's results to settle.
"""

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode
from telegram.error import TelegramError

from ongabot import ongabot
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine

EVENT_DATE = date(2026, 9, 2)


def _match(match_id):
    return Cs2Match(
        id=match_id,
        map_name="de_mirage",
        finished_at=datetime(2026, 9, 2, 21, 0),
        score=(13, 7),
        our_team=2,
        players=(
            PlayerLine("76561198000000011", "tommy", 20, 10, 2.0, 3, 2, user_id=11),
            PlayerLine("76561198000000022", "kalle", 12, 14, 0.86, 1, 2, user_id=22),
        ),
    )


def _session(match_ids):
    return Cs2Session(EVENT_DATE, [_match(match_id) for match_id in match_ids])


def _context(event=None, seen=None, deadline=None):
    event = event if event is not None else MagicMock(cs2_reported=False, event_date=EVENT_DATE)

    chat = MagicMock()
    chat.chat_id = 123
    chat.get_event_by_date.return_value = event

    context = MagicMock()
    context.bot_data.get_chat.return_value = chat
    context.bot.send_message = AsyncMock()
    context.application.user_data = {}
    context.job.chat_id = 123
    context.job.data = {
        "event_date": EVENT_DATE,
        "seen": set(seen or []),
        "deadline": deadline or (datetime.now() + timedelta(hours=14)),
    }

    return context, event


def _patch_results(session, text="RESULTS"):
    return patch("ongabot.ongabot.event_results", AsyncMock(return_value=(session, text)))


class Cs2SweepCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_a_second_matching_sweep_before_posting(self):
        """A first sighting may be mid-session; posting then would report a partial night."""
        context, event = _context()

        with _patch_results(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        self.assertEqual(context.job.data["seen"], {"m1"})
        context.job.schedule_removal.assert_not_called()

    async def test_posts_once_the_match_list_stops_growing(self):
        context, event = _context(seen=["m1"])

        with _patch_results(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_awaited_once()
        self.assertEqual(context.bot.send_message.await_args.args, (123, "RESULTS"))
        kwargs = context.bot.send_message.await_args.kwargs
        self.assertEqual(kwargs["parse_mode"], ParseMode.MARKDOWN_V2)
        self.assertTrue(kwargs["link_preview_options"].is_disabled, "Leetify links must not preview")
        event.record_cs2_session.assert_called_once_with({11, 22})
        context.job.schedule_removal.assert_called_once()

    async def test_keeps_waiting_while_new_matches_keep_appearing(self):
        context, _event = _context(seen=["m1"])

        with _patch_results(_session(["m1", "m2"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        self.assertEqual(context.job.data["seen"], {"m1", "m2"})

    async def test_keeps_waiting_when_nothing_has_been_played_yet(self):
        context, _event = _context()

        with _patch_results(_session([])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_not_called()

    async def test_retries_instead_of_giving_up_when_leetify_is_unreachable(self):
        context, _event = _context()

        with _patch_results(None, None):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_not_called()

    async def test_gives_up_quietly_when_the_deadline_passes_with_nothing_found(self):
        context, _event = _context(deadline=datetime.now() - timedelta(minutes=1))

        with _patch_results(_session([])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_posts_what_it_has_when_the_deadline_passes_with_matches_found(self):
        context, event = _context(deadline=datetime.now() - timedelta(minutes=1))

        with _patch_results(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_awaited_once()
        event.record_cs2_session.assert_called_once()
        context.job.schedule_removal.assert_called_once()

    async def test_stops_when_the_event_has_already_been_reported(self):
        context, _event = _context(event=MagicMock(cs2_reported=True, event_date=EVENT_DATE))

        with _patch_results(_session(["m1"])) as results:
            await ongabot.cs2_sweep_callback(context)

        results.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_stops_when_the_event_no_longer_exists(self):
        context, _event = _context()
        context.bot_data.get_chat.return_value.get_event_by_date.return_value = None

        with _patch_results(_session(["m1"])) as results:
            await ongabot.cs2_sweep_callback(context)

        results.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_a_failed_send_does_not_mark_the_event_as_reported(self):
        """Otherwise the results would be lost for good - the sweep must be able to retry."""
        context, event = _context(seen=["m1"])
        context.bot.send_message = AsyncMock(side_effect=TelegramError("boom"))

        with _patch_results(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        event.record_cs2_session.assert_not_called()
        context.job.schedule_removal.assert_not_called()


class ScheduleCs2SweepTest(unittest.TestCase):
    def test_schedules_a_repeating_sweep_for_the_event(self):
        job_queue = MagicMock()

        ongabot.schedule_cs2_sweep(job_queue, 123, EVENT_DATE)

        job_queue.run_repeating.assert_called_once()
        kwargs = job_queue.run_repeating.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 123)
        self.assertEqual(kwargs["data"]["event_date"], EVENT_DATE)
        self.assertEqual(kwargs["data"]["seen"], set())
        self.assertIn(str(EVENT_DATE), kwargs["name"])

    def test_is_a_no_op_without_a_job_queue(self):
        ongabot.schedule_cs2_sweep(None, 123, EVENT_DATE)


class CompletePastEventsSchedulesSweepTest(unittest.IsolatedAsyncioTestCase):
    def _context(self, cancelled=False):
        event = MagicMock()
        event.completed = False
        event.cancelled = cancelled
        event.event_date = date(2020, 1, 1)
        event.poll_id = "poll1"
        event.update_status_message = AsyncMock()

        chat = MagicMock()
        chat.chat_id = 123
        chat.events = {event.event_date: event}
        chat.remove_pinned_poll = AsyncMock()

        context = MagicMock()
        context.bot_data.chats = {123: chat}
        context.bot.send_message = AsyncMock()
        return context

    async def test_schedules_a_sweep_for_a_newly_completed_event(self):
        context = self._context()

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.complete_past_events_callback(context)

        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[1:], (123, date(2020, 1, 1)))

    async def test_does_not_schedule_a_sweep_for_a_cancelled_event(self):
        context = self._context(cancelled=True)

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.complete_past_events_callback(context)

        schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
