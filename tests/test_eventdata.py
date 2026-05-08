from ongabot.eventdata import DEFAULT_EVENT_DAY, DEFAULT_NUM_SLOTS, DEFAULT_START_TIME, EventData

from datetime import date, time
import unittest


class EventDataDefaultsTest(unittest.TestCase):
    def test_default_start_time(self):
        self.assertEqual(EventData().start_time, DEFAULT_START_TIME)

    def test_default_num_slots(self):
        self.assertEqual(EventData().num_slots, DEFAULT_NUM_SLOTS)

    def test_default_event_date_is_upcoming_default_day(self):
        weekday_index = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }[DEFAULT_EVENT_DAY]
        self.assertEqual(EventData().event_date.weekday(), weekday_index)

    def test_explicit_values(self):
        d, t, n = date(2026, 5, 7), time(20, 0), 3
        e = EventData(d, t, n)
        self.assertEqual((e.event_date, e.start_time, e.num_slots), (d, t, n))


if __name__ == "__main__":
    unittest.main()
