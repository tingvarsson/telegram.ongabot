import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import scripts.devbot as devbot
from scripts.devbot import Checkout, Holder, SlotError, choose_slot

HERE = "/repo"
OTHER = "/repo/.claude/worktrees/other"


def _running(*pids):
    return lambda pid: pid in pids


class ChooseSlotTest(unittest.TestCase):
    def test_first_free_slot_when_nothing_has_run(self):
        self.assertEqual(choose_slot({"ongadev1": None, "ongadev2": None}, HERE, None), ("ongadev1", []))

    def test_skips_a_slot_another_checkout_is_running(self):
        holders = {"ongadev1": Holder(11, OTHER, "feat/a"), "ongadev2": None}
        self.assertEqual(choose_slot(holders, HERE, None, _running(11)), ("ongadev2", []))

    def test_restarting_reuses_this_checkouts_running_slot(self):
        holders = {"ongadev1": Holder(11, OTHER, "feat/a"), "ongadev2": Holder(22, HERE, "feat/b")}
        self.assertEqual(choose_slot(holders, HERE, None, _running(11, 22)), ("ongadev2", ["ongadev2"]))

    def test_reuses_the_slot_this_checkout_held_last_even_after_it_stopped(self):
        # Sticky slot: the same branch comes back in the same test chat.
        holders = {"ongadev1": None, "ongadev2": Holder(22, HERE, "feat/b")}
        self.assertEqual(choose_slot(holders, HERE, None, _running()), ("ongadev2", []))

    def test_a_dead_holder_frees_the_slot(self):
        holders = {"ongadev1": Holder(11, OTHER, "feat/a"), "ongadev2": None}
        self.assertEqual(choose_slot(holders, HERE, None, _running()), ("ongadev1", []))

    def test_both_busy_fails_and_names_both_branches(self):
        holders = {"ongadev1": Holder(11, OTHER, "feat/a"), "ongadev2": Holder(22, "/x", "feat/c")}
        with self.assertRaises(SlotError) as ctx:
            choose_slot(holders, HERE, None, _running(11, 22))
        self.assertIn("feat/a", str(ctx.exception))
        self.assertIn("feat/c", str(ctx.exception))

    def test_requested_slot_takes_over_from_another_checkout(self):
        holders = {"ongadev1": Holder(11, OTHER, "feat/a"), "ongadev2": None}
        self.assertEqual(choose_slot(holders, HERE, "ongadev1", _running(11)), ("ongadev1", ["ongadev1"]))

    def test_requested_slot_also_stops_this_checkouts_other_bot(self):
        # A checkout runs at most one bot.
        holders = {"ongadev1": Holder(11, HERE, "feat/b"), "ongadev2": Holder(22, OTHER, "feat/a")}
        self.assertEqual(
            choose_slot(holders, HERE, "ongadev2", _running(11, 22)), ("ongadev2", ["ongadev1", "ongadev2"])
        )

    def test_requested_free_slot_stops_nothing(self):
        self.assertEqual(choose_slot({"ongadev1": None, "ongadev2": None}, HERE, "ongadev2"), ("ongadev2", []))

    def test_unknown_requested_slot_is_rejected(self):
        with self.assertRaises(SlotError):
            choose_slot({"ongadev1": None, "ongadev2": None}, HERE, "prod")


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
            devbot.write_holder(main, "ongadev1", holder)
            self.assertEqual(devbot.read_holder(main, "ongadev1"), holder)

    def test_missing_or_corrupt_state_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp)
            self.assertIsNone(devbot.read_holder(main, "ongadev1"))
            state = main / ".git" / "devbot" / "ongadev1.json"
            state.parent.mkdir(parents=True)
            state.write_text("{not json")
            self.assertIsNone(devbot.read_holder(main, "ongadev1"))


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


class WorktreeDbTest(unittest.TestCase):
    def test_seeds_from_the_newest_database_in_the_main_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            main, root = Path(tmp) / "main", Path(tmp) / "wt"
            main.mkdir()
            root.mkdir()
            (main / "ongabot.db").write_text("dev")
            snapshot = main / "ongabot.db.260831"
            snapshot.write_text("snapshot")
            past = time.time() - 3600
            os.utime(main / "ongabot.db", (past, past))

            db_path, seed = devbot.ensure_worktree_db(Checkout(root=root, main=main, branch="b"))

            self.assertEqual((db_path, seed), (root / "ongabot.db", snapshot))
            self.assertEqual(db_path.read_text(), "snapshot")

    def test_existing_worktree_database_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            main, root = Path(tmp) / "main", Path(tmp) / "wt"
            main.mkdir()
            root.mkdir()
            (main / "ongabot.db").write_text("dev")
            (root / "ongabot.db").write_text("branch state")

            db_path, seed = devbot.ensure_worktree_db(Checkout(root=root, main=main, branch="b"))

            self.assertIsNone(seed)
            self.assertEqual(db_path.read_text(), "branch state")

    def test_no_seed_available_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            main, root = Path(tmp) / "main", Path(tmp) / "wt"
            main.mkdir()
            root.mkdir()
            db_path, seed = devbot.ensure_worktree_db(Checkout(root=root, main=main, branch="b"))
            self.assertIsNone(seed)
            self.assertFalse(db_path.exists())


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
            self.assertEqual(devbot.env_file(in_worktree.main, "ongadev1"), main / ".env.ongadev1")


class CliTest(unittest.TestCase):
    def test_run_without_the_slot_env_file_explains_what_to_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp).resolve()
            checkout = Checkout(root=main, main=main, branch="master")
            with self.assertRaises(SlotError) as ctx:
                devbot.cmd_run(checkout, "ongadev1")
            self.assertIn(".env.ongadev1", str(ctx.exception))
            self.assertIsNone(devbot.read_holder(main, "ongadev1"))


if __name__ == "__main__":
    unittest.main()
