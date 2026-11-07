#!/usr/bin/env python3
"""Container healthcheck for ONGAbot, built on a heartbeat file.

The bot long-polls Telegram and opens no port, so there is nothing to probe from outside.
Instead a repeating job in the bot (heartbeat_callback in ongabot.py) rewrites a heartbeat
file whenever the bot is demonstrably working: the job queue fires, the updater is polling and
Telegram answers getMe. Run as a script, this module checks how old that file is and exits 0
(healthy) or 1 (unhealthy), which is the contract Docker's HEALTHCHECK expects.

Stdlib only and free of bot imports, so the check stays cheap and cannot fail on anything but
the heartbeat itself.
"""

import datetime
import os
import sys
from pathlib import Path
from typing import Tuple

# How often the bot writes the heartbeat.
HEARTBEAT_INTERVAL = datetime.timedelta(seconds=60)
# How old the heartbeat may get before the bot counts as unhealthy: three missed beats, so a
# single network blip does not flap the status.
HEARTBEAT_MAX_AGE = datetime.timedelta(seconds=180)


def heartbeat_path() -> Path:
    """Where the heartbeat lives: next to the persistence database.

    Derived from DB_PATH so each dev bot (ongabot-<bot>.db) gets its own file, and so the
    healthcheck process, which shares the container's environment, finds the same file as the
    bot. The default must match the DB_PATH default in ongabot.main().
    """
    return Path(os.getenv("DB_PATH", "ongabot.db") + ".heartbeat")


def write_heartbeat(now: datetime.datetime) -> None:
    """Record a heartbeat. Freshness is judged by mtime; the timestamp is there for humans."""
    heartbeat_path().write_text(now.isoformat() + "\n", encoding="utf-8")


def clear_heartbeat() -> None:
    """Remove any heartbeat left by a previous process.

    `docker restart` keeps the container's filesystem, so a leftover file would otherwise
    report healthy before the restarted bot is up.
    """
    heartbeat_path().unlink(missing_ok=True)


def check(now: datetime.datetime) -> Tuple[bool, str]:
    """Whether the heartbeat is fresh as of now (aware), and a reason for the healthcheck log."""
    path = heartbeat_path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False, f"unhealthy: no heartbeat yet at {path}"
    age = now - datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
    seconds = int(age.total_seconds())
    if age > HEARTBEAT_MAX_AGE:
        return False, f"unhealthy: last heartbeat {seconds}s ago (max {int(HEARTBEAT_MAX_AGE.total_seconds())}s)"
    return True, f"healthy: last heartbeat {seconds}s ago"


def main() -> int:
    """Print the health verdict and return the exit code Docker expects (0 healthy, 1 not)."""
    healthy, reason = check(datetime.datetime.now(datetime.timezone.utc))
    # Docker keeps this output in `docker inspect` under State.Health.Log.
    print(reason)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
