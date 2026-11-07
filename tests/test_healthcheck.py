import datetime
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ongabot import healthcheck

UTC = datetime.timezone.utc


class HealthcheckTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmp.cleanup)
        self.db_path = os.path.join(tmp.name, "ongabot-dev.db")
        env = patch.dict(os.environ, {"DB_PATH": self.db_path})
        env.start()
        self.addCleanup(env.stop)
        self.heartbeat = Path(self.db_path + ".heartbeat")

    def _age_heartbeat(self, seconds: float) -> datetime.datetime:
        """Write a heartbeat and backdate its mtime; returns the "now" to check against."""
        # Whole seconds, so the float mtime round-trips exactly and the age prints as given.
        now = datetime.datetime.now(UTC).replace(microsecond=0)
        healthcheck.write_heartbeat(now)
        then = (now - datetime.timedelta(seconds=seconds)).timestamp()
        os.utime(self.heartbeat, (then, then))
        return now

    def test_heartbeat_lives_next_to_the_database(self):
        self.assertEqual(healthcheck.heartbeat_path(), self.heartbeat)

    def test_default_path_follows_the_default_database(self):
        with patch.dict(os.environ, clear=True):
            self.assertEqual(healthcheck.heartbeat_path(), Path("ongabot.db.heartbeat"))

    def test_write_records_the_timestamp(self):
        now = datetime.datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
        healthcheck.write_heartbeat(now)
        self.assertEqual(self.heartbeat.read_text(encoding="utf-8").strip(), now.isoformat())

    def test_missing_heartbeat_is_unhealthy(self):
        healthy, reason = healthcheck.check(datetime.datetime.now(UTC))
        self.assertFalse(healthy)
        self.assertIn("no heartbeat yet", reason)

    def test_fresh_heartbeat_is_healthy(self):
        now = self._age_heartbeat(30)
        healthy, reason = healthcheck.check(now)
        self.assertTrue(healthy)
        self.assertIn("30s ago", reason)

    def test_stale_heartbeat_is_unhealthy(self):
        now = self._age_heartbeat(healthcheck.HEARTBEAT_MAX_AGE.total_seconds() + 60)
        healthy, reason = healthcheck.check(now)
        self.assertFalse(healthy)
        self.assertIn("max 180s", reason)

    def test_max_age_tolerates_missed_beats(self):
        self.assertGreaterEqual(healthcheck.HEARTBEAT_MAX_AGE, 2 * healthcheck.HEARTBEAT_INTERVAL)

    def test_clear_removes_the_heartbeat(self):
        healthcheck.write_heartbeat(datetime.datetime.now(UTC))
        healthcheck.clear_heartbeat()
        self.assertFalse(self.heartbeat.exists())

    def test_clear_without_a_heartbeat_is_a_no_op(self):
        healthcheck.clear_heartbeat()
        self.assertFalse(self.heartbeat.exists())

    def test_main_exits_zero_and_prints_reason_when_healthy(self):
        healthcheck.write_heartbeat(datetime.datetime.now(UTC))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(healthcheck.main(), 0)
        self.assertTrue(out.getvalue().startswith("healthy"))

    def test_main_exits_one_when_unhealthy(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(healthcheck.main(), 1)
        self.assertTrue(out.getvalue().startswith("unhealthy"))


if __name__ == "__main__":
    unittest.main()
