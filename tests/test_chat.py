import os
import pickle
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from ongabot.chat import SHORTS_HISTORY_DAYS, Chat
from ongabot.event import Event
from ongabot.eventdata import EventData
from ongabot.eventjob import EventJob
from ongabot.youtube.selection import PostedShort

TOKYO = ZoneInfo("Asia/Tokyo")

# The daily-Short attributes /short no longer keeps; Chat drops them when an old pickle loads.
STALE_SHORTS_ATTRS = ("topic_scores", "posted_shorts", "last_shorts_posted_date")


def _make_event(poll_id: str, event_date: date, completed: bool = False, cancelled: bool = False):
    event = MagicMock()
    event.poll_id = poll_id
    event.event_date = event_date
    event.completed = completed
    event.cancelled = cancelled
    return event


class ChatAddEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_add_new_event_succeeds(self):
        event = _make_event("p1", date(2026, 6, 4))
        result = self.chat.add_event(event)
        self.assertTrue(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], event)
        self.assertEqual(self.chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_add_rejects_active_slot_returns_false(self):
        active = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(active)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event)
        self.assertFalse(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], active)

    def test_add_cancelled_slot_without_force_returns_none(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        self.chat.add_event(cancelled)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event, force=False)
        self.assertIsNone(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], cancelled)

    def test_add_cancelled_slot_with_force_replaces_old(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        self.chat.add_event(cancelled)
        new_event = _make_event("p2", date(2026, 6, 4))
        result = self.chat.add_event(new_event, force=True)
        self.assertTrue(result)
        self.assertIs(self.chat.events[date(2026, 6, 4)], new_event)
        self.assertNotIn("p1", self.chat._poll_id_index)
        self.assertEqual(self.chat._poll_id_index["p2"], date(2026, 6, 4))


class ChatRemoveEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_remove_event_clears_both_structures(self):
        event = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(event)
        self.chat.remove_event("p1")
        self.assertNotIn(date(2026, 6, 4), self.chat.events)
        self.assertNotIn("p1", self.chat._poll_id_index)

    def test_remove_unknown_poll_id_does_not_raise(self):
        self.chat.remove_event("nonexistent")


class ChatGetEventTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)
        self.event = _make_event("p1", date(2026, 6, 4))
        self.chat.add_event(self.event)

    def test_get_event_by_poll_id_returns_event(self):
        self.assertIs(self.chat.get_event_by_poll_id("p1"), self.event)

    def test_get_event_by_poll_id_returns_none_for_unknown(self):
        self.assertIsNone(self.chat.get_event_by_poll_id("unknown"))

    def test_get_event_by_date_returns_event(self):
        self.assertIs(self.chat.get_event_by_date(date(2026, 6, 4)), self.event)

    def test_get_event_by_date_returns_none_for_unknown(self):
        self.assertIsNone(self.chat.get_event_by_date(date(2026, 1, 1)))


class ChatActiveEventsTest(unittest.TestCase):
    def test_active_events_excludes_completed(self):
        chat = Chat(chat_id=1)
        active = _make_event("p1", date(2026, 6, 4), completed=False)
        completed = _make_event("p2", date(2026, 6, 11), completed=True)
        chat.add_event(active)
        chat.add_event(completed)
        self.assertEqual(chat.active_events, [active])


class ChatSetStateMigrationTest(unittest.TestCase):
    def test_migrates_str_keyed_events_to_date_keyed(self):
        event = _make_event("p1", date(2026, 6, 4))
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertIs(chat.events[date(2026, 6, 4)], event)
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_migrates_collision_keeps_active_over_cancelled(self):
        cancelled = _make_event("p1", date(2026, 6, 4), completed=True, cancelled=True)
        active = _make_event("p2", date(2026, 6, 4), completed=False)
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": cancelled, "p2": active},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIs(chat.events[date(2026, 6, 4)], active)
        self.assertNotIn("p1", chat._poll_id_index)
        self.assertIn("p2", chat._poll_id_index)

    def test_rebuilds_poll_id_index_when_missing(self):
        event = _make_event("p1", date(2026, 6, 4))
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date(2026, 6, 4): event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))


