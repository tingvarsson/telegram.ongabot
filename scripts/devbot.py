#!/usr/bin/env python3
"""Run a dev instance of ONGAbot on one of the local test bots.

Each dev bot has its own env file (with that bot's API_TOKEN) in the `.env.d/`
directory of the *main* checkout, named after the bot: `.env.d/ongadev2`,
`.env.d/ongadev3`, ... Every file there is a slot; add or remove a bot by adding
or removing its file.

`make run` picks a slot, starts the bot from the current checkout (the main one
or any worktree) and records who holds the slot. That way several branches can
be tested live at the same time without two processes polling the same token,
which Telegram rejects with a `Conflict` error.

Slot choice when no slot is named:
  1. the slot this checkout held last, so a restart lands in the same test chat
  2. otherwise the first free slot, in name order
  3. if every slot is busy with another checkout, fail and say who holds them;
     another branch's bot is never stopped silently
Naming a slot (`make run BOT=ongadev3`) takes it over, stopping whatever runs on it.

Each checkout keeps one database per bot, `<checkout>/ongabot-<bot>.db`, which starts
empty and persists across restarts. Bot data is tied to the bot's own chats, so bots
never share a database, and a branch never touches another checkout's data. DB_PATH
in an env file is ignored here. Put the test group in AUTHORIZED_CHAT_IDS in the bot's
env file so an empty database is authorized from the first start.

Usage:
    python scripts/devbot.py run [--bot NAME]
    python scripts/devbot.py stop [--bot NAME]
    python scripts/devbot.py status
    python scripts/devbot.py env-file [--bot NAME]
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

ENV_DIR = ".env.d"
# A slot name is the env file's name; anything else in .env.d (dotfiles, editor backups) is ignored.
SLOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BOT_SCRIPT = "ongabot/ongabot.py"
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
    return main / ENV_DIR / slot


def discover_slots(main: Path) -> list[str]:
    """Return the configured dev bots: the env files in .env.d/, in name order.

    Only names are listed; the files themselves hold tokens and are not read here.
    """
    env_dir = main / ENV_DIR
    if not env_dir.exists():
        return []
    try:
        entries = list(env_dir.iterdir())
    except OSError as e:
        # Seen when a sandbox blocks reads of .env.d: say so rather than claiming no bots exist.
        raise SlotError(f"Cannot list {env_dir}: {e.strerror}. Run this outside the sandbox.") from e
    return sorted(path.name for path in entries if not path.is_dir() and SLOT_NAME.match(path.name))


def legacy_env_files(main: Path) -> list[str]:
    """Top-level .env / .env.<bot> files from before .env.d/, so the error can say what to move."""
    # not is_dir() rather than is_file(): a sandbox masks a blocked file as a device node.
    return sorted(path.name for path in main.glob(".env*") if not path.is_dir() and path.name != ".env.example")


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


def _check_known(slot: str, slots: list[str]) -> None:
    if slot not in slots:
        known = ", ".join(slots) or "none"
        raise SlotError(f"No dev bot '{slot}' (configured in {ENV_DIR}/: {known})")


def choose_slot(
    slots: list[str],
    holders: dict[str, Holder | None],
    checkout: str,
    requested: str | None,
    running: Callable[[int], bool] = is_running,
) -> tuple[str, list[str]]:
    """Return the slot to run on and the slots whose bot must be stopped first."""
    if not slots:
        raise SlotError(f"No dev bots configured: add one env file per bot to {ENV_DIR}/ in the main checkout")
    live = {slot: holder for slot, holder in holders.items() if holder is not None and running(holder.pid)}
    # A checkout runs at most one bot, so moving it to another slot stops its old one.
    own_live = [slot for slot, holder in live.items() if holder.checkout == checkout]

    if requested is not None:
        _check_known(requested, slots)
        to_stop = set(own_live)
        if requested in live:
            to_stop.add(requested)
        return requested, sorted(to_stop)

    for slot in slots:
        holder = holders.get(slot)
        if holder is not None and holder.checkout == checkout:
            return slot, [slot] if slot in live else []
    for slot in slots:
        if slot not in live:
            return slot, []
    busy = ", ".join(f"{slot} runs {live[slot].branch} ({live[slot].checkout})" for slot in slots)
    raise SlotError(f"All dev bots are busy: {busy}. Stop one, or take one over with `make run BOT=<name>`.")


def db_path(checkout: Checkout, slot: str) -> Path:
    """This checkout's database for `slot`; the bot creates it empty on first start."""
    return checkout.root / f"ongabot-{slot}.db"


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


