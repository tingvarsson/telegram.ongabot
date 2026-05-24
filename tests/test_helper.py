from ongabot.utils import helper

from datetime import date, time
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
        result = helper.get_upcoming_date(today, "wednesday")
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


class ParseDateTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("iso_date", "2026-05-07", date(2026, 5, 7)),
            ("dd_mm_yyyy", "07.05.2026", date(2026, 5, 7)),
        ]
    )
    def test_parse_date_concrete(self, _, token, expected):
        self.assertEqual(helper.parse_date(token), expected)

    @parameterized.expand(
        [
            ("monday", "monday", 0),
            ("wednesday", "wednesday", 2),
            ("sunday", "sunday", 6),
        ]
    )
    def test_parse_date_weekday(self, _, token, expected_weekday):
        self.assertEqual(helper.parse_date(token).weekday(), expected_weekday)

    @parameterized.expand(
        [
            ("empty", ""),
            ("slash_format", "2026/05/07"),
            ("nonsense", "notadate"),
            ("partial_iso", "2026-05"),
        ]
    )
    def test_parse_date_raises(self, _, token):
        with self.assertRaises(ValueError):
            helper.parse_date(token)


class ParseTimeTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("standard", "18:30", time(18, 30)),
            ("midnight", "00:00", time(0, 0)),
            ("end_of_day", "23:59", time(23, 59)),
        ]
    )
    def test_parse_time_valid(self, _, token, expected):
        self.assertEqual(helper.parse_time(token), expected)

    @parameterized.expand(
        [
            ("dot_format", "18.30"),
            ("hour_only", "18"),
            ("out_of_range", "25:00"),
            ("nonsense", "noon"),
        ]
    )
    def test_parse_time_raises(self, _, token):
        with self.assertRaises(ValueError):
            helper.parse_time(token)


class ParseNumSlotsTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("one", "1", 1),
            ("five", "5", 5),
            ("ten", "10", 10),
        ]
    )
    def test_parse_num_slots_valid(self, _, value, expected):
        self.assertEqual(helper.parse_num_slots(value), expected)

    @parameterized.expand(
        [
            ("zero", "0"),
            ("negative", "-1"),
            ("float", "1.5"),
            ("alpha", "abc"),
            ("empty", ""),
        ]
    )
    def test_parse_num_slots_raises(self, _, value):
        with self.assertRaises(ValueError):
            helper.parse_num_slots(value)


class ParseNamedArgsTest(unittest.TestCase):
    @parameterized.expand(
        [
            ("single", ["key=value"], {"key": "value"}),
            ("multiple", ["a=1", "b=2"], {"a": "1", "b": "2"}),
            ("value_with_equals", ["k=v=extra"], {"k": "v=extra"}),
            ("key_case_folded", ["KEY=val"], {"key": "val"}),
        ]
    )
    def test_parse_named_args_valid(self, _, args, expected):
        allowed = set(expected.keys())
        self.assertEqual(helper.parse_named_args(args, allowed), expected)

    @parameterized.expand(
        [
            ("no_equals", ["noequalssign"]),
            ("unknown_key", ["foo=bar"]),
            ("empty_key", ["=value"]),
        ]
    )
    def test_parse_named_args_raises(self, _, args):
        with self.assertRaises(ValueError):
            helper.parse_named_args(args, {"known"})


class ParseEventJobArgsTest(unittest.TestCase):
    DEFAULTS = ("sunday", "wednesday", time(18, 30), 5)

    def test_no_args_returns_defaults(self):
        self.assertEqual(helper.parse_event_job_args([], *self.DEFAULTS), self.DEFAULTS)

    def test_override_trigger_on(self):
        result = helper.parse_event_job_args(["trigger_on=monday"], *self.DEFAULTS)
        self.assertEqual(result[0], "monday")

    def test_override_day(self):
        result = helper.parse_event_job_args(["day=thursday"], *self.DEFAULTS)
        self.assertEqual(result[1], "thursday")

    def test_override_time(self):
        result = helper.parse_event_job_args(["time=20:00"], *self.DEFAULTS)
        self.assertEqual(result[2], time(20, 0))

    def test_override_slots(self):
        result = helper.parse_event_job_args(["slots=3"], *self.DEFAULTS)
        self.assertEqual(result[3], 3)

    def test_override_all(self):
        args = ["trigger_on=monday", "day=thursday", "time=19:00", "slots=3"]
        self.assertEqual(
            helper.parse_event_job_args(args, *self.DEFAULTS),
            ("monday", "thursday", time(19, 0), 3),
        )

    @parameterized.expand(
        [
            ("invalid_trigger_on", ["trigger_on=notaday"]),
            ("invalid_day", ["day=notaday"]),
            ("invalid_time", ["time=99:99"]),
            ("invalid_slots", ["slots=0"]),
        ]
    )
    def test_invalid_args_raise(self, _, args):
        with self.assertRaises(ValueError):
            helper.parse_event_job_args(args, *self.DEFAULTS)


class CreateHelpTextTest(unittest.TestCase):
    def test_help_text_contains_version(self):
        import ongabot
        result = helper.create_help_text()
        self.assertIn(ongabot.__version__, result)

    def test_help_text_contains_commandments_header(self):
        result = helper.create_help_text()
        self.assertIn("Commandments:", result)


if __name__ == "__main__":
    unittest.main()
