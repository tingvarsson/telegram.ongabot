import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.devbot as devbot
from scripts.devbot import Checkout, Holder, SlotError, choose_slot

HERE = "/repo"
OTHER = "/repo/.claude/worktrees/other"
SLOTS = ["ongadev2", "ongadev3"]


def _running(*pids):
    return lambda pid: pid in pids


def _free():
    return {slot: None for slot in SLOTS}


class ChooseSlotTest(unittest.TestCase):
    def test_first_free_slot_in_name_order_when_nothing_has_run(self):
        self.assertEqual(choose_slot(SLOTS, _free(), HERE, None), ("ongadev2", []))

    def test_skips_a_slot_another_checkout_is_running(self):
        holders = {"ongadev2": Holder(11, OTHER, "feat/a"), "ongadev3": None}
        self.assertEqual(choose_slot(SLOTS, holders, HERE, None, _running(11)), ("ongadev3", []))

    def test_restarting_reuses_this_checkouts_running_slot(self):
        holders = {"ongadev2": Holder(11, OTHER, "feat/a"), "ongadev3": Holder(22, HERE, "feat/b")}
        self.assertEqual(choose_slot(SLOTS, holders, HERE, None, _running(11, 22)), ("ongadev3", ["ongadev3"]))

    def test_reuses_the_slot_this_checkout_held_last_even_after_it_stopped(self):
        # Sticky slot: the same branch comes back in the same test chat.
        holders = {"ongadev2": None, "ongadev3": Holder(22, HERE, "feat/b")}
        self.assertEqual(choose_slot(SLOTS, holders, HERE, None, _running()), ("ongadev3", []))

    def test_a_dead_holder_frees_the_slot(self):
        holders = {"ongadev2": Holder(11, OTHER, "feat/a"), "ongadev3": None}
        self.assertEqual(choose_slot(SLOTS, holders, HERE, None, _running()), ("ongadev2", []))

    def test_all_busy_fails_and_names_every_branch(self):
        holders = {"ongadev2": Holder(11, OTHER, "feat/a"), "ongadev3": Holder(22, "/x", "feat/c")}
        with self.assertRaises(SlotError) as ctx:
            choose_slot(SLOTS, holders, HERE, None, _running(11, 22))
        self.assertIn("feat/a", str(ctx.exception))
        self.assertIn("feat/c", str(ctx.exception))

    def test_any_number_of_slots(self):
        slots = ["a", "b", "c"]
        holders = {"a": Holder(1, OTHER, "x"), "b": Holder(2, "/y", "y"), "c": None}
        self.assertEqual(choose_slot(slots, holders, HERE, None, _running(1, 2)), ("c", []))

    def test_requested_slot_takes_over_from_another_checkout(self):
        holders = {"ongadev2": Holder(11, OTHER, "feat/a"), "ongadev3": None}
        self.assertEqual(choose_slot(SLOTS, holders, HERE, "ongadev2", _running(11)), ("ongadev2", ["ongadev2"]))

    def test_requested_slot_also_stops_this_checkouts_other_bot(self):
        # A checkout runs at most one bot.
        holders = {"ongadev2": Holder(11, HERE, "feat/b"), "ongadev3": Holder(22, OTHER, "feat/a")}
        self.assertEqual(
            choose_slot(SLOTS, holders, HERE, "ongadev3", _running(11, 22)), ("ongadev3", ["ongadev2", "ongadev3"])
        )

    def test_requested_free_slot_stops_nothing(self):
        self.assertEqual(choose_slot(SLOTS, _free(), HERE, "ongadev3"), ("ongadev3", []))

    def test_unknown_requested_slot_is_rejected_with_the_configured_names(self):
        with self.assertRaises(SlotError) as ctx:
            choose_slot(SLOTS, _free(), HERE, "ongadev1")
        self.assertIn("ongadev2, ongadev3", str(ctx.exception))

    def test_no_configured_slots_is_an_error(self):
        with self.assertRaises(SlotError):
            choose_slot([], {}, HERE, None)


class DiscoverSlotsTest(unittest.TestCase):
    def test_every_env_file_in_env_d_is_a_slot_in_name_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp)
            env_dir = main / ".env.d"
            env_dir.mkdir()
            for name in ["ongadev3", "ongadev2", ".hidden", "ongadev2~", "ongadev2.swp"]:
                (env_dir / name).write_text("")
            (env_dir / "subdir").mkdir()
            self.assertEqual(devbot.discover_slots(main), ["ongadev2", "ongadev3"])
            self.assertEqual(devbot.env_file(main, "ongadev3"), env_dir / "ongadev3")

    @unittest.skipIf(os.geteuid() == 0, "root can list any directory")
    def test_unreadable_env_d_is_an_error_not_an_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_dir = Path(tmp) / ".env.d"
            env_dir.mkdir()
            env_dir.chmod(0)
            try:
                with self.assertRaises(SlotError) as ctx:
                    devbot.discover_slots(Path(tmp))
                self.assertIn("outside the sandbox", str(ctx.exception))
            finally:
                env_dir.chmod(0o700)

    def test_no_env_d_means_no_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(devbot.discover_slots(Path(tmp)), [])


class ParseEnvFileTest(unittest.TestCase):
    def test_parses_keys_and_skips_comments_and_blanks(self):
        text = "# comment\n\nAPI_TOKEN=abc:def\nLOG_LEVEL=INFO\n"
        self.assertEqual(devbot.parse_env_file(text), {"API_TOKEN": "abc:def", "LOG_LEVEL": "INFO"})

    def test_strips_export_prefix_and_matching_quotes(self):
        text = "export A=1\nB=\"two words\"\nC='x'\n"
        self.assertEqual(devbot.parse_env_file(text), {"A": "1", "B": "two words", "C": "x"})

    def test_keeps_equals_signs_in_values_and_empty_values(self):
        self.assertEqual(devbot.parse_env_file("A=b=c\nB=\n"), {"A": "b=c", "B": ""})


class HolderStateTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp)
            holder = Holder(123, "/repo", "feat/x")
            devbot.write_holder(main, "ongadev2", holder)
            self.assertEqual(devbot.read_holder(main, "ongadev2"), holder)

    def test_missing_or_corrupt_state_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp)
            self.assertIsNone(devbot.read_holder(main, "ongadev2"))
            state = main / ".git" / "devbot" / "ongadev2.json"
            state.parent.mkdir(parents=True)
            state.write_text("{not json")
            self.assertIsNone(devbot.read_holder(main, "ongadev2"))


class IsRunningTest(unittest.TestCase):
    def test_dead_pid_is_not_running(self):
        proc = subprocess.Popen(["true"])
        proc.wait()
        self.assertFalse(devbot.is_running(proc.pid))

    def test_live_pid_without_the_bot_marker_is_not_a_bot(self):
        # Guards against a recycled pid being mistaken for (and signalled as) a bot.
        self.assertFalse(devbot.is_running(os.getpid(), marker="ongabot/ongabot.py-not-this-process"))

    @unittest.skipUnless(Path("/proc/self/cmdline").exists(), "needs /proc")
    def test_live_pid_with_marker_is_running(self):
        marker = Path("/proc/self/cmdline").read_bytes().split(b"\0")[0].decode()
        self.assertTrue(devbot.is_running(os.getpid(), marker=marker))


class DatabaseTest(unittest.TestCase):
    def test_one_database_per_checkout_and_bot(self):
        main, worktree = Path("/repo"), Path("/repo/.claude/worktrees/feat")
        in_main = Checkout(root=main, main=main, branch="master")
        in_worktree = Checkout(root=worktree, main=main, branch="feat")
        self.assertEqual(devbot.db_path(in_main, "ongadev2"), main / "ongabot-ongadev2.db")
        self.assertEqual(devbot.db_path(in_main, "ongadev3"), main / "ongabot-ongadev3.db")
        self.assertEqual(devbot.db_path(in_worktree, "ongadev3"), worktree / "ongabot-ongadev3.db")


class CmdRunTest(unittest.TestCase):
    def _run(self, env_text):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve()
            (main / ".env.d").mkdir()
            (main / ".env.d" / "ongadev2").write_text(env_text)
            checkout = Checkout(root=main, main=main, branch="feat")
            with patch.object(devbot.os, "execve") as execve, patch.object(devbot.os, "chdir"):
                devbot.cmd_run(checkout, None)
            holder = devbot.read_holder(main, "ongadev2")
            return main, execve.call_args.args[2], holder

    def test_starts_the_bot_with_its_env_and_its_own_database(self):
        main, env, holder = self._run("API_TOKEN=x\nAUTHORIZED_CHAT_IDS=-5119974194\n")
        self.assertEqual(env["API_TOKEN"], "x")
        self.assertEqual(env["AUTHORIZED_CHAT_IDS"], "-5119974194")
        self.assertEqual(env["DB_PATH"], str(main / "ongabot-ongadev2.db"))
        self.assertEqual(holder, Holder(os.getpid(), str(main), "feat"))

    def test_db_path_from_the_env_file_is_overridden(self):
        # .env.example sets DB_PATH=ongabot.db; honouring it would put every bot on one database.
        main, env, _ = self._run("API_TOKEN=x\nDB_PATH=ongabot.db\n")
        self.assertEqual(env["DB_PATH"], str(main / "ongabot-ongadev2.db"))


def _git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t"}
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


class FindCheckoutTest(unittest.TestCase):
    def test_main_checkout_and_worktree_share_the_main_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve() / "repo"
            main.mkdir()
            _git(main, "init", "-q", "-b", "master")
            _git(main, "commit", "-q", "--allow-empty", "-m", "init")
            worktree = main / ".claude" / "worktrees" / "feat"
            _git(main, "worktree", "add", "-q", "-b", "feat", str(worktree))

            in_main = devbot.find_checkout(main)
            in_worktree = devbot.find_checkout(worktree)

            self.assertEqual(in_main, Checkout(root=main, main=main, branch="master"))
            self.assertFalse(in_main.is_worktree)
            self.assertEqual(in_worktree, Checkout(root=worktree, main=main, branch="feat"))
            self.assertTrue(in_worktree.is_worktree)
            self.assertEqual(devbot.env_file(in_worktree.main, "ongadev2"), main / ".env.d" / "ongadev2")


class CliTest(unittest.TestCase):
    def test_run_with_only_top_level_env_files_says_to_move_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve()
            for name in [".env.ongadev2", ".env.ongadev3", ".env.example"]:
                (main / name).write_text("")
            with self.assertRaises(SlotError) as ctx:
                devbot.cmd_run(Checkout(root=main, main=main, branch="master"), None)
            message = str(ctx.exception)
            self.assertIn(".env.ongadev2 → .env.d/ongadev2", message)
            self.assertIn(".env.ongadev3 → .env.d/ongadev3", message)
            self.assertNotIn(".env.example", message)

    def test_run_with_an_unknown_bot_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve()
            (main / ".env.d").mkdir()
            (main / ".env.d" / "ongadev2").write_text("")
            with self.assertRaises(SlotError):
                devbot.cmd_run(Checkout(root=main, main=main, branch="master"), "ongadev9")
            self.assertIsNone(devbot.read_holder(main, "ongadev9"))


if __name__ == "__main__":
    unittest.main()
