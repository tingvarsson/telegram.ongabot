"""The job that keeps an event's CS2 results message up to date through the evening.

The sweep starts when the gaming starts and posts as soon as Leetify has processed the first
demo, then edits that same message as later matches land. It stops once the match list has
been quiet long enough for the night to count as over.
"""

import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

from ongabot import ongabot
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine

EVENT_DATE = date(2026, 9, 2)
START_TIME = time(18, 30)
NEW_MESSAGE_ID = 555


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


def _context(event=None, seen=None, quiet_since=None, deadline=None, message_id=0):
    if event is None:
        event = MagicMock(cs2_reported=False, event_date=EVENT_DATE, cs2_message_id=message_id)
    event.chat_id = 123

    chat = MagicMock()
    chat.chat_id = 123
    chat.get_event_by_date.return_value = event

    context = MagicMock()
    context.bot_data.get_chat.return_value = chat
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=NEW_MESSAGE_ID))
    context.bot.edit_message_text = AsyncMock()
    context.application.user_data = {}
    context.job.chat_id = 123
    context.job.data = {
        "event_date": EVENT_DATE,
        "seen": set(seen or []),
        "quiet_since": quiet_since or datetime.now(),
        "deadline": deadline or (datetime.now() + timedelta(hours=14)),
    }

    return context, event


def _patch_session(session):
    return patch("ongabot.ongabot.event_session", AsyncMock(return_value=session))


def _settled():
    """A quiet_since far enough back that the night counts as over."""
    return datetime.now() - ongabot.CS2_SWEEP_SETTLE - timedelta(minutes=1)


