import unittest
from utils import helper
from datetime import date


class NewEventCommandTest(unittest.TestCase):
    def setUp(self):
        self.upcomingTestDates = [
            (date(2021, 2, 25), date(2021, 3, 3)),
            (date(2021, 3, 12), date(2021, 3, 17)),
            (date(2021, 3, 17), date(2021, 3, 17)),
            (date(2021, 3, 18), date(2021, 3, 24)),
        ]

    def test_getUpcomingWednesdayDate(self):
        for today, expected in self.upcomingTestDates:
            result = helper.get_upcoming_wednesday_date(today)
            self.assertEqual(
                result.weekday(),
                2,
                "Wrong day of week. Should be 2 as 0 is monday and 6 is sunday",
            )
            self.assertEqual(
                result,
                expected,
                f"Wrong calculated date! Expected: {expected}. Actual: {result}",
            )


if __name__ == "__main__":
    unittest.main()
