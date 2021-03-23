from ongabot.utils import helper

from datetime import date
from parameterized import parameterized
import unittest


class HelperTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("next_month_wednesday", date(2021, 2, 25), date(2021, 3, 3)),
            ("next_wednesday", date(2021, 3, 12), date(2021, 3, 17)),
            ("today_wednesday", date(2021, 3, 17), date(2021, 3, 17)),
            ("next_year_wednesday", date(2020, 12, 31), date(2021, 1, 6)),
        ]
    )
    def test_getUpcomingWednesdayDate(self, _, today, expected):
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
