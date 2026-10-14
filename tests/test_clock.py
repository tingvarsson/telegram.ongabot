"""The bot's time source: the bot-wide default zone, zone lookup and quiet hours."""

import os
import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ongabot.utils import clock


class BotTimezoneTest(unittest.TestCase):
    def test_defaults_to_utc_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(clock.bot_timezone(), ZoneInfo("UTC"))

    def test_reads_the_env_var(self):
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Europe/Stockholm"}):
            self.assertEqual(clock.bot_timezone(), ZoneInfo("Europe/Stockholm"))

    def test_unknown_zone_warns_and_falls_back_to_utc(self):
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Mars/Olympus_Mons"}):
            with self.assertLogs("ongabot.utils.clock", level="WARNING"):
                self.assertEqual(clock.bot_timezone(), ZoneInfo("UTC"))


class ResolveTimezoneTest(unittest.TestCase):
    def test_ignores_case_and_returns_the_canonical_name(self):
        self.assertEqual(str(clock.resolve_timezone("europe/STOCKHOLM")), "Europe/Stockholm")

    def test_rejects_unknown_names(self):
        for name in ("Nowhere/Special", "", "../../etc/passwd", "/etc/localtime"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                clock.resolve_timezone(name)


STOCKHOLM = ZoneInfo("Europe/Stockholm")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 14, hour, minute, tzinfo=STOCKHOLM)


class QuietHoursTest(unittest.TestCase):
    def test_defaults_to_eleven_at_night_to_seven_in_the_morning(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(clock.quiet_hours(), (time(23, 0), time(7, 0)))

    def test_reads_the_env_var(self):
        with patch.dict(os.environ, {"QUIET_HOURS": "22:30 - 8:00"}):
            self.assertEqual(clock.quiet_hours(), (time(22, 30), time(8, 0)))

    def test_off_or_an_empty_window_turns_them_off(self):
        for raw in ("off", "OFF", "07:00-07:00"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"QUIET_HOURS": raw}):
                self.assertIsNone(clock.quiet_hours())

    def test_malformed_values_warn_and_fall_back_to_the_default(self):
        for raw in ("night", "23-07", "25:00-07:00", "23:00-07:60"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"QUIET_HOURS": raw}):
                with self.assertLogs("ongabot.utils.clock", level="WARNING"):
                    self.assertEqual(clock.quiet_hours(), (time(23, 0), time(7, 0)))


class IsQuietTest(unittest.TestCase):
    def test_default_window_wraps_past_midnight(self):
        cases = {(22, 59): False, (23, 0): True, (0, 0): True, (3, 0): True, (6, 59): True, (7, 0): False}
        with patch.dict(os.environ, {}, clear=True):
            for (hour, minute), quiet in cases.items():
                with self.subTest(at=f"{hour:02}:{minute:02}"):
                    self.assertEqual(clock.is_quiet(_at(hour, minute)), quiet)

    def test_window_that_does_not_wrap(self):
        cases = {(0, 59): False, (1, 0): True, (5, 59): True, (6, 0): False, (23, 30): False}
        with patch.dict(os.environ, {"QUIET_HOURS": "01:00-06:00"}):
            for (hour, minute), quiet in cases.items():
                with self.subTest(at=f"{hour:02}:{minute:02}"):
                    self.assertEqual(clock.is_quiet(_at(hour, minute)), quiet)

    def test_never_quiet_when_off(self):
        with patch.dict(os.environ, {"QUIET_HOURS": "off"}):
            self.assertFalse(clock.is_quiet(_at(3)))


class QuietEndTest(unittest.TestCase):
    def test_is_the_window_end_on_that_day_in_the_zone(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                clock.quiet_end(date(2026, 10, 14), STOCKHOLM), datetime(2026, 10, 14, 7, 0, tzinfo=STOCKHOLM)
            )

    def test_is_midnight_when_off(self):
        with patch.dict(os.environ, {"QUIET_HOURS": "off"}):
            self.assertEqual(
                clock.quiet_end(date(2026, 10, 14), STOCKHOLM), datetime(2026, 10, 14, 0, 0, tzinfo=STOCKHOLM)
            )


class NowTest(unittest.TestCase):
    def test_now_is_aware_in_the_given_zone(self):
        tokyo = ZoneInfo("Asia/Tokyo")
        self.assertEqual(clock.now(tokyo).tzinfo, tokyo)
        self.assertEqual(clock.today(tokyo), clock.now(tokyo).date())


if __name__ == "__main__":
    unittest.main()
