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
        self.f.run("old", status="ok", finished=iso(3601), duration_s=40, turns=9)
        self.assertEqual(self.f.rows(), [])

    def test_running_row_shows_model_effort_elapsed_and_activity(self):
        self.f.run("a", log=["[0m01s] started glm-5.3-flash (reasoning high) session s",
                             "[0m20s] turn 3 · Execute git diff --stat"])
        [row] = self.f.rows()
        self.assertIn("droid-review (glm-5.3-flash high)", row)
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

    def filled(self, raw, ground):
        """How many of a bar's cells sit on a ground colour."""
        return sum(len(text) for g, text in re.findall(r"(\033\[48;[0-9;]*m)\033\[1;97m([^\033]*)", raw) if g == ground)

    def test_the_bar_is_one_piece_with_its_text_inside(self):
        b = sl.bar("0:20 / ~0:40", sl.ON_GREEN, 0.5)
        self.assertEqual(sl.ANSI.sub("", b), "[ 0:20 / ~0:40" + " " * (sl.BAR_W - 13) + "]")
        self.assertEqual(self.filled(b, sl.ON_GREEN), sl.BAR_W // 2)
        self.assertEqual(self.filled(b, sl.ON_EMPTY), sl.BAR_W - sl.BAR_W // 2)
        self.assertEqual(self.filled(sl.bar("x", sl.ON_GREEN), sl.ON_GREEN), sl.BAR_W)   # done: full
        long = sl.ANSI.sub("", sl.bar("x" * 99, sl.ON_GREEN))
        self.assertEqual(len(long), sl.BAR_W + 2)   # never wider, so rows stay lined up

    def test_bar_fills_with_time_and_turns_amber_past_the_estimate(self):
        for i, d in enumerate((40, 40)):
            self.f.run("ok%d" % i, status="ok", finished=iso(9999), duration_s=d, turns=5)
        self.f.run("a", started=iso(20), log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", started=iso(90), log=["[0m20s] turn 2 · Read x"])
        late, early = sl.rows(self.f.dir, NOW, 200)
        self.assertEqual(self.filled(early, sl.ON_GREEN), int(sl.BAR_W * 0.4))   # half the estimate
        self.assertEqual(self.filled(late, sl.ON_GREEN), 0)                        # past it: amber
        self.assertIn("[ 1:30 / ~0:40", sl.ANSI.sub("", late))

    def test_a_running_bar_stops_at_four_fifths_however_late(self):
        self.assertEqual(sl.progress(20, 40), 0.4)
        self.assertEqual(sl.progress(40, 40), 0.8)
        self.assertEqual(sl.progress(40000, 40), 0.8)
        self.f.run("ok", status="ok", finished=iso(9999), duration_s=40, turns=5)
        self.f.run("a", started=iso(40000), log=["[0m20s] turn 2 · Read x"])
        [row] = sl.rows(self.f.dir, NOW, 200)
        self.assertEqual(self.filled(row, sl.ON_AMBER), int(sl.BAR_W * 0.8))   # a thousand times over
        self.assertEqual(self.filled(row, sl.ON_EMPTY), sl.BAR_W - int(sl.BAR_W * 0.8))

    def test_no_history_a_block_drifts_across_the_bar(self):
        self.f.run("a", log=["[0m20s] turn 2 · Read x"])
        one, two = sl.rows(self.f.dir, NOW, 200)[0], sl.rows(self.f.dir, NOW + 1, 200)[0]
        self.assertEqual(self.filled(one, sl.ON_TEAL), 4)
        self.assertNotEqual(one.index(sl.ON_TEAL), two.index(sl.ON_TEAL))

    def test_feedback_is_timed_against_feedback(self):
        self.f.run("r", status="ok", finished=iso(9999), duration_s=600, turns=5)
        self.f.run("f", status="ok", kind="feedback", finished=iso(9999), duration_s=60, turns=5)
        self.f.run("a", kind="feedback", log=["[0m20s] turn 2 · Read x"])
        self.assertIn("/ ~1:00", self.f.rows()[0])

    def phase(self, *calls, quiet=0, kind="review"):
        return sl.phase(["[0m01s] started glm (reasoning high) session s"] +
                        ["[0m%02ds] turn %d · %s" % (i, turn, call) for i, (turn, call) in enumerate(calls)], quiet, kind)

    def test_phase_is_the_commonest_kind_of_call_in_the_last_turns(self):
        self.assertEqual(self.phase(), "starting")
        self.assertEqual(self.phase((1, "Skill review")), "starting")
        self.assertEqual(self.phase((1, "Read a"), (2, "Grep x"), (3, "Glob *.py")), "reading files")
        self.assertEqual(self.phase((1, "Read a"), (2, "WebSearch x"), (3, "FetchUrl http://y")), "researching")
        self.assertEqual(self.phase((1, "TodoWrite plan")), "planning")
        self.assertEqual(self.phase((1, "GenerateImage x")), "working")
        # Twenty reads long ago do not outweigh what it is doing now.
        self.assertEqual(self.phase(*[(i, "Read f") for i in range(1, 21)],
                                    (21, "Execute npm test"), (22, "Execute npm run lint"), (23, "Read out.log")), "running checks")
        self.assertEqual(self.phase((1, "Read a"), (2, "Execute npm test")), "running checks")   # a tie: the latest

    def test_phase_tells_looking_from_running_by_the_commands_first_word(self):
        for look in ("git diff --stat", "cd /repo && git log --oneline", "cat x", "FOO=1 grep -n x y", "(cd sub && ls)"):
            self.assertEqual(self.phase((1, "Execute " + look)), "reading files", look)
        for run in ("npm test", "python3 t.py", "cd /repo && .claude/skills/x/regress.sh", "bash -n x.sh"):
            self.assertEqual(self.phase((1, "Execute " + run)), "running checks", run)
        self.assertEqual(self.phase((1, "Execute npm test"), kind="feedback"), "running commands")

    def test_gone_quiet_it_is_thinking_unless_a_command_is_going(self):
        self.assertEqual(self.phase((1, "Read a"), (2, "WebSearch x"), quiet=sl.QUIET_S), "thinking")
        self.assertEqual(self.phase((1, "Read a"), (2, "WebSearch x"), quiet=sl.QUIET_S - 1), "researching")
        self.assertEqual(self.phase((1, "Read a"), (2, "Execute npm test"), quiet=300), "running checks")

    def test_a_command_that_came_back_is_not_still_running(self):
        log = ["[0m10s] turn 1 · Read a", "[0m20s] turn 2 · Execute npm test"]
        back = "[1m15s] turn 2 ↳ Execute returned in 55s"
        self.assertEqual(sl.phase(log, 300), "running checks")
        self.assertEqual(sl.phase(log + [back], 300), "thinking")            # quiet since it returned
        self.assertEqual(sl.phase(log + [back], 5), "running checks")        # just back: still what it is at
        self.assertEqual(sl.phase(log + ["[1m15s] turn 2 ↳ Execute failed in 55s"], 300), "thinking")
        # Two started together: one back, one still out.
        two = log + ["[0m20s] turn 2 · Execute npm run lint", "[0m30s] turn 2 ↳ Execute returned in 10s, 1 still running"]
        self.assertEqual(sl.phase(two, 300), "running checks")
        self.assertEqual(sl.phase(two + [back], 300), "thinking")
        # A command that only looks, still out, is not a check.
        self.assertEqual(sl.phase(["[0m20s] turn 2 · Execute git log -S x"], 300), "reading files")

    def test_running_row_leads_with_the_phase(self):
        self.f.run("a", log=["[0m10s] turn 2 · Read a", "[0m20s] turn 3 · Execute git diff --stat"])
        [raw] = sl.rows(self.f.dir, NOW, 200)
        self.assertIn(sl.INK + "reading files" + sl.RESET, raw)   # bright, not grey
        self.assertIn("]  reading files · turn 3 · Execute git diff --stat", sl.ANSI.sub("", raw))

    def test_a_quiet_row_says_for_how_long(self):
        log = ["[0m10s] turn 2 · Read a", "[0m20s] turn 3 · Execute cd /repo && npm test"]
        self.f.run("a", log=log)
        old = NOW - 45
        os.utime(os.path.join(self.f.dir, "a.log"), (old, old))
        self.assertIn("]  running checks for 0:45 · turn 3 · Execute npm test", self.f.rows()[0])   # and no cd
        self.f.run("a", log=log + ["[1m00s] turn 3 ↳ Execute returned in 40s"])
        os.utime(os.path.join(self.f.dir, "a.log"), (old, old))
        self.assertIn("]  thinking for 0:45 · turn 3 · Execute npm test", self.f.rows()[0])   # the call, not its return

    def test_dead_process_reads_as_stopped(self):
        self.f.run("a", pid=DEAD_PID, log=["[0m20s] turn 2 · Read x"])
        [row] = self.f.rows()
        self.assertRegex(row, r"\[ stopped +\]  just now · its process is gone")

    def test_dead_process_hidden_once_its_log_is_old(self):
        self.f.run("a", pid=DEAD_PID, log=["[0m20s] turn 2 · Read x"])
        old = NOW - 3600
        os.utime(os.path.join(self.f.dir, "a.log"), (old, old))
        self.assertEqual(self.f.rows(), [])

    def test_finished_rows_show_for_fifteen_minutes(self):
        self.f.run("ok", status="ok", finished=iso(890), duration_s=92, turns=14)
        self.f.run("bad", status="failed", finished=iso(5), duration_s=3, error="droid reported: no auth")
        self.f.run("int", status="interrupted", finished=iso(1), duration_s=7)
        self.f.run("gone", status="failed", finished=iso(901), duration_s=1, error="x")
        rows = self.f.rows()
        self.assertEqual(len(rows), 3)
        text = "\n".join(rows)
        self.assertRegex(text, r"\[ done in 1:32 · 14 turns +\]  14m ago · not triaged yet")
        self.assertRegex(text, r"\[ failed after 0:03 +\]  just now · droid reported: no auth")
        self.assertRegex(text, r"\[ interrupted after 0:07 +\]  just now")
        self.assertEqual([sl.ago(s) for s in (0, 59, 60, 899, 3600, 7300)],
                         ["just now", "just now", "1m ago", "14m ago", "1h ago", "2h ago"])
        raw = next(r for r in sl.rows(self.f.dir, NOW, 200) if "done in" in r)
        self.assertEqual(self.filled(raw, sl.ON_GREEN), sl.BAR_W)   # the result fills the bar, in its colour
        raw = next(r for r in sl.rows(self.f.dir, NOW, 200) if "failed after" in r)
        self.assertEqual(self.filled(raw, sl.ON_RED), sl.BAR_W)

    def test_rechecks_say_their_round(self):
        self.f.run("a", round=2, log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", round=3, kind="feedback", model="gemini-3.8-flash", log=["[0m20s] turn 1 · Read y"])
        self.f.run("c", round=1, model="grok-4.7", log=["[0m20s] turn 1 · Read z"])
        text = "\n".join(self.f.rows())
        self.assertIn("droid-review 2 (glm-5.3-flash high)", text)
        self.assertIn("droid-feedback 3 (gemini-3.8-flash high)", text)
        self.assertRegex(text, r"droid-review \(grok-4\.7 high\) +\[")   # padded to the widest

    def test_rechecks_are_timed_against_rechecks(self):
        self.f.run("first", status="ok", finished=iso(9999), duration_s=300, turns=40)
        self.f.run("again", status="ok", round=2, finished=iso(9999), duration_s=60, turns=8)
        self.f.legacy_log("20260924-old", "glm-5.3-flash", 600)   # no metadata: a first round
        self.f.run("a", round=2, log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", round=1, started=iso(26), log=["[0m20s] turn 2 · Read x"])
        rows = self.f.rows()
        self.assertIn("/ ~7:30", rows[0])   # first rounds: median of 300 and 600
        self.assertIn("/ ~1:00", rows[1])   # re-checks: 60

    def test_shows_droids_display_name_and_times_by_id(self):
        self.f.run("ok", status="ok", model_name="GPT-6.1 Sol", model="gpt-6.1-sol", effort=None,
                   finished=iso(9999), duration_s=120, turns=9)
        self.f.run("a", model_name="GPT-6.1 Sol", model="gpt-6.1-sol", effort="high",
                   log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", model="glm-5.3-flash", started=iso(30), log=["[0m20s] turn 2 · Read x"])  # older run: no name
        text = "\n".join(self.f.rows())
        self.assertIn("(GPT-6.1 Sol high)", text)
        self.assertIn("/ ~2:00", text)            # its estimate, found by id
        self.assertIn("(glm-5.3-flash high)", text)    # no name recorded: the id

    def test_feedback_runs_are_labelled(self):
        self.f.run("a", kind="feedback", log=["[0m20s] turn 2 · Read x"])
        self.assertIn("droid-feedback (glm-5.3-flash high)", self.f.rows()[0])

    def test_rows_line_up_across_models(self):
        self.f.run("a", started=iso(30), log=["[0m20s] turn 2 · Read x"])
        self.f.run("b", started=iso(20), model="gemini-3.8-flash", effort=None,
                   log=["[0m20s] turn 2 · Read y"])
        a, b = self.f.rows()
        self.assertIn("droid-review (gemini-3.8-flash)", b)   # no effort named: none shown
        # The bar starts at the same column in both rows.
        col = lambda r: r.index("[")
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

    def test_live_pid_but_log_silent_an_hour_reads_as_stopped(self):
        # Killed outright, its pid reused: the pid says alive, the log says not.
        self.f.run("a", pid=1, log=["[0m20s] turn 2 · Read x"])
        old = NOW - sl.STALE_S - 60
        os.utime(os.path.join(self.f.dir, "a.log"), (old, old))
        self.assertEqual(self.f.rows(), [])   # stopped, and long enough ago to hide
        os.utime(os.path.join(self.f.dir, "a.log"), (NOW - sl.STALE_S + 60,) * 2)
        self.assertIn("turn 2", self.f.rows()[0])   # still within the hour: running

    def test_a_finished_review_says_what_came_of_it(self):
        self.f.run("new", status="ok", finished=iso(120), duration_s=60, turns=5)
        self.f.run("done", status="ok", finished=iso(600), duration_s=60, turns=5, started=iso(700),
                   responses=[{"at": iso(500), "text": "first"}, {"at": iso(180), "text": "fixed 2;  rejected the race"}])
        done, new = self.f.rows()
        self.assertIn("]  2m ago · not triaged yet", new)
        self.assertIn("]  10m ago · triaged 3m ago: fixed 2; rejected the race", done)   # the latest note, on one line

    def test_a_review_waits_an_hour_to_be_triaged_then_a_quarter_after(self):
        self.f.run("waiting", status="ok", finished=iso(3500), duration_s=60, turns=5)
        self.f.run("forgotten", status="ok", finished=iso(3700), duration_s=60, turns=5)
        self.f.run("just", status="ok", finished=iso(5000), duration_s=60, turns=5, responses=[{"at": iso(800), "text": "x"}])
        self.f.run("long", status="ok", finished=iso(1000), duration_s=60, turns=5, responses=[{"at": iso(950), "text": "y"}])
        self.f.run("failed", status="failed", finished=iso(1000), duration_s=60)   # nothing to triage
        text = "\n".join(self.f.rows())
        self.assertEqual(len(self.f.rows()), 2)
        self.assertIn("58m ago · not triaged yet", text)
        self.assertIn("triaged 13m ago: x", text)

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
            r = self.run_script(stdin, "--", sys.executable, "-c",
                                'import sys,json; print("MINE", json.load(sys.stdin)["workspace"]["current_dir"])')
            lines = r.stdout.splitlines()
            self.assertEqual(lines[0], "MINE " + f.root)
            self.assertIn("droid-review (glm-5.3-flash high)", sl.ANSI.sub("", lines[1]))
        finally:
            f.close()

    def test_previous_status_line_keeps_its_quoting(self):
        # As the settings shell hands it over: already split and unquoted.
        with tempfile.TemporaryDirectory() as d:
            r = self.run_script(json.dumps({"workspace": {"current_dir": d}}),
                                "--", sys.executable, "-c", 'print("PREV line")')
            self.assertEqual(r.stdout, "PREV line\n")
            r = self.run_script(json.dumps({"workspace": {"current_dir": d}}),
                                "--", 'echo "one string"; echo two')   # a whole command line
            self.assertEqual(r.stdout, "one string\ntwo\n")
            r = self.run_script(json.dumps({"workspace": {"current_dir": d}}),   # leading VAR=value
                                "--", "PREV_VAR=set", sys.executable, "-c",
                                'import os; print("PREV", os.environ["PREV_VAR"])')
            self.assertEqual(r.stdout, "PREV set\n")
            r = self.run_script(json.dumps({"workspace": {"current_dir": d}}),   # value with a space
                                "--", "PREV_VAR=one two", "B=x=y", sys.executable, "-c",
                                'import os; print("PREV", os.environ["PREV_VAR"], os.environ["B"])')
            self.assertEqual(r.stdout, "PREV one two x=y\n")

    def test_requote_leaves_assignments_as_assignments(self):
        self.assertEqual(sl.requote(["A=one two", "cmd", "X=1"]), "A='one two' cmd X=1")
        self.assertEqual(sl.requote(["python3", "-c", 'print("x")']), "python3 -c 'print(\"x\")'")

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
