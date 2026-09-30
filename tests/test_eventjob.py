from ongabot.eventjob import DEFAULT_TRIGGER_DAY, TRIGGER_TIME, EventJob, ptb_weekday
from ongabot.eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME

from datetime import date, datetime, time
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import unittest

STOCKHOLM = ZoneInfo("Europe/Stockholm")
# A Sunday; the default schedule triggers on Sundays for the Wednesday after.
SUNDAY = date(2026, 10, 4)
WEDNESDAY = date(2026, 10, 7)


class EventJobToEventDataTest(unittest.TestCase):
    def setUp(self):
        self.job = EventJob(chat_id=1, event_day="wednesday", start_time=time(18, 30), num_slots=5)

    def test_to_event_data_weekday(self):
        self.assertEqual(self.job.to_event_data(SUNDAY).event_date.weekday(), 2)

    def test_to_event_data_is_the_next_event_day_from_today(self):
        self.assertEqual(self.job.to_event_data(SUNDAY).event_date, WEDNESDAY)

    def test_to_event_data_start_time(self):
        self.assertEqual(self.job.to_event_data(SUNDAY).start_time, time(18, 30))

    def test_to_event_data_num_slots(self):
        self.assertEqual(self.job.to_event_data(SUNDAY).num_slots, 5)

    def test_to_event_data_reflects_job_attrs(self):
        job = EventJob(chat_id=1, event_day="friday", start_time=time(20, 0), num_slots=3)
        result = job.to_event_data(SUNDAY)
        self.assertEqual(result.event_date.weekday(), 4)
        self.assertEqual(result.start_time, time(20, 0))
        self.assertEqual(result.num_slots, 3)


class PtbWeekdayTest(unittest.TestCase):
    """python-telegram-bot's run_daily counts days from Sunday, not from Monday like datetime."""

    def test_maps_every_weekday(self):
        expected = {
            "sunday": 0,
            "monday": 1,
            "tuesday": 2,
            "wednesday": 3,
            "thursday": 4,
            "friday": 5,
            "saturday": 6,
        }
        for name, day in expected.items():
            with self.subTest(name=name):
                self.assertEqual(ptb_weekday(name), day)

    def test_ignores_case(self):
        self.assertEqual(ptb_weekday("Sunday"), 0)


class EventJobScheduleTest(unittest.TestCase):
    def test_runs_daily_on_the_trigger_day_at_20_local(self):
        job_queue = MagicMock()
        EventJob(chat_id=1, trigger_on="sunday").schedule(job_queue, "callback", STOCKHOLM)

        job_queue.run_daily.assert_called_once()
        args, kwargs = job_queue.run_daily.call_args
        self.assertEqual(args, ("callback",))
        self.assertEqual(kwargs["time"], TRIGGER_TIME.replace(tzinfo=STOCKHOLM))
        self.assertEqual(kwargs["days"], (0,))
        self.assertEqual(kwargs["chat_id"], 1)
        self.assertEqual(kwargs["name"], "weeky_event_1")