class ChatSetStateMigrationOldEventTest(unittest.TestCase):
    def _make_real_old_event(self, poll_id: str, poll_question: str) -> Event:
        """Build a real Event in pre-EventData state (no 'data' attribute)."""
        poll = MagicMock()
        poll.id = poll_id
        poll.question = poll_question
        state = {
            "chat_id": 1,
            "poll": poll,
            "poll_id": poll_id,
            "poll_answers": {},
            "first_answer": None,
            "status_message_id": 0,
            # 'data', 'completed', 'cancelled', 'user_streaks' intentionally absent
        }
        event = Event.__new__(Event)
        event.__setstate__(state)
        return event

    def test_two_old_events_with_different_dates_migrate_without_collision(self):
        event1 = self._make_real_old_event("p1", "Event: TOGA (with ONGA)\nWhen: 2026-06-04 18:30")
        event2 = self._make_real_old_event("p2", "Event: ONGA\nWhen: 2026-06-03 18:30")

        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": event1, "p2": event2},
                "event_job": None,
                "pinned_polls": {},
            }
        )

        self.assertEqual(len(chat.events), 2)
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertIn(date(2026, 6, 3), chat.events)
        self.assertIs(chat.events[date(2026, 6, 4)], event1)
        self.assertIs(chat.events[date(2026, 6, 3)], event2)

    def test_two_old_events_with_unparseable_questions_both_kept_with_surrogate_keys(self):
        event1 = self._make_real_old_event("p1", "no when line here")
        event2 = self._make_real_old_event("p2", "also no when line")

        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {"p1": event1, "p2": event2},
                "event_job": None,
                "pinned_polls": {},
            }
        )

        # Both events must be kept — no discard
        self.assertEqual(len(chat.events), 2)
        # First event gets date.min, second gets the next surrogate date
        self.assertIn(date.min, chat.events)
        self.assertIn(date.min + timedelta(days=1), chat.events)


class ChatSetStateRetroactiveMigrationTest(unittest.TestCase):
    def _make_broken_migration_event(self, poll_id: str, poll_question: str, sentinel_date: date = date.min) -> Event:
        """Build an Event simulating the broken v1.1.0 migration: data present but event_date=sentinel."""
        poll = MagicMock()
        poll.id = poll_id
        poll.question = poll_question
        event = Event.__new__(Event)
        event.__dict__.update(
            {
                "chat_id": 1,
                "poll": poll,
                "poll_id": poll_id,
                "poll_answers": {},
                "first_answer": None,
                "status_message_id": 0,
                "data": EventData(sentinel_date),
                "completed": True,
                "cancelled": False,
                "user_streaks": {},
            }
        )
        return event

    def test_recovers_real_date_for_event_at_date_min(self):
        event = self._make_broken_migration_event("p1", "Event: ONGA\nWhen: 2026-06-04 18:30")
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date.min: event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertNotIn(date.min, chat.events)
        self.assertIs(chat.events[date(2026, 6, 4)], event)
        self.assertEqual(event.data.event_date, date(2026, 6, 4))
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_recovers_real_date_for_event_at_surrogate_date(self):
        surrogate = date.min + timedelta(days=1)
        event = self._make_broken_migration_event("p1", "Event: ONGA\nWhen: 2026-06-04 18:30", sentinel_date=surrogate)
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {surrogate: event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertNotIn(surrogate, chat.events)
        self.assertEqual(chat._poll_id_index["p1"], date(2026, 6, 4))

    def test_leaves_event_at_date_min_when_unparseable(self):
        event = self._make_broken_migration_event("p1", "no when line here")
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date.min: event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date.min, chat.events)
        self.assertIs(chat.events[date.min], event)
        self.assertEqual(event.data.event_date, date.min)

    def test_skips_recovery_when_real_date_already_occupied(self):
        sentinel_event = self._make_broken_migration_event("p1", "Event: ONGA\nWhen: 2026-06-04 18:30")
        occupant = _make_event("p2", date(2026, 6, 4), completed=True)
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date.min: sentinel_event, date(2026, 6, 4): occupant},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date.min, chat.events)
        self.assertIs(chat.events[date.min], sentinel_event)
        self.assertIs(chat.events[date(2026, 6, 4)], occupant)

    def test_does_not_affect_real_date_events(self):
        event = _make_event("p1", date(2026, 6, 4))
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {date(2026, 6, 4): event},
                "event_job": None,
                "pinned_polls": {},
            }
        )
        self.assertIn(date(2026, 6, 4), chat.events)
        self.assertIs(chat.events[date(2026, 6, 4)], event)


