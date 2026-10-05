#!/usr/bin/env python3
"""The droid reviews in this repo as a history, and the line that says what
came of each one. droid-review.sh runs it (--history, --note, --compare); it
reads and writes only .droid-reviews/.

    reviews.py history [--all]         this branch's reviews, newest first
    reviews.py note <review> <text>    record what was done about a review
    reviews.py compare [<review>]      a review against the repo now (default: last)

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

Compare answers two things about a finished review without a model run: what
has changed since it was written, committed or not, and for each file:line it
cites, whether this branch changed that line (else the finding is about code
that was already there) and whether the line has changed since:

    GLM-5.3-Flash · review · round 1 · today 00:24
    reviewed c7d7fb5 · HEAD is 4073ac9, 2 commits on
    uncommitted then: none · now: 1 file

    changed since the review: 3 files
      README.md                              committed
      skills/droid-review/statusline.py      committed, uncommitted
      notes.txt                              uncommitted (untracked)

    cited in the review: 2
      skills/droid-review/statusline.py:47   changed on this branch · changed since (committed)
      skills/droid-review/runs.py:12         not changed on this branch · unchanged, now line 14

"Since" is against the working tree, so staged, unstaged and untracked changes
count. A file that was uncommitted when the review ran is compared by the
content hash the run recorded: the same as then, or changed in ways the lines
cannot be told for.
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
from runs import (AMBER, BOLD, GREEN, GREY, RED, RESET, STALE_S, TEAL,  # noqa: E402
                  alive, clock, find_reviews, log_ends, silent_for)

STAMP = re.compile(r"^\d{8}-\d{6}-")


def git(*args, raw=False):
    try:
        r = subprocess.run(("git",) + args, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.strip()


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


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)
# path/to/file.ext:12 or :12-20. The path must have an extension and exist in
# the reviewed commit or on disk, which is what keeps prose and URLs out.
CITE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]*\.[A-Za-z]\w*):(\d+)(?:[-–](\d+))?")


def hunks(*args):
    """(old start, old count, new start, new count) per hunk of a git diff
    -U0; None when git cannot make the diff."""
    out = git("diff", "-U0", "--no-color", "--no-ext-diff", *args)
    if out is None:
        return None
    return [(int(a), int(b or 1), int(c), int(d or 1)) for a, b, c, d in
            ((m.group(1), m.group(2), m.group(3), m.group(4)) for m in HUNK.finditer(out))]


# A reviewer's line number is near the code it means, not always on it, and a
# fix often lands beside the line cited: a change this close counts.
NEAR = 3


def touched(hs, lo, hi, side):
    """Whether a hunk changes lines lo..hi or ones within NEAR of them: side
    0 the old file, 1 the new. A hunk with no lines on that side (a pure
    insertion or deletion) sits between its line and the next."""
    for h in hs:
        start, count = h[side * 2], h[side * 2 + 1]
        end = start + count - 1 if count else start + 1
        if start <= hi + NEAR and lo - NEAR <= end:
            return True
    return False


def moved(hs, line):
    """Where an old line that no hunk touched sits in the new file."""
    return line + sum(d - b for a, b, c, d in hs if (a + b - 1 if b else a) < line)


def blob(path):
    """The content hash of a file on disk, as git names it; None if absent."""
    return git("hash-object", "--", path) if os.path.isfile(path) else None


def citations(text):
    """(path, first line, last line) for each file:line a review's text
    cites, in order, once each."""
    out = []
    for m in CITE.finditer(text):
        lo = int(m.group(2))
        c = (m.group(1), lo, max(lo, int(m.group(3) or lo)))
        if c not in out:
            out.append(c)
    return out


def body(path):
    """A review file's text: below its header, above the notes."""
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return ""
    text = text.split("\n## Response\n")[0]
    lines = text.splitlines()
    # The header ends at its "- turns:" line; a review may open with a bullet
    # of its own, so "the first line that is not a bullet" would not do.
    for i, line in enumerate(lines[:40]):
        if line.startswith("- turns: "):
            return "\n".join(lines[i + 1:])
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith("# ") or re.match(r"^- [a-z ]+: ", lines[i])):
        i += 1
    return "\n".join(lines[i:])


