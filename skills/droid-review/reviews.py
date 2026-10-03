#!/usr/bin/env python3
"""The droid reviews in this repo as a history, and the line that says what
came of each one. droid-review.sh runs it (--history, --note); it reads and
writes only .droid-reviews/.

    reviews.py history [--all]         this branch's reviews, newest first
    reviews.py note <review> <text>    record what was done about a review

History groups a review with its re-checks (one droid session, its rounds) and
says, for each round, when it ran, how it ended, the commit it reviewed and
how far HEAD has moved since, and the notes left on it:

    GLM-5.3-Flash · review · 2 rounds · session 71feef9c-4f42-4fac-90c1-99274f49d494
      1  Oct 2 23:18  ok in 3:00 · 22 turns   at 9f8e7d6, 4 commits behind
         → fixed 4 (date -r, quoting after --); 2 false positives
      2  Oct 3 00:07  ok in 0:41 · 9 turns    at 17e6822, current

A note is the triaging agent's own account of what it did ("fixed 3, rejected
the race as a false positive"), one line, stored in the run's .json under
"responses" and appended to the review file under "## Response". <review> is
the review file (or its .json / .log), a session id (its newest round), or
"last" (the newest finished review on this branch). Notes leave the files'
modification times alone, so `--session last` still finds the newest review.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.dont_write_bytecode = True   # no __pycache__ beside the skill
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statusline import (AMBER, BOLD, GREEN, GREY, RED, RESET, STALE_S, TEAL,  # noqa: E402
                        alive, clock, find_reviews, log_ends, silent_for)

STAMP = re.compile(r"^\d{8}-\d{6}-")


def git(*args):
    try:
        r = subprocess.run(("git",) + args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def when(iso):
    try:
        return datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def header(path):
    """The '- key: value' lines at the top of a review file."""
    out = {}
    try:
        with open(path) as f:
            for i, line in enumerate(f):
                if i > 40 or line.startswith("## "):
                    break
                hit = re.match(r"^- ([a-z ]+): (.*)$", line.rstrip("\n"))
                if hit:
                    out.setdefault(hit.group(1), hit.group(2))
                elif line.startswith("# "):
                    out.setdefault("title", line[2:].strip())
    except OSError:
        pass
    return out


def file_notes(path):
    """The notes under "## Response" in a review file: where a review written
    before the metadata keeps them, having no .json."""
    out, inside = [], False
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("## "):
                    inside = line.strip() == "## Response"
                    continue
                hit = re.match(r"^- (\d{4}-\d\d-\d\dT\S+): (.*)$", line.rstrip("\n")) if inside else None
                if hit:
                    out.append({"at": hit.group(1), "text": hit.group(2)})
    except OSError:
        pass
    return out


def load(folder, now):
    """Every run in the folder: its .json, or for a review written before the
    metadata existed, what its file's header says."""
    runs, seen = [], set()
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name)) as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(m, dict) or not m.get("status"):
            continue
        base = name[:-5]
        seen.add(base)
        status = m["status"]
        if status == "running" and (not alive(m.get("pid")) or silent_for(folder, {"_name": base}, now) > STALE_S):
            status = "stopped"
        runs.append({
            "base": base, "log": os.path.join(folder, base + ".log"), "meta": m, "kind": m.get("kind") or "review", "status": status,
            "started": when(m.get("started")), "session": m.get("session") or (m.get("continues") or {}).get("session"),
            "model": m.get("model"), "name": m.get("model_name") or m.get("model") or "?", "effort": m.get("effort"),
            "branch": m.get("branch"), "head": m.get("head"), "scope": m.get("scope"),
            "duration": m.get("duration_s"), "turns": m.get("turns"), "error": m.get("error"),
            "review": (m.get("files") or {}).get("review"), "notes": m.get("responses") or [],
        })
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md") or name.endswith("-multi.md") or name[:-3] in seen:
            continue
        h = header(os.path.join(folder, name))
        if "session" not in h:
            continue   # not a review file
        model, _, effort = (h.get("model") or "?").partition(" (reasoning ")
        effort = effort.rstrip(")")
        turns = re.match(r"(\d+), (\d+)s", h.get("turns") or "")
        runs.append({
            "base": name[:-3], "log": None, "meta": None, "kind": "feedback" if "feedback" in h.get("title", "") else "review",
            "status": "ok", "started": when(h.get("started") or h.get("when")), "session": h["session"],
            "model": model, "name": model, "effort": None if effort in ("", "droid default") else effort,
            "branch": None, "head": None, "scope": None,
            "duration": int(turns.group(2)) if turns else None, "turns": int(turns.group(1)) if turns else None,
            "error": None, "review": os.path.join(os.path.basename(folder), name),
            "notes": file_notes(os.path.join(folder, name)),
        })
    return runs