def _suggested_slot(legacy_name: str) -> str:
    """`.env.ongadev2` becomes `ongadev2`; a bare `.env` has no bot name to offer."""
    return legacy_name.removeprefix(".env.") if legacy_name != ".env" else "<botname>"


def _slots(main: Path) -> list[str]:
    slots = discover_slots(main)
    if not slots and (legacy := legacy_env_files(main)):
        moves = ", ".join(f"{name} → {ENV_DIR}/{_suggested_slot(name)}" for name in legacy)
        raise SlotError(f"No dev bots in {ENV_DIR}/ yet. Move the env files there, named after the bot: {moves}")
    return slots


def _holders(main: Path, slots: list[str]) -> dict[str, Holder | None]:
    return {slot: read_holder(main, slot) for slot in slots}


def _stop_slots(holders: dict[str, Holder | None], slots: list[str]) -> None:
    for slot in slots:
        holder = holders[slot]
        if holder is None:
            continue
        print(f"Stopping {slot} (pid {holder.pid}, {holder.branch})", flush=True)
        stop_pid(holder.pid)


def cmd_run(checkout: Checkout, requested: str | None) -> int:
    slots = _slots(checkout.main)
    holders = _holders(checkout.main, slots)
    slot, to_stop = choose_slot(slots, holders, str(checkout.root), requested)
    _stop_slots(holders, to_stop)

    env = dict(os.environ)
    env.update(parse_env_file(env_file(checkout.main, slot).read_text()))
    env.setdefault("CHANGELOG_PATH", str(checkout.root / "CHANGELOG.md"))
    database = db_path(checkout, slot)
    if env.get("DB_PATH") not in (None, "", str(database)):
        print(f"Ignoring DB_PATH={env['DB_PATH']} from {ENV_DIR}/{slot}: each bot uses its own database", flush=True)
    env["DB_PATH"] = str(database)
    print(f"Database: {database}{'' if database.exists() else ' (new, empty)'}", flush=True)

    # exec keeps the pid, so the recorded pid is the bot process itself and `stop` can signal it.
    write_holder(checkout.main, slot, Holder(pid=os.getpid(), checkout=str(checkout.root), branch=checkout.branch))
    print(f"{slot} → {checkout.branch} ({checkout.root})", flush=True)
    os.chdir(checkout.root)
    os.execve(sys.executable, [sys.executable, BOT_SCRIPT], env)
    return 0  # not reached


def cmd_stop(checkout: Checkout, requested: str | None) -> int:
    slots = _slots(checkout.main)
    holders = _holders(checkout.main, slots)
    if requested is not None:
        _check_known(requested, slots)
        targets = [requested]
    else:
        root = str(checkout.root)
        targets = [slot for slot, holder in holders.items() if holder is not None and holder.checkout == root]
    live = [slot for slot in targets if (holder := holders[slot]) is not None and is_running(holder.pid)]
    if not live:
        print("No dev bot running for this checkout" if requested is None else f"{requested} is not running")
        return 0
    _stop_slots(holders, live)
    return 0


def cmd_status(checkout: Checkout) -> int:
    slots = _slots(checkout.main)
    if not slots:
        print(f"No dev bots configured: add one env file per bot to {checkout.main / ENV_DIR}/")
        return 0
    for slot in slots:
        holder = read_holder(checkout.main, slot)
        if holder is not None and is_running(holder.pid):
            print(f"{slot}: running pid {holder.pid}, {holder.branch} ({holder.checkout})")
        elif holder is not None:
            print(f"{slot}: free (last: {holder.branch})")
        else:
            print(f"{slot}: free")
    return 0


def cmd_env_file(checkout: Checkout, requested: str | None) -> int:
    slots = _slots(checkout.main)
    slot, _ = choose_slot(slots, _holders(checkout.main, slots), str(checkout.root), requested)
    print(env_file(checkout.main, slot))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ONGAbot on a local dev bot.")
    parser.add_argument("command", choices=["run", "stop", "status", "env-file"])
    parser.add_argument("--bot", help=f"dev bot to use (a file name in {ENV_DIR}/); default picks one automatically")
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
