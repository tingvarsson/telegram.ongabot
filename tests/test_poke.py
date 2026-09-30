"""The morning poke at regulars who have not voted, when no slot has a full stack yet."""

import os
import unittest
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import User
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, TelegramError

from ongabot import poke
from ongabot.chat import Chat
from ongabot.event import Event
from tests import message_fixtures

# Always a week ahead, so the poke's has-it-started check never sees it as over.
EVENT_DATE = date.today() + timedelta(weeks=1)
CHAT_ID = message_fixtures.CHAT_ID
POLL_MESSAGE_ID = 321

TOMMY, ANNA, EMILE, NASTY_USER = message_fixtures.users()


def _event(event_date: date, picks: Dict[User, Tuple[int, ...]], slot_votes: List[int] = None) -> Event:
    """An open event with picks per user; slot_votes overrides the per-slot voter counts."""
    event = message_fixtures.event(event_date, list(picks), list(picks.values()))
    event.completed = False
    if slot_votes is not None:
        for option, votes in zip(event.poll.options, slot_votes):
            option.voter_count = votes
    return event


def _chat(today: Event, history: List[Event] = ()) -> Chat:
    chat = Chat(CHAT_ID)
    for event in [*history, today]:
        chat.add_event(event)
    return chat


def _history() -> List[Event]:
    """Last week's event, where all four fixture users voted."""
    return [_event(EVENT_DATE - timedelta(weeks=1), {TOMMY: (0,), ANNA: (1,), EMILE: (3,), NASTY_USER: (0,)})]


def _member(status=ChatMemberStatus.MEMBER):
    return MagicMock(status=status)


def _context(chat: Chat, get_chat_member=None):
    context = MagicMock()
    context.bot_data.get_chat.return_value = chat
    context.bot.send_message = AsyncMock()
    context.bot.get_chat_member = get_chat_member or AsyncMock(return_value=_member())
    context.job.chat_id = CHAT_ID
    context.job.data = EVENT_DATE
    return context


class PokeLeadTimeTest(unittest.TestCase):
    def test_defaults_to_ten_hours(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(poke.poke_lead_time(), timedelta(hours=10))

    def test_env_override_allows_fractions(self):
        with patch.dict(os.environ, {"POKE_LEAD_HOURS": "0.1"}):
            self.assertEqual(poke.poke_lead_time(), timedelta(minutes=6))

    def test_bad_values_fall_back_to_the_default(self):
        for raw in ("soon", "-1", "nan", "inf"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"POKE_LEAD_HOURS": raw}):
                with self.assertLogs("ongabot.poke", level="WARNING"):
                    self.assertEqual(poke.poke_lead_time(), timedelta(hours=10))


class PokeTimeTest(unittest.TestCase):
    def test_default_start_pokes_in_the_morning(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(poke.poke_time(_event(EVENT_DATE, {})), datetime.combine(EVENT_DATE, time(8, 30)))

    def test_never_pokes_the_day_before(self):
        event = _event(EVENT_DATE, {})
        event.data.start_time = time(9, 0)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(poke.poke_time(event), datetime.combine(EVENT_DATE, time(0, 0)))


class SchedulePokeTest(unittest.TestCase):
    def setUp(self):
        self.job_queue = MagicMock()
        self.job_queue.get_jobs_by_name.return_value = []
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def _scheduled_at(self):
        self.job_queue.run_once.assert_called_once()
        kwargs = self.job_queue.run_once.call_args.kwargs
        self.assertEqual(kwargs["name"], poke.poke_job_name(CHAT_ID, EVENT_DATE))
        self.assertEqual(kwargs["data"], EVENT_DATE)
        # Aware in local time, so the JobQueue does not read a local wall-clock time as UTC.
        self.assertIsNotNone(kwargs["when"].tzinfo)
        return kwargs["when"].replace(tzinfo=None)

    def test_schedules_at_the_poke_time(self):
        poke.schedule_poke(self.job_queue, CHAT_ID, _event(EVENT_DATE, {}), datetime.combine(EVENT_DATE, time(0, 5)))
        self.assertEqual(self._scheduled_at(), datetime.combine(EVENT_DATE, time(8, 30)))

    def test_runs_right_away_when_the_poke_time_has_passed(self):
        """A restart at noon still gets the poke out before the game."""
        now = datetime.combine(EVENT_DATE, time(12, 0))
        poke.schedule_poke(self.job_queue, CHAT_ID, _event(EVENT_DATE, {}), now)
        self.assertEqual(self._scheduled_at(), now)

    def test_nothing_once_the_event_has_started(self):
        poke.schedule_poke(self.job_queue, CHAT_ID, _event(EVENT_DATE, {}), datetime.combine(EVENT_DATE, time(18, 30)))
        self.job_queue.run_once.assert_not_called()

    def test_nothing_for_a_poked_cancelled_or_completed_event(self):
        for flag in ("poked", "cancelled", "completed"):
            with self.subTest(flag=flag):
                event = _event(EVENT_DATE, {})
                setattr(event, flag, True)
                poke.schedule_poke(self.job_queue, CHAT_ID, event, datetime.combine(EVENT_DATE, time(0, 5)))
                self.job_queue.run_once.assert_not_called()

    def test_scheduling_twice_is_a_no_op(self):
        self.job_queue.get_jobs_by_name.return_value = [MagicMock()]
        poke.schedule_poke(self.job_queue, CHAT_ID, _event(EVENT_DATE, {}), datetime.combine(EVENT_DATE, time(0, 5)))
        self.job_queue.run_once.assert_not_called()


class ScheduleTodaysPokesTest(unittest.IsolatedAsyncioTestCase):
    async def test_schedules_only_chats_with_an_event_today(self):
        today = date.today()
        with_event = _chat(_event(today, {}))
        without_event = Chat(99)
        context = MagicMock()
        context.bot_data.chats = {CHAT_ID: with_event, 99: without_event}

        with patch("ongabot.poke.schedule_poke") as schedule:
            await poke.schedule_todays_pokes_callback(context)

        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[1], CHAT_ID)
        self.assertIs(schedule.call_args.args[2], with_event.get_event_by_date(today))


