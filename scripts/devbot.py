#!/usr/bin/env python3
"""Run a dev instance of ONGAbot on one of the local test-bot slots.

There are two dev bots, each with its own token in an env file in the *main*
checkout: `.env.ongadev1` and `.env.ongadev2`. `make run` picks a slot, starts
the bot from the current checkout (the main one or any worktree) and records
who holds the slot. That way two branches can be tested live at the same time
without two processes polling the same token, which Telegram rejects with a
`Conflict` error.

Slot choice when no slot is named:
  1. the slot this checkout held last, so a restart lands in the same test chat
  2. otherwise the first free slot, ongadev1 before ongadev2
  3. if both are busy with other checkouts, fail and say who holds them;
     another branch's bot is never stopped silently
Naming a slot (`make run BOT=ongadev2`) takes it over, stopping whatever runs on it.

A worktree gets its own database (seeded from the newest ongabot.db* in the main
checkout), so a branch's pickle migrations never touch the main dev database.
The main checkout keeps using DB_PATH from its env file.

Usage:
    python scripts/devbot.py run [--bot ongadev1|ongadev2]
    python scripts/devbot.py stop [--bot ongadev1|ongadev2]
    python scripts/devbot.py status
    python scripts/devbot.py env-file [--bot ongadev1|ongadev2]
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

SLOTS = ("ongadev1", "ongadev2")
BOT_SCRIPT = "ongabot/ongabot.py"
DB_NAME = "ongabot.db"
STOP_TIMEOUT_SECONDS = 15.0


class SlotError(Exception):
    """A slot request that can't be satisfied; the message is shown to the user."""


@dataclass(frozen=True)
class Holder:
    """Who last ran a bot on a slot."""

    pid: int
    checkout: str
    branch: str