def threads(runs):
    """A review and its re-checks share a droid session: one thread, rounds in
    the order they ran. Newest activity first."""
    by = {}
    for r in runs:
        by.setdefault(r["session"] or r["base"], []).append(r)
    out = [sorted(t, key=lambda r: stamp(r)) for t in by.values()]
    out.sort(key=lambda t: stamp(t[-1]), reverse=True)
    return out


def stamp(r):
    s = r["started"]
    return s.timestamp() if s else 0


def slug(branch):
    return (branch or "").replace("/", "-")


def on_branch(thread, branch):
    """Whether a thread belongs to this branch: by the branch its metadata
    recorded, else (an older review) by the branch in its file name."""
    for r in thread:
        if r["branch"] is not None:
            if r["branch"] == branch:
                return True
        elif STAMP.sub("", r["base"]).startswith(slug(branch) + "-") or STAMP.sub("", r["base"]) == slug(branch):
            return True
    return False


class Paint:
    def __init__(self, on):
        self.on = on

    def __call__(self, color, text):
        return color + text + RESET if self.on and text else text


def day(t, now):
    d = (now.date() - t.date()).days
    if d == 0:
        return "today %s" % t.strftime("%H:%M")
    if d == 1:
        return "yesterday %s" % t.strftime("%H:%M")
    fmt = "%b %-d %H:%M" if t.year == now.year else "%b %-d %Y %H:%M"
    return t.strftime(fmt)


def result(r, p, now_ts):
    took = clock(r["duration"]) if r["duration"] is not None else "?"
    s = r["status"]
    if s == "ok":
        turns = " · %s turns" % r["turns"] if r["turns"] is not None else ""
        return p(GREEN + BOLD, "ok in " + took) + turns, len("ok in " + took + turns)
    if s == "failed":
        err = " ".join(str(r["error"] or "").split())
        err = (err[:57] + "…") if len(err) > 58 else err
        text = "failed after %s%s" % (took, ": " + err if err else "")
        return p(RED + BOLD, text), len(text)
    if s == "running":
        elapsed = now_ts - stamp(r) if r["started"] else 0
        _, last = log_ends(r["log"])
        turn = re.search(r"turn (\d+)", last or "")
        text = "running %s%s" % (clock(elapsed), " · turn " + turn.group(1) if turn else "")
        return p(TEAL + BOLD, text), len(text)
    text = "interrupted after " + took if s == "interrupted" else "stopped (its process is gone)"
    return p(AMBER + BOLD, text), len(text)


def freshness(r, head, branch, p):
    """The commit a round reviewed, against HEAD now."""
    sha = r["head"]
    if not sha:
        return ""
    at = "at " + sha[:7]
    if sha == head:
        return at + ", " + p(GREEN, "current")
    if git("merge-base", "--is-ancestor", sha, "HEAD") is not None:
        n = int(git("rev-list", "--count", sha + "..HEAD") or 0)
        return at + ", " + p(AMBER, "%d commit%s behind" % (n, "" if n == 1 else "s"))
    if r["branch"] and r["branch"] != branch:
        return at + " on " + r["branch"]
    return at + ", " + p(AMBER, "not in this branch now (rebased?)")