class ChatShortsStateTest(unittest.TestCase):
    def test_new_chat_has_no_shorts_history(self):
        chat = Chat(chat_id=1)

        self.assertEqual(chat.recent_video_ids, {})

    def test_new_chat_carries_no_daily_short_state(self):
        chat = Chat(chat_id=1)

        for stale in STALE_SHORTS_ATTRS:
            self.assertFalse(hasattr(chat, stale), stale)


class ChatRecordShortsPostTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_records_the_video_with_the_date_it_was_posted(self):
        self.chat.record_shorts_post("abc", datetime(2026, 9, 1, 12, 0))

        self.assertEqual(self.chat.recent_video_ids, {"abc": date(2026, 9, 1)})

    def test_is_recently_posted_true_for_a_tracked_video(self):
        self.chat.record_shorts_post("abc", datetime(2026, 9, 1))

        self.assertTrue(self.chat.is_recently_posted("abc"))

    def test_is_recently_posted_false_for_an_unknown_video(self):
        self.assertFalse(self.chat.is_recently_posted("xyz"))

    def test_forget_undoes_a_recorded_post(self):
        self.chat.record_shorts_post("abc", datetime(2026, 9, 1))

        self.chat.forget_shorts_post("abc")

        self.assertFalse(self.chat.is_recently_posted("abc"))

    def test_forget_of_an_unknown_video_is_a_no_op(self):
        self.chat.forget_shorts_post("xyz")

        self.assertEqual(self.chat.recent_video_ids, {})

    def test_prunes_entries_older_than_the_history_window(self):
        self.chat.record_shorts_post("old", datetime(2026, 1, 1))
        self.chat.record_shorts_post("new", datetime(2026, 1, 1) + timedelta(days=SHORTS_HISTORY_DAYS + 1))

        self.assertNotIn("old", self.chat.recent_video_ids)
        self.assertIn("new", self.chat.recent_video_ids)

    def test_keeps_entries_exactly_at_the_history_window(self):
        self.chat.record_shorts_post("edge", datetime(2026, 1, 1))
        self.chat.record_shorts_post("new", datetime(2026, 1, 1) + timedelta(days=SHORTS_HISTORY_DAYS))

        self.assertIn("edge", self.chat.recent_video_ids)


class ChatSetStateShortsMigrationTest(unittest.TestCase):
    def test_defaults_recent_video_ids_missing_from_an_old_pickle(self):
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {},
                "event_job": None,
                "pinned_polls": {},
            }
        )

        self.assertEqual(chat.recent_video_ids, {})

    def test_drops_the_daily_short_state_and_keeps_recent_video_ids(self):
        chat = Chat.__new__(Chat)
        chat.__setstate__(
            {
                "chat_id": 1,
                "events": {},
                "event_job": None,
                "pinned_polls": {},
                "topic_scores": {"speedrun": 5.0},
                "recent_video_ids": {"abc": date(2026, 1, 1)},
                "posted_shorts": {},
                "last_shorts_posted_date": date(2026, 1, 1),
            }
        )

        self.assertEqual(chat.recent_video_ids, {"abc": date(2026, 1, 1)})
        for stale in STALE_SHORTS_ATTRS:
            self.assertFalse(hasattr(chat, stale), stale)

    def test_loads_a_pickle_written_by_the_daily_short_version(self):
        # The pickle references youtube.selection.PostedShort, so the class has to stay
        # importable or bot_data would fail to load at startup.
        chat = Chat(chat_id=1)
        chat.recent_video_ids = {"abc": date(2026, 9, 1)}
        chat.topic_scores = {"linux": 3.0}
        chat.posted_shorts = {1: PostedShort("abc", ("linux",), datetime(2026, 9, 1, 12, 0))}
        chat.last_shorts_posted_date = date(2026, 9, 1)

        restored = pickle.loads(pickle.dumps(chat))

        self.assertEqual(restored.recent_video_ids, {"abc": date(2026, 9, 1)})
        for stale in STALE_SHORTS_ATTRS:
            self.assertFalse(hasattr(restored, stale), stale)


class ChatTimezoneTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_follows_the_bot_default_until_set(self):
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Europe/Stockholm"}):
            self.assertEqual(Chat(1).tz, ZoneInfo("Europe/Stockholm"))

    def test_own_zone_wins_over_the_bot_default(self):
        chat = Chat(1)
        chat.set_timezone("Asia/Tokyo")
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Europe/Stockholm"}):
            self.assertEqual(chat.tz, TOKYO)

    def test_reset_follows_the_bot_default_again(self):
        chat = Chat(1)
        chat.set_timezone("Asia/Tokyo")
        chat.set_timezone(None)
        self.assertEqual(chat.tz, ZoneInfo("UTC"))

    def test_a_zone_no_longer_known_falls_back_with_a_warning(self):
        chat = Chat(1)
        chat.timezone_name = "Atlantis/Lost"
        with self.assertLogs("ongabot.chat", level="WARNING"):
            self.assertEqual(chat.tz, ZoneInfo("UTC"))

    def test_now_and_today_are_in_the_chat_zone(self):
        chat = Chat(1)
        chat.set_timezone("Asia/Tokyo")
        self.assertEqual(chat.now().tzinfo, TOKYO)
        self.assertEqual(chat.today(), chat.now().date())

    def test_old_pickle_follows_the_bot_default(self):
        chat = Chat.__new__(Chat)
        chat.__setstate__({"chat_id": 1, "events": {}, "event_job": None, "pinned_polls": {}})
        self.assertIsNone(chat.timezone_name)


class ChatScheduleEventJobTest(unittest.TestCase):
    """The weekly job is scheduled in the chat's zone, and a missed trigger is caught up (Q15)."""

    # Sunday 21:00 in Tokyo: the default Sunday 20:00 trigger has just passed.
    NOW = datetime(2026, 10, 4, 21, 0, tzinfo=TOKYO)
    WEDNESDAY = date(2026, 10, 7)

    def setUp(self):
        self.chat = Chat(1)
        self.chat.set_timezone("Asia/Tokyo")
        self.chat.set_event_job(EventJob(1))
        self.chat.event_job.last_triggered_on = date(2026, 9, 27)
        self.job_queue = MagicMock()

    def test_schedules_in_the_chat_zone(self):
        job = self.chat.schedule_event_job(self.job_queue, "callback", self.NOW)

        self.assertIs(job, self.job_queue.run_daily.return_value)
        self.assertEqual(self.job_queue.run_daily.call_args.kwargs["time"].tzinfo, TOKYO)

    def test_creates_the_missed_poll_right_away(self):
        with self.assertLogs("ongabot.chat", level="INFO") as logs:
            self.chat.schedule_event_job(self.job_queue, "callback", self.NOW)

        self.job_queue.run_once.assert_called_once_with("callback", when=5, chat_id=1, name="weeky_event_1_catchup")
        self.assertTrue(any("missed" in line for line in logs.output))

    def test_no_catch_up_when_the_event_already_has_a_poll(self):
        self.chat.add_event(_make_event("p1", self.WEDNESDAY))

        self.chat.schedule_event_job(self.job_queue, "callback", self.NOW)

        self.job_queue.run_once.assert_not_called()

    def test_no_catch_up_once_the_trigger_has_run(self):
        self.chat.event_job.last_triggered_on = date(2026, 10, 4)

        self.chat.schedule_event_job(self.job_queue, "callback", self.NOW)

        self.job_queue.run_once.assert_not_called()

    def test_nothing_without_a_schedule(self):
        chat = Chat(2)
        self.assertIsNone(chat.schedule_event_job(self.job_queue, "callback", self.NOW))
        self.job_queue.run_daily.assert_not_called()


if __name__ == "__main__":
    unittest.main()