class Cs2SweepCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_posts_as_soon_as_the_first_match_shows_up(self):
        """The whole point of sweeping from gaming time: results appear during the night."""
        context, event = _context()

        with _patch_session(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_awaited_once()
        self.assertEqual(context.bot.send_message.await_args.args[0], 123)
        kwargs = context.bot.send_message.await_args.kwargs
        self.assertEqual(kwargs["parse_mode"], ParseMode.MARKDOWN_V2)
        self.assertTrue(kwargs["link_preview_options"].is_disabled, "Leetify links must not preview")
        event.update_cs2_progress.assert_called_once_with(NEW_MESSAGE_ID, {11, 22})
        event.record_cs2_session.assert_not_called()
        context.job.schedule_removal.assert_not_called()

    async def test_edits_the_same_message_when_another_match_lands(self):
        """One message per night that grows, rather than one message per match."""
        context, event = _context(seen=["m1"], message_id=42)

        with _patch_session(_session(["m1", "m2"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.bot.edit_message_text.assert_awaited_once()
        self.assertEqual(context.bot.edit_message_text.await_args.kwargs["message_id"], 42)
        self.assertEqual(context.job.data["seen"], {"m1", "m2"})
        event.update_cs2_progress.assert_called_once_with(42, {11, 22})
        context.job.schedule_removal.assert_not_called()

    async def test_marks_the_message_as_live_until_the_night_is_over(self):
        context, _event = _context()

        with _patch_session(_session(["m1"])):
            with patch("ongabot.ongabot.render_results", return_value="RESULTS") as render:
                await ongabot.cs2_sweep_callback(context)

        self.assertTrue(render.call_args.kwargs["live"])

    async def test_drops_the_live_marker_on_the_final_pass(self):
        context, _event = _context(seen=["m1"], quiet_since=_settled())

        with _patch_session(_session(["m1"])):
            with patch("ongabot.ongabot.render_results", return_value="RESULTS") as render:
                await ongabot.cs2_sweep_callback(context)

        self.assertFalse(render.call_args.kwargs["live"])

    async def test_does_not_rewrite_the_message_while_the_match_list_is_unchanged(self):
        """A gap between two matches must not cost an edit every 20 minutes."""
        context, _event = _context(seen=["m1"], message_id=42)

        with _patch_session(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.edit_message_text.assert_not_awaited()
        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_not_called()

    async def test_finalises_once_the_match_list_has_been_quiet_long_enough(self):
        context, event = _context(seen=["m1"], quiet_since=_settled(), message_id=42)

        with _patch_session(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.edit_message_text.assert_awaited_once()
        event.record_cs2_session.assert_called_once_with({11, 22})
        context.job.schedule_removal.assert_called_once()

    async def test_keeps_waiting_when_nothing_has_been_played_yet(self):
        context, _event = _context()

        with _patch_session(_session([])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_not_called()

    async def test_retries_instead_of_giving_up_when_leetify_is_unreachable(self):
        context, _event = _context()

        with _patch_session(None):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_not_called()

    async def test_gives_up_when_the_deadline_passes_with_leetify_still_unreachable(self):
        context, _event = _context(deadline=datetime.now() - timedelta(minutes=1))

        with _patch_session(None):
            await ongabot.cs2_sweep_callback(context)

        context.job.schedule_removal.assert_called_once()

    async def test_gives_up_quietly_when_the_deadline_passes_with_nothing_found(self):
        context, _event = _context(deadline=datetime.now() - timedelta(minutes=1))

        with _patch_session(_session([])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_finalises_what_it_has_when_the_deadline_passes_with_matches_found(self):
        """Matches still arriving at 08:30 the next morning are not worth another 20 minutes."""
        context, event = _context(deadline=datetime.now() - timedelta(minutes=1))

        with _patch_session(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_awaited_once()
        event.record_cs2_session.assert_called_once()
        context.job.schedule_removal.assert_called_once()

    async def test_stops_when_the_event_has_already_been_reported(self):
        context, _event = _context(event=MagicMock(cs2_reported=True, event_date=EVENT_DATE))

        with _patch_session(_session(["m1"])) as session:
            await ongabot.cs2_sweep_callback(context)

        session.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_stops_when_the_event_no_longer_exists(self):
        context, _event = _context()
        context.bot_data.get_chat.return_value.get_event_by_date.return_value = None

        with _patch_session(_session(["m1"])) as session:
            await ongabot.cs2_sweep_callback(context)

        session.assert_not_awaited()
        context.job.schedule_removal.assert_called_once()

    async def test_a_failed_write_does_not_mark_the_event_as_reported(self):
        """Otherwise the results would be lost for good - the sweep must be able to retry."""
        context, event = _context(seen=["m1"], quiet_since=_settled())
        context.bot.send_message = AsyncMock(side_effect=TelegramError("boom"))

        with _patch_session(_session(["m1"])):
            await ongabot.cs2_sweep_callback(context)

        event.record_cs2_session.assert_not_called()
        event.update_cs2_progress.assert_not_called()
        context.job.schedule_removal.assert_not_called()

    async def test_posts_a_new_message_when_the_old_one_has_been_deleted(self):
        context, event = _context(seen=["m1"], message_id=42)
        context.bot.edit_message_text = AsyncMock(side_effect=BadRequest("Message to edit not found"))

        with _patch_session(_session(["m1", "m2"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_awaited_once()
        event.update_cs2_progress.assert_called_once_with(NEW_MESSAGE_ID, {11, 22})

    async def test_a_rejected_edit_is_not_replaced_by_a_new_message(self):
        """Bad markup or an over-long message would fail on a fresh send too - just retry."""
        context, event = _context(seen=["m1"], message_id=42)
        context.bot.edit_message_text = AsyncMock(side_effect=BadRequest("Can't parse entities"))

        with _patch_session(_session(["m1", "m2"])):
            await ongabot.cs2_sweep_callback(context)

        context.bot.send_message.assert_not_awaited()
        event.update_cs2_progress.assert_not_called()
        context.job.schedule_removal.assert_not_called()


class ScheduleCs2SweepTest(unittest.TestCase):
    def test_schedules_the_first_pass_at_the_events_start_time(self):
        job_queue = MagicMock()
        job_queue.get_jobs_by_name.return_value = []
        upcoming = date.today() + timedelta(days=1)

        ongabot.schedule_cs2_sweep(job_queue, 123, upcoming, START_TIME)

        job_queue.run_repeating.assert_called_once()
        kwargs = job_queue.run_repeating.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 123)
        self.assertEqual(kwargs["first"], datetime.combine(upcoming, START_TIME))
        self.assertEqual(kwargs["interval"], ongabot.CS2_SWEEP_INTERVAL)
        self.assertEqual(kwargs["data"]["event_date"], upcoming)
        self.assertEqual(kwargs["data"]["seen"], set())
        self.assertEqual(kwargs["data"]["deadline"], datetime.combine(upcoming, START_TIME) + ongabot.CS2_SWEEP_GIVE_UP)
        self.assertIn(str(upcoming), kwargs["name"])

    def test_starts_immediately_when_the_start_time_has_already_passed(self):
        """A restart mid-evening must resume the sweep, not wait for tomorrow."""
        job_queue = MagicMock()
        job_queue.get_jobs_by_name.return_value = []
        before = datetime.now()

        ongabot.schedule_cs2_sweep(job_queue, 123, date.today() - timedelta(days=1), START_TIME)

        first = job_queue.run_repeating.call_args.kwargs["first"]
        self.assertGreaterEqual(first, before)
        self.assertLessEqual(first, datetime.now())

    def test_does_not_schedule_a_second_sweep_for_the_same_event(self):
        """The daily scheduler and the completion fallback both reach for the same event."""
        job_queue = MagicMock()
        job_queue.get_jobs_by_name.return_value = [MagicMock()]

        ongabot.schedule_cs2_sweep(job_queue, 123, EVENT_DATE, START_TIME)

        job_queue.run_repeating.assert_not_called()

    def test_is_a_no_op_without_a_job_queue(self):
        ongabot.schedule_cs2_sweep(None, 123, EVENT_DATE, START_TIME)


class ScheduleTodaysCs2SweepsTest(unittest.IsolatedAsyncioTestCase):
    def _context(self, event=None):
        chat = MagicMock()
        chat.chat_id = 123
        chat.get_event_by_date.return_value = event

        context = MagicMock()
        context.bot_data.chats = {123: chat}
        return context

    def _event(self, cancelled=False, reported=False):
        return MagicMock(cancelled=cancelled, cs2_reported=reported, start_time=START_TIME)

    async def test_schedules_a_sweep_for_todays_event(self):
        context = self._context(self._event())

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.schedule_todays_cs2_sweeps_callback(context)

        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[1:], (123, date.today(), START_TIME))

    async def test_skips_a_chat_without_an_event_today(self):
        context = self._context(None)

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.schedule_todays_cs2_sweeps_callback(context)

        schedule.assert_not_called()

    async def test_skips_a_cancelled_event(self):
        context = self._context(self._event(cancelled=True))

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.schedule_todays_cs2_sweeps_callback(context)

        schedule.assert_not_called()

    async def test_skips_an_event_whose_results_are_already_final(self):
        context = self._context(self._event(reported=True))

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.schedule_todays_cs2_sweeps_callback(context)

        schedule.assert_not_called()


class CompletePastEventsSchedulesSweepTest(unittest.IsolatedAsyncioTestCase):
    def _context(self, cancelled=False):
        event = MagicMock()
        event.completed = False
        event.cancelled = cancelled
        event.event_date = date(2020, 1, 1)
        event.start_time = START_TIME
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
        """The safety net for an event whose sweep never ran - the bot was down all evening."""
        context = self._context()

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.complete_past_events_callback(context)

        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[1:], (123, date(2020, 1, 1), START_TIME))

    async def test_does_not_schedule_a_sweep_for_a_cancelled_event(self):
        context = self._context(cancelled=True)

        with patch("ongabot.ongabot.schedule_cs2_sweep") as schedule:
            await ongabot.complete_past_events_callback(context)

        schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
