#!/usr/bin/env python3
"""droid reviews in Claude Code's status line: one row per review running in
this repo, under whatever status line you already have.

    ◐ droid glm-5.3-flash high  ▓▓▓▓▓▓░░░░  0:25 / ~0:40  turn 3 · Execute git diff
    ✓ droid gemini-3.8-flash    done in 1:32 · 14 turns · .droid-reviews/…-gemini-3.8-flash.md

It reads what droid-review.sh writes to .droid-reviews/: each run's .json
(status, model, start, pid) and the last line of its .log (turn and what droid
is doing). The estimate is the median time of this model's finished runs in
the same folder; without any, the bar just pulses. A finished run stays for
30 seconds with its result, then the row goes. Nothing running, nothing
printed — your status line looks as it did.

In ~/.claude/settings.json, with your current status line command (if any)
after the `--`, so it prints first and these rows go under it:

    "statusLine": {
      "type": "command",
      "command": "python3 /path/to/droid-review-skill/skills/droid-review/statusline.py -- python3 ~/.claude/my-statusline.py",
      "refreshInterval": 2
    }

refreshInterval keeps the elapsed time moving while the session is idle (a
review usually runs in the background while you wait). Remove the setting, or
put your old command back, to undo.
"""

import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime

SHOW_FINISHED_S = 30
SPIN = "◐◓◑◒"
RESET = "\033[0m"
TEAL, GREEN, AMBER, RED, GREY = (
    "\033[38;2;94;196;182m", "\033[38;2;63;185;80m", "\033[38;2;230;180;80m",
    "\033[38;2;248;81;73m", "\033[38;5;245m")
# Escapes that take no width: colors, and OSC 8 link open/close (ESC ] 8 ;; url ESC \).
ANSI = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033]*\033\\")


def find_reviews(start):
    """The nearest .droid-reviews/ at or above start, or None."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, ".droid-reviews")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def alive(pid):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, TypeError, ValueError):
        return True   # exists but not ours, or unknowable: do not call it dead
    return True


def load_runs(folder):
    runs = []
    for name in os.listdir(folder):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name)) as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue   # half-written or not ours
        if isinstance(m, dict) and m.get("status"):
            m["_name"] = name[:-5]
            runs.append(m)
    return runs


DONE = re.compile(r"done · \S+ turns · (\d+)s$")
STARTED = re.compile(r"^\[[^]]*\] started (\S+) ")


def history(folder, runs):
    """model -> finished durations in seconds: from .json, and from the .log of
    runs older than the metadata (their first line names the model, their last
    says done in N seconds)."""
    out, seen = {}, set()
    for m in runs:
        seen.add(m["_name"])
        if m.get("status") == "ok" and m.get("model") and m.get("duration_s") is not None:
            out.setdefault(m["model"], []).append(m["duration_s"])
    for name in os.listdir(folder):
        if not name.endswith(".log") or name[:-4] in seen:
            continue
        first, last = log_ends(os.path.join(folder, name))
        s, d = STARTED.match(first or ""), DONE.search(last or "")
        if s and d:
            out.setdefault(s.group(1), []).append(int(d.group(1)))
    return out


def log_ends(path):
    """First and last non-empty line of a log, reading only its ends."""
    try:
        with open(path, "rb") as f:
            first = f.readline().decode("utf-8", "replace").strip()
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", "replace").strip().splitlines()
    except OSError:
        return None, None
    return first, (tail[-1] if tail else None)


def clock(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60) if s < 3600 else "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def bar(elapsed, estimate, width=10):
    if not estimate:
        pos = int(elapsed) % width   # no estimate: a pulse, so it still looks alive
        return GREY + "░" * pos + TEAL + "▓" + GREY + "░" * (width - pos - 1) + RESET
    filled = min(width, int(width * elapsed / estimate))
    color = AMBER if elapsed > estimate else GREEN
    return color + "▓" * filled + GREY + "░" * (width - filled) + RESET


def fit(text, columns):
    """Cut a colored line to columns visible characters."""
    if len(ANSI.sub("", text)) <= columns:
        return text
    out, n = [], 0
    for part in re.split("(%s)" % ANSI.pattern, text):
        if part and ANSI.fullmatch(part):
            out.append(part)
            continue
        room = columns - 1 - n
        if room <= 0:
            break
        out.append(part[:room])
        n += len(part[:room])
    return "".join(out) + "…" + RESET


def link(text, path):
    """text as a clickable file link (OSC 8) in terminals that support it."""
    if not text:
        return ""
    return "\033]8;;file://%s\033\\%s\033]8;;\033\\" % (path, text)


def since(iso, now):
    try:
        return now - datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


def ended_ago(folder, m, now):
    """Seconds since a run ended; a "stopped" one has no finish recorded, so
    its log's last write stands in."""
    ago = since(m.get("finished"), now)
    if ago is None:
        try:
            ago = now - os.path.getmtime(os.path.join(folder, m["_name"] + ".log"))
        except OSError:
            ago = float("inf")
    return ago


