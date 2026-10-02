#!/usr/bin/env python3
"""Tests for skills/droid-review/statusline.py: what it prints for each state a
run's metadata can be in, against fixture .droid-reviews/ folders. No droid,
no Claude Code.

    python3 .claude/skills/maintain-droid-review-skill/statusline_test.py
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "..", "..", "skills", "droid-review", "statusline.py")
sys.dont_write_bytecode = True   # no __pycache__ beside the skill
spec = importlib.util.spec_from_file_location("statusline", SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)

NOW = time.time()
DEAD_PID = 999_999  # above macOS/Linux default pid_max in practice; checked in setUp


def iso(seconds_ago):
    return (datetime.fromtimestamp(NOW - seconds_ago).astimezone()).isoformat(timespec="seconds")


def plain(lines):
    return [sl.ANSI.sub("", l) for l in lines]


class Folder:
    """A temporary repo dir holding .droid-reviews/ with the runs a test adds."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.dir = os.path.join(self.root, ".droid-reviews")
        os.makedirs(self.dir)

    def run(self, name, log=None, **meta):
        m = {"kind": "review", "status": "running", "pid": os.getpid(), "model": "glm-5.3-flash",
             "effort": "high", "started": iso(25), "finished": None,
             "files": {"review": ".droid-reviews/%s.md" % name}}
        m.update(meta)
        with open(os.path.join(self.dir, name + ".json"), "w") as f:
            json.dump(m, f)
        if log is not None:
            with open(os.path.join(self.dir, name + ".log"), "w") as f:
                f.write("\n".join(log) + "\n")

    def legacy_log(self, name, model, seconds):
        """A run from before the metadata: only a .log."""
        with open(os.path.join(self.dir, name + ".log"), "w") as f:
            f.write("[0m01s] started %s (reasoning high) session abc\n" % model)
            f.write("[0m09s] turn 1 · Read README.md\n")
            f.write("[%dm%02ds] done · 9 turns · %ds\n" % (seconds // 60, seconds % 60, seconds))

    def rows(self, columns=200):
        return plain(sl.rows(self.dir, NOW, columns))

    def close(self):
        self.tmp.cleanup()


class StatusLine(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.assertFalse(sl.alive(DEAD_PID), "pick another DEAD_PID: %d is alive" % DEAD_PID)

    def tearDown(self):
        self.f.close()

    def test_nothing_running_prints_nothing(self):
        self.f.run("old", status="ok", finished=iso(3600), duration_s=40, turns=9)
        self.assertEqual(self.f.rows(), [])

    def test_running_row_shows_model_effort_elapsed_and_activity(self):
        self.f.run("a", log=["[0m01s] started glm-5.3-flash (reasoning high) session s",
                             "[0m20s] turn 3 · Execute git diff --stat"])
        [row] = self.f.rows()
        self.assertIn("droid glm-5.3-flash high", row)
        self.assertIn("0:25", row)
        self.assertIn("turn 3 · Execute git diff --stat", row)
        self.assertNotIn("/ ~", row)   # no history: no estimate

    def test_just_started_says_starting(self):
        self.f.run("a", log=["[0m01s] started glm-5.3-flash (reasoning high) session s"])
        self.assertIn("starting", self.f.rows()[0])

    def test_estimate_is_median_of_same_model_ok_runs(self):
        for i, d in enumerate((30, 40, 300)):
            self.f.run("ok%d" % i, status="ok", finished=iso(9999), duration_s=d, turns=5)
        self.f.run("other", status="ok", model="gemini-3.8-flash", finished=iso(9999), duration_s=5)
        self.f.run("failed", status="failed", finished=iso(9999), duration_s=1)
        self.f.run("a", log=["[0m20s] turn 2 · Read x"])
        [row] = self.f.rows()
        self.assertIn("0:25 / ~0:40", row)

    def test_estimate_reads_logs_from_before_the_metadata(self):
        self.f.legacy_log("20260924-old", "glm-5.3-flash", 50)
        self.f.legacy_log("20260924-old2", "glm-5.3-flash", 70)
        self.f.run("a", log=["[0m20s] turn 2 · Read x"])
        self.assertIn("/ ~1:00", self.f.rows()[0])

    def test_bar_fills_with_time_and_turns_amber_past_the_estimate(self):
        self.assertEqual(sl.ANSI.sub("", sl.bar(20, 40)), "▓▓▓▓▓░░░░░")
        self.assertIn(sl.GREEN, sl.bar(20, 40))
        self.assertEqual(sl.ANSI.sub("", sl.bar(90, 40)), "▓" * 10)
        self.assertIn(sl.AMBER, sl.bar(90, 40))
        self.assertEqual(sl.ANSI.sub("", sl.bar(3, None)).count("▓"), 1)   # pulse

    def test_dead_process_reads_as_stopped(self):
        self.f.run("a", pid=DEAD_PID, log=["[0m20s] turn 2 · Read x"])
        [row] = self.f.rows()
        self.assertIn("stopped (its process is gone)", row)

    def test_dead_process_hidden_once_its_log_is_old(self):
        self.f.run("a", pid=DEAD_PID, log=["[0m20s] turn 2 · Read x"])
        old = NOW - 3600
        os.utime(os.path.join(self.f.dir, "a.log"), (old, old))
        self.assertEqual(self.f.rows(), [])

    def test_finished_rows_show_for_30_seconds(self):
        self.f.run("ok", status="ok", finished=iso(10), duration_s=92, turns=14)
        self.f.run("bad", status="failed", finished=iso(5), duration_s=3, error="droid reported: no auth")
        self.f.run("int", status="interrupted", finished=iso(1), duration_s=7)
        self.f.run("gone", status="ok", finished=iso(31), duration_s=1, turns=1)
        rows = self.f.rows()
        self.assertEqual(len(rows), 3)
        text = "\n".join(rows)
        self.assertIn("done in 1:32 · 14 turns · .droid-reviews/ok.md", text)
        self.assertIn("failed after 0:03  droid reported: no auth", text)
        self.assertIn("interrupted after 0:07", text)

    def test_feedback_runs_are_labelled(self):
        self.f.run("a", kind="feedback", log=["[0m20s] turn 2 · Read x"])
        self.assertIn("droid feedback glm-5.3-flash", self.f.rows()[0])

    def test_rows_line_up_across_models(self):
        self.f.run("a", started=iso(30), log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", started=iso(20), model="gemini-3.8-flash", effort=None,
                   log=["[0m20s] turn 2 · Read y"])
        a, b = self.f.rows()
        # The bar starts at the same column in both rows.
        col = lambda r: re.search(r"[▓░]", r).start()
        self.assertEqual(col(a), col(b))

    def test_rows_are_ordered_by_start(self):
        self.f.run("late", started=iso(5), model="z-model", log=["[0m01s] turn 1 · Read x"])
        self.f.run("early", started=iso(50), model="a-model", log=["[0m01s] turn 1 · Read x"])
        rows = self.f.rows()
        self.assertIn("a-model", rows[0])
        self.assertIn("z-model", rows[1])

    def test_long_rows_are_cut_to_the_width(self):
        self.f.run("a", log=["[0m20s] turn 2 · Execute " + "x" * 300])
        [row] = self.f.rows(columns=60)
        self.assertEqual(len(row), 60)
        self.assertTrue(row.endswith("…"))

    def test_fit_keeps_links_whole(self):
        t = sl.GREEN + "ok " + sl.link("abc.md", "/x/abc.md") + " and more"
        cut = sl.fit(t, 6)
        self.assertEqual(sl.ANSI.sub("", cut), "ok ab…")
        self.assertEqual(cut.count("\033]8;;"), 2)   # opened and closed

    def test_half_written_or_foreign_json_is_ignored(self):
        with open(os.path.join(self.f.dir, "junk.json"), "w") as f:
            f.write("{not json")
        with open(os.path.join(self.f.dir, "list.json"), "w") as f:
            f.write("[1, 2]")
        self.f.run("a", log=["[0m20s] turn 2 · Read x"])
        self.assertEqual(len(self.f.rows()), 1)

    def test_found_from_a_subdirectory(self):
        sub = os.path.join(self.f.root, "src", "deep")
        os.makedirs(sub)
        self.assertEqual(sl.find_reviews(sub), self.f.dir)


class Command(unittest.TestCase):
    """The script as Claude Code runs it: JSON on stdin, rows on stdout."""

    def run_script(self, stdin, *args, env=None):
        e = dict(os.environ, COLUMNS="120", **(env or {}))
        return subprocess.run([sys.executable, SCRIPT, *args], input=stdin, capture_output=True,
                              text=True, env=e, timeout=10)

    def test_previous_status_line_prints_first_with_the_same_input(self):
        f = Folder()
        try:
            f.run("a", log=["[0m20s] turn 2 · Read x"])
            stdin = json.dumps({"workspace": {"current_dir": f.root}})
            r = self.run_script(stdin, "--", "python3", "-c",
                                "'import sys,json; print(\"MINE\", json.load(sys.stdin)[\"workspace\"][\"current_dir\"])'")
            lines = r.stdout.splitlines()
            self.assertEqual(lines[0], "MINE " + f.root)
            self.assertIn("droid glm-5.3-flash", sl.ANSI.sub("", lines[1]))
        finally:
            f.close()

    def test_outside_a_repo_with_reviews_prints_only_the_previous_line(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_script(json.dumps({"workspace": {"current_dir": d}}), "--", "echo", "MINE")
            self.assertEqual(r.stdout, "MINE\n")
            self.assertEqual(r.returncode, 0)

    def test_bad_input_prints_nothing_and_exits_0(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, SCRIPT], input="not json", capture_output=True,
                               text=True, cwd=d, timeout=10)
            self.assertEqual((r.stdout, r.returncode), ("", 0))

    def test_fast_enough_for_a_status_line(self):
        f = Folder()
        try:
            for i in range(300):   # a long-used repo
                f.run("old%03d" % i, status="ok", finished=iso(99999), duration_s=40, turns=9)
            f.run("a", log=["[0m20s] turn 2 · Read x"])
            t = time.time()
            self.run_script(json.dumps({"workspace": {"current_dir": f.root}}))
            self.assertLess(time.time() - t, 1.0)
        finally:
            f.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
