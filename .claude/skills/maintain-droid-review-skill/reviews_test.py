#!/usr/bin/env python3
"""Unit tests for skills/droid-review/reviews.py: threads, branch filter, the
round lines, notes, and --compare. Builds .droid-reviews/ folders in a temp
dir (--compare in a real throwaway repo); freshness against HEAD in the
history is covered live by regress.sh.

    python3 .claude/skills/maintain-droid-review-skill/reviews_test.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime

sys.dont_write_bytecode = True   # no __pycache__ beside the skill
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "skills", "droid-review"))
import reviews  # noqa: E402

NOW = time.time()


def iso(ago):
    return datetime.fromtimestamp(NOW - ago).astimezone().isoformat(timespec="seconds")


class Folder:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, ".droid-reviews")
        os.mkdir(self.path)

    def run(self, base, **m):
        m.setdefault("status", "ok")
        m.setdefault("kind", "review")
        m.setdefault("model", "glm-5.3-flash")
        m.setdefault("pid", 1)
        m.setdefault("files", {"review": ".droid-reviews/%s.md" % base})
        with open(os.path.join(self.path, base + ".json"), "w") as f:
            json.dump(m, f)
        if m["status"] != "running" and m["files"].get("review"):
            with open(os.path.join(self.path, base + ".md"), "w") as f:
                f.write("# droid review\n\n- session: %s\n\nfindings\n" % m.get("session"))

    def md(self, name, text):
        with open(os.path.join(self.path, name), "w") as f:
            f.write(text)


class Threads(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(self.f.tmp.cleanup)

    def test_rounds_of_a_session_are_one_thread_in_order(self):
        self.f.run("20261003-000000-feat-glm", session="s1", started=iso(600), branch="feat")
        self.f.run("20261003-001000-feat-glm", session="s1", started=iso(60), branch="feat")
        self.f.run("20261003-000500-feat-grok", session="s2", started=iso(300), branch="feat")
        ts = reviews.threads(reviews.load(self.f.path, NOW))
        self.assertEqual([[r["base"] for r in t] for t in ts],
                         [["20261003-000000-feat-glm", "20261003-001000-feat-glm"], ["20261003-000500-feat-grok"]])

    def test_a_run_without_a_session_is_its_own_thread(self):
        self.f.run("a", status="failed", started=iso(10), error="boom")
        self.f.run("b", status="failed", started=iso(20), error="boom")
        self.assertEqual(len(reviews.threads(reviews.load(self.f.path, NOW))), 2)

    def test_a_dead_running_run_is_stopped(self):
        self.f.run("a", status="running", pid=2 ** 22 + 12345, started=iso(10), files={})
        self.assertEqual(reviews.load(self.f.path, NOW)[0]["status"], "stopped")

    def test_older_review_files_come_from_their_header(self):
        self.f.md("20260924-185524-master.md",
                  "# droid review\n\n- when: 2026-09-24T19:00:32\n- model: qwen3.8-max (reasoning max)\n"
                  "- session: af1\n- turns: 10, 305s\n\nbody\n")
        self.f.md("20260924-185524-master-multi.md", "# index\n\n- session: nope\n")
        self.f.md("notes.md", "# not a review\n")
        runs = reviews.load(self.f.path, NOW)
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual((r["model"], r["effort"], r["session"], r["turns"], r["duration"]),
                         ("qwen3.8-max", "max", "af1", 10, 305))

    def test_branch_by_metadata_else_by_file_name(self):
        self.f.run("20261003-000000-feat-x-glm", session="s1", started=iso(9), branch="feat/x")
        self.f.run("20261003-000000-main-glm", session="s2", started=iso(9), branch="main")
        self.f.md("20260924-185524-feat-x-qwen3.8-max.md", "# droid review\n\n- session: s3\n")
        self.f.md("20260924-185524-feat-xy.md", "# droid review\n\n- session: s4\n")
        self.f.md("20260920-101010-feat-x.md", "# droid review\n\n- session: s5\n")   # the oldest naming
        ts = reviews.threads(reviews.load(self.f.path, NOW))
        mine = sorted(t[0]["session"] for t in ts if reviews.on_branch(t, "feat/x"))
        self.assertEqual(mine, ["s1", "s3", "s5"])


class Lines(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(self.f.tmp.cleanup)
        self.p = reviews.Paint(False)

    def test_results(self):
        r = lambda **k: dict({"duration": 75, "turns": 9, "error": None, "started": None, "log": None}, **k)
        self.assertEqual(reviews.result(r(status="ok"), self.p, NOW)[0], "ok in 1:15 · 9 turns")
        self.assertEqual(reviews.result(r(status="failed", error="model\n unavailable"), self.p, NOW)[0],
                         "failed after 1:15: model unavailable")
        self.assertEqual(reviews.result(r(status="interrupted"), self.p, NOW)[0], "interrupted after 1:15")
        long = reviews.result(r(status="failed", error="x" * 200), self.p, NOW)[0]
        self.assertTrue(long.endswith("…") and len(long) < 90)

    def test_a_running_round_shows_its_turn(self):
        log = os.path.join(self.f.path, "a.log")
        with open(log, "w") as f:
            f.write("[0s] started glm-5.3-flash\n[40s] turn 4 · Read x\n")
        r = {"status": "running", "duration": None, "turns": None, "error": None,
             "started": reviews.when(iso(65)), "log": log}
        self.assertEqual(reviews.result(r, self.p, NOW)[0], "running 1:05 · turn 4")

    def test_day(self):
        now = datetime(2026, 10, 3, 12, 0)
        self.assertEqual(reviews.day(datetime(2026, 10, 3, 9, 5), now), "today 09:05")
        self.assertEqual(reviews.day(datetime(2026, 10, 2, 23, 1), now), "yesterday 23:01")
        self.assertEqual(reviews.day(datetime(2026, 9, 24, 19, 0), now), "Sep 24 19:00")
        self.assertEqual(reviews.day(datetime(2025, 9, 24, 19, 0), now), "Sep 24 2025 19:00")


class Notes(unittest.TestCase):
    def setUp(self):
        self.f = Folder()
        self.addCleanup(self.f.tmp.cleanup)
        self.f.run("20261003-000000-feat-glm", session="s1", started=iso(600), branch="feat")
        self.f.run("20261003-001000-feat-glm", session="s1", started=iso(60), branch="feat")
        self.md = os.path.join(self.f.path, "20261003-000000-feat-glm.md")
        self.meta = self.md[:-3] + ".json"
        os.utime(self.md, (NOW - 600, NOW - 600))
        os.utime(self.meta, (NOW - 600, NOW - 600))

    def test_a_note_goes_in_the_json_and_the_review_file(self):
        reviews.note(self.f.path, ".droid-reviews/20261003-000000-feat-glm.md", "fixed 2;\n rejected 1", now=NOW)
        reviews.note(self.f.path, "20261003-000000-feat-glm.json", "then the third", now=NOW)
        with open(self.meta) as f:
            m = json.load(f)
        self.assertEqual([n["text"] for n in m["responses"]], ["fixed 2; rejected 1", "then the third"])
        with open(self.md) as f:
            text = f.read()
        self.assertEqual(text.count("## Response"), 1)
        self.assertTrue(text.rstrip().endswith(": then the third"))
        self.assertIn(": fixed 2; rejected 1\n", text)

    def test_a_note_keeps_modification_times(self):
        before = (os.path.getmtime(self.md), os.path.getmtime(self.meta))
        reviews.note(self.f.path, "20261003-000000-feat-glm.md", "fixed", now=NOW)
        self.assertEqual((os.path.getmtime(self.md), os.path.getmtime(self.meta)), before)

    def test_a_session_or_last_means_its_newest_round(self):
        self.assertEqual(reviews.resolve(self.f.path, "s1", NOW)["base"], "20261003-001000-feat-glm")
        self.assertEqual(reviews.resolve(self.f.path, "last", NOW, "feat")["base"], "20261003-001000-feat-glm")
        self.assertIsNone(reviews.resolve(self.f.path, "nope", NOW))

    def test_last_skips_a_round_still_running(self):
        self.f.run("20261003-002000-feat-glm", session="s1", status="running", pid=os.getpid(),
                   started=iso(5), branch="feat", files={})
        self.assertEqual(reviews.resolve(self.f.path, "last", NOW, "feat")["base"], "20261003-001000-feat-glm")

    def test_refuses_a_running_review_an_empty_note_and_no_match(self):
        self.f.run("20261003-002000-feat-glm", session="s9", status="running", pid=os.getpid(),
                   started=iso(5), branch="feat", files={})
        for target, text in (("s9", "x"), ("s1", "  \n "), ("nope", "x")):
            with self.assertRaises(SystemExit):
                reviews.note(self.f.path, target, text, now=NOW)

    def test_a_note_on_a_review_older_than_the_metadata_shows_in_history(self):
        self.f.md("20260924-185524-feat-qwen.md", "# droid review\n\n- when: 2026-09-24T19:00:32\n"
                  "- model: qwen3.8-max (reasoning droid default)\n- session: old\n- turns: 10, 305s\n\n"
                  "## Findings\n\n- 2026-09-24T19:00:00: not a note, a finding\n")
        reviews.note(self.f.path, "old", "fixed the base-ref crash", now=NOW)
        out = reviews.history(self.f.path, True, False, now=NOW)
        self.assertEqual([l for l in out if "→" in l], ["     → fixed the base-ref crash"])

    def test_history_shows_the_note_under_its_round(self):
        reviews.note(self.f.path, "20261003-000000-feat-glm.md", "fixed the crash", now=NOW)
        out = reviews.history(self.f.path, True, False, now=NOW)
        at = next(i for i, l in enumerate(out) if l.startswith("  1  "))
        self.assertEqual(out[at + 1], "     → fixed the crash")
        self.assertTrue(out[at + 2].startswith("  2  "))   # a round without a note is one line
        self.assertTrue(any("· review · 2 rounds · session s1" in l for l in out))


class Compare(unittest.TestCase):
    """--compare, in a real repo: a branch that changed line 5 of a.py and
    added b.py, reviewed with c.txt edited but not committed."""

    def sh(self, *args):
        return subprocess.run(args, cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def write(self, name, text):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(text)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = os.path.realpath(tmp.name)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.repo)
        git = lambda *a: self.sh("git", "-c", "user.name=t", "-c", "user.email=t@t", *a)
        self.git = git
        git("init", "-q", "-b", "master")
        lines = ["line %d" % i for i in range(1, 31)]
        self.write("a.py", "\n".join(lines) + "\n")
        self.write("c.txt", "one\n")
        git("add", "."); git("commit", "-q", "-m", "base")
        self.base = git("rev-parse", "HEAD")
        git("checkout", "-q", "-b", "feat")
        lines[4] = "line 5, changed on the branch"
        self.lines = lines
        self.write("a.py", "\n".join(lines) + "\n")
        self.write("b.py", "new\n")
        git("add", "."); git("commit", "-q", "-m", "feat")
        self.head = git("rev-parse", "HEAD")
        self.write("c.txt", "one\ntwo, uncommitted at the review\n")
        self.folder = os.path.join(self.repo, ".droid-reviews")
        os.mkdir(self.folder)
        self.write(".droid-reviews/.gitignore", "*\n")
        self.meta = {
            "status": "ok", "kind": "review", "model": "glm-5.3-flash", "pid": 1, "session": "s1", "round": 1,
            "started": iso(600), "branch": "feat", "head": self.head, "scope": "branch",
            "base": {"merge_base": self.base}, "uncommitted": {"staged": 0, "unstaged": 1, "untracked": 0},
            "uncommitted_files": {"c.txt": git("hash-object", "c.txt")},
            "files": {"review": ".droid-reviews/r.md"},
        }
        self.save()
        self.write(".droid-reviews/r.md", "# droid review\n\n- session: s1\n- turns: 2, 1s\n\n"
                   "- high `a.py:5` breaks. Also a.py:20-21 and b.py:1, c.txt:2.\n"
                   "  See http://example.com:80 and gone.py:3 (no such file).\n"
                   "\n## Response\n\n- 2026-10-03T00:00:00+08:00: fixed x.py:9\n")

    def save(self):
        with open(os.path.join(self.folder, "r.json"), "w") as f:
            json.dump(self.meta, f)

    def compare(self):
        return "\n".join(reviews.compare(self.folder, "last", now=NOW))

    def test_nothing_changed(self):
        out = self.compare()
        self.assertIn("reviewed %s · HEAD is still there" % self.head[:7], out)
        self.assertIn("uncommitted then: 1 file · now: 1 file", out)
        self.assertIn("nothing has changed since the review", out)

    def test_cites_only_real_files_above_the_notes(self):
        out = self.compare()
        self.assertIn("cited in the review: 4", out)
        for no in ("example.com", "gone.py", "x.py"):
            self.assertNotIn(no, out)

    def test_which_lines_the_branch_changed(self):
        out = self.compare()
        self.assertRegex(out, r"a\.py:5 +changed on this branch · unchanged")
        self.assertRegex(out, r"a\.py:20-21 +not changed on this branch · unchanged")
        self.assertRegex(out, r"b\.py:1 +new on this branch · unchanged")
        # c.txt:2 is the uncommitted line: the branch's, read from the working copy.
        self.assertRegex(out, r"c\.txt:2 +changed on this branch · unchanged \(uncommitted then, the same now\)")

    def test_a_commit_since_and_a_line_that_moved(self):
        self.lines[19] = "line 20, fixed"
        self.write("a.py", "added at the top\n" + "\n".join(self.lines) + "\n")
        self.git("commit", "-q", "-m", "fix", "--", "a.py")
        out = self.compare()
        self.assertIn("1 commit on", out)
        self.assertRegex(out, r"changed since the review: 1 file\n +a\.py +committed")
        self.assertRegex(out, r"a\.py:20-21 +not changed on this branch · changed since \(committed\)")
        self.assertRegex(out, r"a\.py:5 +changed on this branch · unchanged, now line 6")

    def test_unstaged_staged_and_untracked_changes_count(self):
        self.lines[19] = "line 20, edited but not committed"
        self.write("a.py", "\n".join(self.lines) + "\n")       # unstaged
        self.write("b.py", "new\nstaged\n")
        self.git("add", "b.py")                                   # staged
        self.write("notes.txt", "untracked\n")                   # untracked
        out = self.compare()
        self.assertIn("HEAD is still there", out)
        self.assertIn("changed since the review: 3 files", out)
        self.assertRegex(out, r"a\.py +uncommitted\n")
        self.assertRegex(out, r"b\.py +uncommitted\n")
        self.assertRegex(out, r"notes\.txt +uncommitted \(untracked\)")
        self.assertRegex(out, r"a\.py:20-21 +not changed on this branch · changed since \(uncommitted\)")
        self.assertRegex(out, r"b\.py:1 +new on this branch · changed since \(uncommitted\)")

    def test_a_file_uncommitted_then_and_different_now(self):
        self.write("c.txt", "one\ntwo, edited again\n")
        out = self.compare()
        self.assertRegex(out, r"c\.txt +uncommitted then, different now")
        self.assertRegex(out, r"c\.txt:2 +uncommitted then and different now: its lines cannot be compared")
        # Committing it as the reviewer saw it is no change; committing something else is.
        self.git("commit", "-q", "-am", "c")
        self.assertRegex(self.compare(), r"c\.txt +committed, uncommitted then, different now")

    def test_a_review_from_before_the_files_were_recorded_says_so(self):
        del self.meta["uncommitted_files"]
        self.save()
        out = self.compare()
        self.assertIn("which 1 file it saw is not known", out)
        self.assertRegex(out, r"a\.py:5 +changed on this branch · unchanged \(if it was committed then\)")

    def test_a_reviewed_commit_the_repo_no_longer_has(self):
        self.meta["head"] = "0" * 40
        self.save()
        self.assertIn("no longer has", self.compare())

    def test_near_counts(self):
        hs = [(10, 1, 10, 1), (40, 0, 41, 2)]   # line 10 changed; two lines inserted after 40
        self.assertTrue(reviews.touched(hs, 13, 13, 0))
        self.assertFalse(reviews.touched(hs, 14, 14, 0))
        self.assertTrue(reviews.touched(hs, 44, 44, 0))    # the insertion sits between 40 and 41
        self.assertEqual(reviews.moved(hs, 30), 30)
        self.assertEqual(reviews.moved(hs, 50), 52)


if __name__ == "__main__":
    unittest.main(verbosity=1)