def rows(folder, now, columns):
    runs = load_runs(folder)
    if not runs:
        return []
    hist = None
    out = []
    for m in runs:
        m["_status"] = m["status"]
        if m["status"] == "running" and not alive(m.get("pid")):
            m["_status"] = "stopped"
        m["_ago"] = None if m["_status"] == "running" else ended_ago(folder, m, now)
    shown = [m for m in runs if m["_ago"] is None or m["_ago"] <= SHOW_FINISHED_S]
    if not shown:
        return []
    shown.sort(key=lambda r: r.get("started") or "")
    # Pad "<model> <effort>" to the widest one shown, so stacked rows line up.
    width = max(len(m.get("model") or "?") + len(" " + m["effort"] if m.get("effort") else "") for m in shown)
    for m in shown:
        status = m["_status"]
        label = "droid" if m.get("kind") != "feedback" else "droid feedback"
        model = m.get("model") or "?"
        effort = (" " + m["effort"]) if m.get("effort") else ""
        pad = " " * (width - len(model + effort))
        who = "%s %s%s%s%s%s" % (label, TEAL, model, RESET + GREY, effort, RESET) + pad
        if status == "running":
            if hist is None:
                hist = history(folder, runs)
            elapsed = since(m.get("started"), now) or 0
            past = hist.get(model) or []
            estimate = statistics.median(past) if past else None
            timing = clock(elapsed) + (GREY + " / ~" + clock(estimate) + RESET if estimate else "")
            _, last = log_ends(os.path.join(folder, m["_name"] + ".log"))
            doing = re.sub(r"^\[[^]]*\]\s*", "", last or "")
            if doing.startswith("started "):
                doing = "starting"
            line = "%s %s  %s  %s  %s" % (TEAL + SPIN[int(now) % len(SPIN)] + RESET, who,
                                          bar(elapsed, estimate), timing, GREY + doing + RESET)
        else:
            took = clock(m["duration_s"]) if m.get("duration_s") is not None else "?"
            if status == "ok":
                review = (m.get("files") or {}).get("review") or ""
                line = "%s %s  done in %s · %s turns · %s" % (
                    GREEN + "✓" + RESET, who, took, m.get("turns"),
                    GREY + link(review, os.path.join(os.path.dirname(folder), review)) + RESET)
            elif status == "failed":
                err = " ".join(str(m.get("error") or "").split())
                line = "%s %s  failed after %s  %s" % (RED + "✗" + RESET, who, took, GREY + err + RESET)
            elif status == "interrupted":
                line = "%s %s  interrupted after %s" % (AMBER + "✗" + RESET, who, took)
            else:
                line = "%s %s  stopped (its process is gone)" % (AMBER + "✗" + RESET, who)
        out.append(fit(line, columns))
    return out


def main(argv):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    # Anything after -- is the status line you already had: run it on the same
    # input and print it first, so these rows stack under it.
    if "--" in argv:
        cmd = argv[argv.index("--") + 1:]
        if cmd:
            try:
                r = subprocess.run(" ".join(cmd), shell=True, input=raw, capture_output=True, text=True, timeout=5)
                if r.stdout.strip():
                    sys.stdout.write(r.stdout if r.stdout.endswith("\n") else r.stdout + "\n")
            except (OSError, subprocess.SubprocessError):
                pass
    ws = data.get("workspace") or {}
    folder = find_reviews(ws.get("current_dir") or data.get("cwd") or os.getcwd())
    if not folder:
        return
    try:
        columns = int(os.environ.get("COLUMNS") or 0) or 100
    except ValueError:
        columns = 100
    for line in rows(folder, time.time(), columns - 2):
        print(line)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:   # a status line must never take the rest down with it
        pass