@dataclass(frozen=True)
class Checkout:
    """The checkout `make run` was invoked from."""

    root: Path  # top level of this checkout (main or worktree)
    main: Path  # main checkout: holds the env files and the slot state
    branch: str

    @property
    def is_worktree(self) -> bool:
        return self.root != self.main


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def find_checkout(cwd: Path) -> Checkout:
    """Resolve this checkout's root, the main checkout's root and the current branch."""
    root = Path(_git(cwd, "rev-parse", "--show-toplevel")).resolve()
    # The common git dir is the main checkout's .git, from the main checkout and from every worktree.
    common_dir = Path(_git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    return Checkout(root=root, main=common_dir.parent, branch=branch)


def env_file(main: Path, slot: str) -> Path:
    return main / f".env.{slot}"


def _state_file(main: Path, slot: str) -> Path:
    # Lives in the shared .git dir so every worktree sees the same slot state, and git never tracks it.
    return main / ".git" / "devbot" / f"{slot}.json"


def read_holder(main: Path, slot: str) -> Holder | None:
    try:
        data = json.loads(_state_file(main, slot).read_text())
        return Holder(pid=int(data["pid"]), checkout=str(data["checkout"]), branch=str(data["branch"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_holder(main: Path, slot: str, holder: Holder) -> None:
    path = _state_file(main, slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(holder)))


def is_running(pid: int, marker: str = BOT_SCRIPT) -> bool:
    """Return True if `pid` is alive and, where /proc exists, is actually a bot process.

    The cmdline check guards against pid reuse: a stale state file must not make an
    unrelated process look like it holds a slot, let alone get signalled by `stop`.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # alive, owned by someone else; the cmdline check below decides
    cmdline = Path(f"/proc/{pid}/cmdline")
    if not cmdline.parent.parent.exists():
        return True
    try:
        return marker in cmdline.read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False


def choose_slot(
    holders: dict[str, Holder | None],
    checkout: str,
    requested: str | None,
    running: Callable[[int], bool] = is_running,
) -> tuple[str, list[str]]:
    """Return the slot to run on and the slots whose bot must be stopped first."""
    live = {slot: holder for slot, holder in holders.items() if holder is not None and running(holder.pid)}
    # A checkout runs at most one bot, so moving it to another slot stops its old one.
    own_live = [slot for slot, holder in live.items() if holder.checkout == checkout]

    if requested is not None:
        if requested not in SLOTS:
            raise SlotError(f"Unknown bot '{requested}', expected one of: {', '.join(SLOTS)}")
        to_stop = set(own_live)
        if requested in live:
            to_stop.add(requested)
        return requested, sorted(to_stop)

    for slot in SLOTS:
        holder = holders.get(slot)
        if holder is not None and holder.checkout == checkout:
            return slot, [slot] if slot in live else []
    for slot in SLOTS:
        if slot not in live:
            return slot, []
    busy = ", ".join(f"{slot} runs {holder.branch} ({holder.checkout})" for slot, holder in sorted(live.items()))
    raise SlotError(f"Both dev bots are busy: {busy}. Stop one, or take one over with `make run BOT=<slot>`.")


def find_seed_db(main: Path) -> Path | None:
    """Return the newest ongabot.db / ongabot.db.* in the main checkout, if any."""
    candidates = [path for path in [main / DB_NAME, *main.glob(f"{DB_NAME}.*")] if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def ensure_worktree_db(checkout: Checkout) -> tuple[Path, Path | None]:
    """Return this worktree's database path and the file it was seeded from (None if it already existed)."""
    target = checkout.root / DB_NAME
    if target.exists():
        return target, None
    seed = find_seed_db(checkout.main)
    if seed is not None:
        shutil.copy2(seed, target)
    return target, seed


def parse_env_file(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines the way `set -a; . ./.env` did, without executing anything."""
    env: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        env[key] = value
    return env


def stop_pid(pid: int, timeout: float = STOP_TIMEOUT_SECONDS) -> None:
    """SIGTERM a bot (it persists its data on shutdown), escalating to SIGKILL after `timeout`."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running(pid):
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _holders(main: Path) -> dict[str, Holder | None]:
    return {slot: read_holder(main, slot) for slot in SLOTS}


def _stop_slots(main: Path, holders: dict[str, Holder | None], slots: list[str]) -> None:
    for slot in slots:
        holder = holders[slot]
        if holder is None:
            continue
        print(f"Stopping {slot} (pid {holder.pid}, {holder.branch})", flush=True)
        stop_pid(holder.pid)


def cmd_run(checkout: Checkout, requested: str | None) -> int:
    holders = _holders(checkout.main)
    slot, to_stop = choose_slot(holders, str(checkout.root), requested)
    path = env_file(checkout.main, slot)
    if not path.exists():
        raise SlotError(
            f"{path} not found. Each dev bot needs its own env file in the main checkout "
            f"(copy .env.example, or rename an existing .env to .env.{slot}), with that bot's API_TOKEN."
        )
    _stop_slots(checkout.main, holders, to_stop)

    env = dict(os.environ)
    env.update(parse_env_file(path.read_text()))
    env.setdefault("CHANGELOG_PATH", str(checkout.root / "CHANGELOG.md"))
    if checkout.is_worktree:
        db_path, seed = ensure_worktree_db(checkout)
        env["DB_PATH"] = str(db_path)
        if seed is not None:
            print(f"Seeded {db_path} from {seed}", flush=True)

    # exec keeps the pid, so the recorded pid is the bot process itself and `stop` can signal it.
    write_holder(checkout.main, slot, Holder(pid=os.getpid(), checkout=str(checkout.root), branch=checkout.branch))
    print(f"{slot} → {checkout.branch} ({checkout.root})", flush=True)
    os.chdir(checkout.root)
    os.execve(sys.executable, [sys.executable, BOT_SCRIPT], env)
    return 0  # not reached


def cmd_stop(checkout: Checkout, requested: str | None) -> int:
    holders = _holders(checkout.main)
    if requested is not None:
        if requested not in SLOTS:
            raise SlotError(f"Unknown bot '{requested}', expected one of: {', '.join(SLOTS)}")
        slots = [requested]
    else:
        root = str(checkout.root)
        slots = [slot for slot, holder in holders.items() if holder is not None and holder.checkout == root]
    live = [slot for slot in slots if (holder := holders[slot]) is not None and is_running(holder.pid)]
    if not live:
        print("No dev bot running for this checkout" if requested is None else f"{requested} is not running")
        return 0
    _stop_slots(checkout.main, holders, live)
    return 0


def cmd_status(checkout: Checkout) -> int:
    for slot in SLOTS:
        holder = read_holder(checkout.main, slot)
        missing = "" if env_file(checkout.main, slot).exists() else f"  [missing .env.{slot}]"
        if holder is not None and is_running(holder.pid):
            print(f"{slot}: running pid {holder.pid}, {holder.branch} ({holder.checkout}){missing}")
        elif holder is not None:
            print(f"{slot}: free (last: {holder.branch}){missing}")
        else:
            print(f"{slot}: free{missing}")
    return 0


def cmd_env_file(checkout: Checkout, requested: str | None) -> int:
    slot, _ = choose_slot(_holders(checkout.main), str(checkout.root), requested)
    print(env_file(checkout.main, slot))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ONGAbot on a local dev-bot slot.")
    parser.add_argument("command", choices=["run", "stop", "status", "env-file"])
    parser.add_argument("--bot", choices=SLOTS, help="slot to use; default picks one automatically")
    args = parser.parse_args(argv)

    checkout = find_checkout(Path.cwd())
    try:
        if args.command == "run":
            return cmd_run(checkout, args.bot)
        if args.command == "stop":
            return cmd_stop(checkout, args.bot)
        if args.command == "env-file":
            return cmd_env_file(checkout, args.bot)
        return cmd_status(checkout)
    except SlotError as e:
        print(f"devbot: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
