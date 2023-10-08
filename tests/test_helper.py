from togabot.utils import helper

from datetime import date
from parameterized import parameterized
import unittest


class HelperTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("next_month_thursday", date(2021, 2, 25), date(2021, 3, 4)),
            ("next_thursday", date(2021, 3, 12), date(2021, 3, 18)),
            ("today_thursday", date(2021, 3, 18), date(2021, 3, 18)),
            ("next_year_thursday", date(2020, 12, 31), date(2021, 1, 7)),
        ]
    )
    def test_getUpcomingThursdayDate(self, _, today, expected):
        result = helper.get_upcoming_date(today, "thursday")
        self.assertEqual(
            result.weekday(),
            3,
            "Wrong day of week. Should be 3 as 0 is monday and 6 is sunday",
        )
        self.assertEqual(
            result,
            expected,
            f"Wrong calculated date! Expected: {expected}. Actual: {result}",
        )


if __name__ == "__main__":
    unittest.main()
