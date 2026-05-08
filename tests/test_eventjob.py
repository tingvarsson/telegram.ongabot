from ongabot.eventjob import DEFAULT_TRIGGER_DAY, EventJob
from ongabot.eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME

from datetime import time
import unittest


class EventJobToEventDataTest(unittest.TestCase):
    def setUp(self):
        self.job = EventJob(chat_id=1, event_day="wednesday", start_time=time(18, 30), num_slots=5)

    def test_to_event_data_weekday(self):
        self.assertEqual(self.job.to_event_data().event_date.weekday(), 2)

    def test_to_event_data_start_time(self):
        self.assertEqual(self.job.to_event_data().start_time, time(18, 30))

    def test_to_event_data_num_slots(self):
        self.assertEqual(self.job.to_event_data().num_slots, 5)

    def test_to_event_data_reflects_job_attrs(self):
        job = EventJob(chat_id=1, event_day="friday", start_time=time(20, 0), num_slots=3)
        result = job.to_event_data()
        self.assertEqual(result.event_date.weekday(), 4)
        self.assertEqual(result.start_time, time(20, 0))
        self.assertEqual(result.num_slots, 3)


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