def history(folder, every, color, now=None):
    now = now or time.time()
    now_dt = datetime.fromtimestamp(now).astimezone()
    p = Paint(color)
    branch = git("branch", "--show-current") or ""
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    dirty = len(status.splitlines()) if status else 0
    ts = threads(load(folder, now))
    shown = ts if every or not branch else [t for t in ts if on_branch(t, branch)]
    top = "droid reviews · %s · HEAD %s · %s" % (
        "every branch" if every or not branch else branch, (head or "?")[:7],
        "%d uncommitted" % dirty if dirty else "clean")
    out = [p(BOLD, top)]
    if not shown:
        out.append("")
        out.append("no reviews%s yet" % ("" if every or not branch else " on this branch (--all for every branch)"))
        return out
    for t in shown:
        first = t[0]
        effort = " " + first["effort"] if first["effort"] else ""
        rounds = "%d round%s" % (len(t), "" if len(t) == 1 else "s")
        sess = " · session " + first["session"] if first["session"] else ""
        out.append("")
        out.append("%s%s · %s · %s%s" % (p(TEAL + BOLD, first["name"]), effort, first["kind"], rounds, p(GREY, sess)))
        for i, r in enumerate(t, 1):
            res, width = result(r, p, now)
            started = day(r["started"].astimezone(), now_dt) if r["started"] else "?"
            fresh = freshness(r, head, branch, p)
            if r["scope"] == "uncommitted":
                fresh = (fresh + ", " if fresh else "") + "uncommitted only"
            out.append("  %d  %-17s %s%s%s" % (i, started, res, " " * max(1, 28 - width), fresh))
            for n in r["notes"]:
                out.append("     " + p(BOLD, "→ ") + n.get("text", ""))
    return out


def resolve(folder, target, now, branch=None):
    """The run a note is for: a review file (.md/.json/.log), a session id
    (its newest round) or "last" (the newest finished one on this branch)."""
    runs = load(folder, now)
    if target == "last":
        branch = git("branch", "--show-current") or "" if branch is None else branch
        mine = [r for r in runs if r["status"] != "running" and (not branch or on_branch([r], branch))]
        return max(mine, key=stamp) if mine else None
    base = os.path.basename(target)
    for ext in (".md", ".json", ".log"):
        if base.endswith(ext):
            base = base[:-len(ext)]
            return next((r for r in runs if r["base"] == base), None)
    rounds = [r for r in runs if r["session"] == target]
    return max(rounds, key=stamp) if rounds else None


def keep_mtime(path, write):
    """Run write() on path, then put its times back: a note is not a new review."""
    try:
        st = os.stat(path)
    except OSError:
        return
    write()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


def note(folder, target, text, now=None, branch=None):
    now = now or time.time()
    text = " ".join(text.split())
    if not text:
        raise SystemExit("the note is empty: say in one line what was done about the review")
    r = resolve(folder, target, now, branch)
    if not r:
        raise SystemExit("no review matches %r (a review file, a session id, or last)" % target)
    if r["status"] == "running":
        raise SystemExit("%s is still running; note it once it has finished" % r["base"])
    at = datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds")
    if r["meta"] is not None:
        meta = os.path.join(folder, r["base"] + ".json")

        def save():
            with open(meta) as f:
                m = json.load(f)
            m.setdefault("responses", []).append({"at": at, "text": text})
            tmp = "%s.%d.tmp" % (meta, os.getpid())
            with open(tmp, "w") as f:
                json.dump(m, f, indent=2)
                f.write("\n")
            os.replace(tmp, meta)
        keep_mtime(meta, save)
    md = os.path.join(folder, r["base"] + ".md")
    if os.path.exists(md):
        def append():
            with open(md) as f:
                has = "\n## Response\n" in f.read()
            with open(md, "a") as f:
                if not has:
                    f.write("\n\n## Response\n\nWhat the agent that triaged this review did about it, in its own words:\n\n")
                f.write("- %s: %s\n" % (at, text))
        keep_mtime(md, append)
    return r


def main(argv):
    folder = find_reviews(os.getcwd())
    if argv[:1] == ["history"]:
        every = "--all" in argv[1:]
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        if not folder:
            print("droid reviews · none in this repo yet (.droid-reviews/ does not exist)")
            return 0
        print("\n".join(history(folder, every, color)))
        return 0
    if argv[:1] == ["note"] and len(argv) >= 3:
        if not folder:
            raise SystemExit("no .droid-reviews/ in this repo, so nothing to note")
        r = note(folder, argv[1], " ".join(argv[2:]))
        print("noted on %s" % (r["review"] or os.path.join(os.path.basename(folder), r["base"] + ".json")))
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