class RecentVotersTest(unittest.TestCase):
    def test_newest_events_first_and_each_user_once(self):
        older = _event(EVENT_DATE - timedelta(weeks=2), {ANNA: (0,), TOMMY: (0,)})
        newer = _event(EVENT_DATE - timedelta(weeks=1), {TOMMY: (1,)})
        chat = _chat(_event(EVENT_DATE, {}), [older, newer])
        self.assertEqual([user.id for user in poke.recent_voters(chat, 8)], [TOMMY.id, ANNA.id])

    def test_only_the_latest_events_count(self):
        ancient = _event(EVENT_DATE - timedelta(weeks=2), {ANNA: (0,)})
        chat = _chat(_event(EVENT_DATE, {TOMMY: (0,)}), [ancient, _event(EVENT_DATE - timedelta(weeks=1), {})])
        self.assertEqual(poke.recent_voters(chat, 2), [TOMMY])

    def test_cancelled_events_are_skipped(self):
        cancelled = _event(EVENT_DATE - timedelta(weeks=1), {ANNA: (0,)})
        cancelled.cancelled = True
        chat = _chat(_event(EVENT_DATE, {}), [cancelled])
        self.assertEqual(poke.recent_voters(chat, 8), [])


class EventHelpersTest(unittest.TestCase):
    def test_full_stack_counts_time_slots_only(self):
        """Five No-op votes are not a stack."""
        event = _event(EVENT_DATE, {}, slot_votes=[4, 4, 4, 5, 5])
        self.assertFalse(event.has_full_stack(5))
        event.poll.options[1].voter_count = 5
        self.assertTrue(event.has_full_stack(5))

    def test_a_retracted_vote_is_not_a_vote(self):
        event = _event(EVENT_DATE, {TOMMY: (0,), ANNA: ()})
        self.assertEqual(event.voted_user_ids(), {TOMMY.id})

    def test_old_pickles_are_not_poked_yet(self):
        event = _event(EVENT_DATE, {})
        state = dict(event.__dict__)
        del state["poked"]
        restored = Event.__new__(Event)
        restored.__setstate__(state)
        self.assertFalse(restored.poked)


class PokeCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_pokes_the_regulars_who_have_not_voted(self):
        chat = _chat(_event(EVENT_DATE, {TOMMY: (0,), ANNA: ()}), _history())
        chat.pinned_polls[chat.get_event_by_date(EVENT_DATE).poll_id] = MagicMock(message_id=POLL_MESSAGE_ID)
        context = _context(chat)

        with self.assertLogs("ongabot.poke", level="INFO") as logs:
            await poke.poke_callback(context)

        context.bot.send_message.assert_awaited_once()
        args, kwargs = context.bot.send_message.call_args
        self.assertEqual(args[0], CHAT_ID)
        text = args[1]
        # Anna retracted, so she is poked too; Tommy voted, so he is not.
        for user in (ANNA, EMILE, NASTY_USER):
            self.assertIn(f"tg://user?id={user.id}", text)
        self.assertNotIn(f"tg://user?id={TOMMY.id}", text)
        self.assertEqual(kwargs["parse_mode"], ParseMode.HTML)
        self.assertEqual(kwargs["reply_parameters"].message_id, POLL_MESSAGE_ID)
        self.assertTrue(kwargs["reply_parameters"].allow_sending_without_reply)
        self.assertTrue(chat.get_event_by_date(EVENT_DATE).poked)
        self.assertIn("Poked 3 member(s)", "\n".join(logs.output))

    async def test_no_reply_when_the_poll_is_no_longer_pinned(self):
        context = _context(_chat(_event(EVENT_DATE, {}), _history()))
        await poke.poke_callback(context)
        self.assertIsNone(context.bot.send_message.call_args.kwargs["reply_parameters"])

    async def test_unverified_members_keep_their_badge(self):
        chat = _chat(_event(EVENT_DATE, {}), _history())
        chat.set_unverified(ANNA.id, "Anna", True)
        context = _context(chat)
        await poke.poke_callback(context)
        self.assertIn(f"🔞 {ANNA.mention_html()}", context.bot.send_message.call_args.args[1])

    async def test_silent_when_a_slot_has_a_full_stack(self):
        chat = _chat(_event(EVENT_DATE, {}, slot_votes=[5, 0, 0, 0, 0]), _history())
        context = _context(chat)

        with self.assertLogs("ongabot.poke", level="INFO") as logs:
            await poke.poke_callback(context)

        context.bot.send_message.assert_not_awaited()
        self.assertTrue(chat.get_event_by_date(EVENT_DATE).poked)
        self.assertIn("full stack", "\n".join(logs.output))

    async def test_silent_when_every_regular_has_voted(self):
        everyone = {user: (0,) for user in message_fixtures.users()}
        chat = _chat(_event(EVENT_DATE, everyone, slot_votes=[4, 0, 0, 0, 0]), _history())
        context = _context(chat)

        await poke.poke_callback(context)

        context.bot.send_message.assert_not_awaited()
        self.assertTrue(chat.get_event_by_date(EVENT_DATE).poked)

    async def test_claimed_before_the_lookups_so_a_rerun_cannot_double_ping(self):
        chat = _chat(_event(EVENT_DATE, {}), _history())
        event = chat.get_event_by_date(EVENT_DATE)
        seen = []

        async def lookup(_chat_id, _user_id):
            seen.append(event.poked)
            return _member()

        await poke.poke_callback(_context(chat, AsyncMock(side_effect=lookup)))

        self.assertTrue(seen)
        self.assertTrue(all(seen))

    async def test_skips_an_event_that_has_started(self):
        """An /updateevent to an earlier start leaves the job at the old time."""
        today = date.today()
        chat = _chat(_event(today, {}), [_event(today - timedelta(weeks=1), {TOMMY: (0,)})])
        chat.get_event_by_date(today).data.start_time = time.min
        context = _context(chat)
        context.job.data = today

        with self.assertLogs("ongabot.poke", level="INFO") as logs:
            await poke.poke_callback(context)

        context.bot.send_message.assert_not_awaited()
        self.assertIn("has started", "\n".join(logs.output))

    async def test_restricted_members_are_pinged_only_while_in_the_group(self):
        def lookup(_chat_id, user_id):
            member = _member(ChatMemberStatus.RESTRICTED)
            member.is_member = user_id != ANNA.id
            return member

        chat = _chat(_event(EVENT_DATE, {}), _history())
        context = _context(chat, AsyncMock(side_effect=lookup))

        await poke.poke_callback(context)

        text = context.bot.send_message.call_args.args[1]
        self.assertNotIn(f"tg://user?id={ANNA.id}", text)
        self.assertIn(f"tg://user?id={TOMMY.id}", text)

    async def test_members_who_left_are_not_pinged(self):
        statuses = {ANNA.id: ChatMemberStatus.LEFT, EMILE.id: ChatMemberStatus.BANNED}
        chat = _chat(_event(EVENT_DATE, {}), _history())
        get_member = AsyncMock(side_effect=lambda _chat_id, user_id: _member(statuses.get(user_id, "member")))
        context = _context(chat, get_member)

        await poke.poke_callback(context)

        text = context.bot.send_message.call_args.args[1]
        self.assertNotIn(f"tg://user?id={ANNA.id}", text)
        self.assertNotIn(f"tg://user?id={EMILE.id}", text)
        self.assertIn(f"tg://user?id={TOMMY.id}", text)

    async def test_a_failed_membership_check_still_pokes(self):
        chat = _chat(_event(EVENT_DATE, {}), _history())
        context = _context(chat, AsyncMock(side_effect=BadRequest("chat not found")))

        with self.assertLogs("ongabot.poke", level="WARNING"):
            await poke.poke_callback(context)

        self.assertIn(f"tg://user?id={TOMMY.id}", context.bot.send_message.call_args.args[1])

    async def test_a_failed_send_is_retried_by_the_next_pass(self):
        chat = _chat(_event(EVENT_DATE, {}), _history())
        context = _context(chat)
        context.bot.send_message.side_effect = TelegramError("flood")

        with self.assertLogs("ongabot.poke", level="WARNING"):
            await poke.poke_callback(context)

        self.assertFalse(chat.get_event_by_date(EVENT_DATE).poked)

    async def test_skips_an_event_that_closed_meanwhile(self):
        for flag in ("poked", "cancelled", "completed"):
            with self.subTest(flag=flag):
                chat = _chat(_event(EVENT_DATE, {}), _history())
                setattr(chat.get_event_by_date(EVENT_DATE), flag, True)
                context = _context(chat)
                await poke.poke_callback(context)
                context.bot.send_message.assert_not_awaited()

    async def test_skips_an_event_that_is_gone(self):
        context = _context(Chat(CHAT_ID))
        await poke.poke_callback(context)
        context.bot.send_message.assert_not_awaited()

    async def test_logs_an_error_without_a_job(self):
        context = MagicMock()
        context.job = None
        with self.assertLogs("ongabot.poke", level="ERROR"):
            await poke.poke_callback(context)