def compare(folder, target, color=False, now=None):
    now = now or time.time()
    p = Paint(color)
    r = resolve(folder, target, now)
    if not r:
        raise SystemExit("no review matches %r (a review file, a session id, or last)" % target)
    if r["status"] == "running":
        raise SystemExit("%s is still running; compare it once it has finished" % r["base"])
    m = r["meta"]
    if not m or not m.get("head"):
        raise SystemExit("%s was written before reviews recorded their commit, so there is nothing to compare it with" % r["base"])
    root = os.path.dirname(folder)
    os.chdir(root)   # the paths a review cites are from the repo root
    sha, head = m["head"], git("rev-parse", "HEAD")
    started = day(r["started"].astimezone(), datetime.fromtimestamp(now).astimezone()) if r["started"] else "?"
    effort = " " + r["effort"] if r["effort"] else ""
    out = ["%s%s · %s · round %d · %s" % (p(TEAL + BOLD, r["name"]), effort, r["kind"], m.get("round") or 1, started)]
    if git("cat-file", "-e", sha + "^{commit}") is None:
        out.append("reviewed %s, which this repo no longer has (rebased and pruned?): nothing to compare" % sha[:7])
        return out
    if sha == head:
        where = "HEAD is still there"
    elif git("merge-base", "--is-ancestor", sha, "HEAD") is not None:
        n = int(git("rev-list", "--count", sha + "..HEAD") or 0)
        where = "HEAD is %s, %s" % ((head or "?")[:7], p(AMBER, "%d commit%s on" % (n, "" if n == 1 else "s")))
    else:
        where = "HEAD is %s, %s" % ((head or "?")[:7], p(AMBER, "not a descendant (rebased?)"))
    out.append("reviewed %s · %s" % (sha[:7], where))

    # What was uncommitted when the review ran: path -> content hash (None for
    # a deleted file). A review from before that was recorded has only counts.
    then = m.get("uncommitted_files")
    counts = m.get("uncommitted") or {}
    n_then = len(then) if then is not None else sum(counts.values())
    status = git("status", "--porcelain=v1", "--untracked-files=all", "-z", raw=True) or ""
    dirty_now = {}
    entries = status.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        dirty_now[e[3:]] = "untracked" if e.startswith("??") else "tracked"
        if e[0] in "RC":
            i += 1   # a rename's old name follows
    files = lambda n: "none" if not n else "%d file%s" % (n, "" if n == 1 else "s")
    out.append("uncommitted then: %s · now: %s" % (files(n_then), files(len(dirty_now))))
    unknown_then = then is None and n_then > 0
    if unknown_then:
        out.append(p(AMBER, "this review ran before uncommitted files were recorded: which %s it saw is not known," % files(n_then)))
        out.append(p(AMBER, "so a line it cites in one of them may not be the line the reviewed commit has"))
    then = then or {}

    names = lambda *a: set((git("diff", "--name-only", "-z", *a, raw=True) or "").split("\0")) - {""}
    committed = names(sha, "HEAD")
    differs = names(sha)   # the reviewed commit against the working tree
    same_as_then = {f for f, h in then.items() if blob(f) == h}
    changed = (differs | set(dirty_now) | set(then)) - same_as_then
    out.append("")
    if not changed:
        out.append(p(GREEN, "nothing has changed since the review"))
    else:
        out.append("changed since the review: %s" % files(len(changed)))
        width = max(len(f) for f in sorted(changed)[:40])
        for f in sorted(changed)[:40]:
            how = []
            if f in committed:
                how.append("committed")
            if f in then:
                how.append("uncommitted then, different now")
            elif f in dirty_now:
                how.append("uncommitted" + (" (untracked)" if dirty_now[f] == "untracked" else ""))
            out.append("  %-*s  %s" % (width, f, ", ".join(how) or "committed"))
        if len(changed) > 40:
            out.append("  … and %d more" % (len(changed) - 40))

    md = os.path.join(folder, r["base"] + ".md")
    cites = [c for c in citations(body(md))
             if git("cat-file", "-e", "%s:%s" % (sha, c[0])) is not None or os.path.exists(c[0])]
    out.append("")
    if not cites:
        out.append("the review cites no file:line")
        return out
    out.append("cited in the review: %d" % len(cites))
    base = (m.get("base") or {}).get("merge_base")
    width = max(len("%s:%d" % c[:2]) + (len("-%d" % c[2]) if c[2] != c[1] else 0) for c in cites)
    for path, lo, hi in cites:
        label = "%s:%d%s" % (path, lo, "-%d" % hi if hi != lo else "")
        in_commit = git("cat-file", "-e", "%s:%s" % (sha, path)) is not None
        if path in then and path not in same_as_then:
            # Its lines were those of a working copy that is gone.
            verdict = p(AMBER, "uncommitted then and different now: its lines cannot be compared")
        else:
            # What the reviewer read: the working copy if it was uncommitted
            # then (and is the same now), else the reviewed commit's.
            as_then = [] if path in same_as_then else [sha]
            if not base:
                origin = None
            elif git("cat-file", "-e", "%s:%s" % (base, path)) is None:
                origin = p(TEAL, "new on this branch")
            else:
                hs = hunks(base, *as_then, "--", path)
                origin = None if hs is None else (
                    p(TEAL, "changed on this branch") if touched(hs, lo, hi, 1)
                    else p(GREY, "not changed on this branch"))
            if path in same_as_then:
                since = p(GREEN, "unchanged (uncommitted then, the same now)")
            elif not in_commit:
                since = p(AMBER, "not in the reviewed commit")
            elif not os.path.exists(path):
                since = p(AMBER, "file gone since")
            else:
                hs = hunks(sha, "--", path) or []
                if touched(hs, lo, hi, 0):
                    hc = hunks(sha, "HEAD", "--", path) or []
                    since = p(AMBER, "changed since (%s)" % ("committed" if touched(hc, lo, hi, 0) else "uncommitted"))
                else:
                    at = moved(hs, lo)
                    since = p(GREEN, "unchanged") + (", now line %d" % at if at != lo else "")
            verdict = " · ".join(x for x in (origin, since) if x)
            if unknown_then:
                verdict += p(GREY, " (if it was committed then)")
        out.append("  %-*s  %s" % (width, label, verdict))
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
    if argv[:1] == ["compare"]:
        if not folder:
            raise SystemExit("no .droid-reviews/ in this repo, so nothing to compare")
        color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        print("\n".join(compare(folder, argv[1] if len(argv) > 1 else "last", color)))
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