class MissedEventDateTest(unittest.TestCase):
    """Q15: a trigger that passed while the bot was down still gets its poll on startup."""

    def _job(self, last_triggered_on):
        job = EventJob(chat_id=1, trigger_on="sunday", event_day="wednesday")
        job.last_triggered_on = last_triggered_on
        return job

    def _at(self, day: date, hour: int) -> datetime:
        return datetime.combine(day, time(hour, 0), tzinfo=STOCKHOLM)

    def test_restart_after_the_trigger_on_the_trigger_day(self):
        job = self._job(date(2026, 9, 27))
        self.assertEqual(job.missed_event_date(self._at(SUNDAY, 21)), WEDNESDAY)

    def test_restart_days_later_before_the_event(self):
        job = self._job(date(2026, 9, 27))
        self.assertEqual(job.missed_event_date(self._at(date(2026, 10, 6), 9)), WEDNESDAY)

    def test_on_the_event_day_itself(self):
        job = self._job(date(2026, 9, 27))
        self.assertEqual(job.missed_event_date(self._at(WEDNESDAY, 9)), WEDNESDAY)

    def test_nothing_once_the_trigger_has_run(self):
        job = self._job(SUNDAY)
        self.assertIsNone(job.missed_event_date(self._at(SUNDAY, 21)))

    def test_nothing_before_the_trigger_is_due(self):
        job = self._job(date(2026, 9, 27))
        self.assertIsNone(job.missed_event_date(self._at(SUNDAY, 19)))

    def test_nothing_once_the_event_has_started(self):
        job = self._job(date(2026, 9, 27))
        self.assertIsNone(job.missed_event_date(self._at(WEDNESDAY, 23)))

    def test_nothing_once_the_event_day_has_passed(self):
        job = self._job(date(2026, 9, 27))
        self.assertIsNone(job.missed_event_date(self._at(date(2026, 10, 8), 9)))

    def test_nothing_without_a_record_of_the_last_run(self):
        """A job from before the marker existed, or a fresh /schedule, never catches up."""
        self.assertIsNone(self._job(None).missed_event_date(self._at(SUNDAY, 21)))

    def test_same_weekday_trigger_and_event(self):
        job = EventJob(chat_id=1, trigger_on="wednesday", event_day="wednesday", start_time=time(22, 0))
        job.last_triggered_on = date(2026, 9, 30)
        self.assertEqual(job.missed_event_date(self._at(WEDNESDAY, 21)), WEDNESDAY)


class EventJobSetStateTest(unittest.TestCase):
    def _make(self, state: dict) -> EventJob:
        obj = EventJob.__new__(EventJob)
        obj.__setstate__(state)
        return obj

    def test_migrates_day_to_schedule_to_trigger_on(self):
        obj = self._make({"chat_id": 1, "day_to_schedule": "monday", "job_name": "weeky_event_1"})
        self.assertEqual(obj.trigger_on, "monday")
        self.assertFalse(hasattr(obj, "day_to_schedule"))

    def test_defaults_trigger_on_when_missing_entirely(self):
        obj = self._make({"chat_id": 1, "job_name": "weeky_event_1"})
        self.assertEqual(obj.trigger_on, DEFAULT_TRIGGER_DAY)

    def test_defaults_event_day_when_missing(self):
        obj = self._make({"chat_id": 1, "trigger_on": "sunday", "job_name": "weeky_event_1"})
        self.assertEqual(obj.event_day, DEFAULT_EVENT_DAY)

    def test_defaults_start_time_when_missing(self):
        obj = self._make({"chat_id": 1, "trigger_on": "sunday", "event_day": "wednesday", "job_name": "weeky_event_1"})
        self.assertEqual(obj.start_time, DEFAULT_START_TIME)

    def test_defaults_num_slots_when_missing(self):
        obj = self._make(
            {
                "chat_id": 1,
                "trigger_on": "sunday",
                "event_day": "wednesday",
                "start_time": time(18, 30),
                "job_name": "weeky_event_1",
            }
        )
        self.assertEqual(obj.num_slots, DEFAULT_NUM_SLOTS)

    def test_defaults_last_triggered_on_when_missing(self):
        obj = self._make({"chat_id": 1, "trigger_on": "sunday", "job_name": "weeky_event_1"})
        self.assertIsNone(obj.last_triggered_on)

    def test_existing_fields_preserved(self):
        obj = self._make(
            {
                "chat_id": 1,
                "trigger_on": "friday",
                "event_day": "saturday",
                "start_time": time(20, 0),
                "num_slots": 3,
                "job_name": "weeky_event_1",
            }
        )
        self.assertEqual(obj.trigger_on, "friday")
        self.assertEqual(obj.num_slots, 3)


if __name__ == "__main__":
    unittest.main()
