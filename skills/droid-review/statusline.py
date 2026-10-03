#!/usr/bin/env python3
"""droid reviews in Claude Code's status line: one row per review running in
this repo, under whatever status line you already have.

    ◐ droid · review   · GLM-5.3-Flash     ▓▓▓▓▓▓░░░░  0:25 / ~0:40  turn 3 · Execute git diff
    ◐ droid · review 2 · Gemini 3.8 Flash  ▓▓░░░░░░░░  0:12 / ~1:30  turn 1 · Read README.md
    ✓ droid · review   · GPT-6 Luna max    ██████████  done in 2:14 · 21 turns · .droid-reviews/…-gpt-6-luna.md

It reads what droid-review.sh writes to .droid-reviews/: each run's .json
(status, model, round, start, pid) and the last line of its .log (turn and
what droid is doing). "review 2" is a re-check (--session), the second round.
The estimate is the median time of this model's finished runs of the same
kind (first review or re-check) in the same folder; without any, the bar
just pulses. A finished run stays for
a minute with its result, then the row goes. Nothing running, nothing
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
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime

sys.dont_write_bytecode = True   # no __pycache__ beside the skill
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runs import (AMBER, BOLD, GREEN, GREY, RED, RESET, STALE_S, TEAL,  # noqa: E402,F401
                  alive, clock, find_reviews, log_ends, silent_for)

SHOW_FINISHED_S = 60
SPIN = "◐◓◑◒"
# Escapes that take no width: colors, and OSC 8 link open/close (ESC ] 8 ;; url ESC \).
ANSI = re.compile(r"\033\[[0-9;]*m|\033\]8;;[^\033]*\033\\")


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
    """(model, is a re-check) -> finished durations in seconds: from .json, and
    from the .log of runs older than the metadata (their first line names the
    model, their last says done in N seconds; counted as first rounds). A
    re-check takes a fraction of a first review, so the two are timed apart."""
    out, seen = {}, set()
    for m in runs:
        seen.add(m["_name"])
        if m.get("status") == "ok" and m.get("model") and m.get("duration_s") is not None:
            out.setdefault((m["model"], (m.get("round") or 1) > 1), []).append(m["duration_s"])
    for name in os.listdir(folder):
        if not name.endswith(".log") or name[:-4] in seen:
            continue
        first, last = log_ends(os.path.join(folder, name))
        s, d = STARTED.match(first or ""), DONE.search(last or "")
        if s and d:
            out.setdefault((s.group(1), False), []).append(int(d.group(1)))
    return out


def bar(elapsed, estimate, width=10):
    if not estimate:
        pos = int(elapsed) % width   # no estimate: a pulse, so it still looks alive
        return GREY + "░" * pos + TEAL + "▓" + GREY + "░" * (width - pos - 1) + RESET
    filled = min(width, int(width * elapsed / estimate))
    color = AMBER if elapsed > estimate else GREEN
    return color + "▓" * filled + GREY + "░" * (width - filled) + RESET


def solid(color, width=10):
    """The bar of a finished run: full, in its result's colour."""
    return color + "█" * width + RESET


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
    # A cut can land inside a link; closing one that is not open is harmless.
    return "".join(out) + "…" + LINK_CLOSE + RESET


LINK_CLOSE = "\033]8;;\033\\"


def link(text, path):
    """text as a clickable file link (OSC 8) in terminals that support it."""
    if not text:
        return ""
    return "\033]8;;file://%s\033\\%s%s" % (path, text, LINK_CLOSE)


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
        ago = silent_for(folder, m, now) if os.path.exists(os.path.join(folder, m["_name"] + ".log")) else float("inf")
    return ago


def rows(folder, now, columns):
    runs = load_runs(folder)
    if not runs:
        return []
    hist = None
    out = []
    for m in runs:
        m["_status"] = m["status"]
        if m["status"] == "running" and (not alive(m.get("pid")) or silent_for(folder, m, now) > STALE_S):
            m["_status"] = "stopped"
        m["_ago"] = None if m["_status"] == "running" else ended_ago(folder, m, now)
    shown = [m for m in runs if m["_ago"] is None or m["_ago"] <= SHOW_FINISHED_S]
    if not shown:
        return []
    shown.sort(key=lambda r: r.get("started") or "")
    # Pad both columns to the widest shown, so stacked rows line up:
    # "droid · review 2 · grok-4.7" over "droid · review   · glm-5.3-flash high".
    def label_of(m):
        label = "feedback" if m.get("kind") == "feedback" else "review"
        if (m.get("round") or 1) > 1:
            label += " %d" % m["round"]   # a re-check: short, and timed against re-checks
        return label
    lwidth = max(len(label_of(m)) for m in shown)
    name = lambda m: m.get("model_name") or m.get("model") or "?"   # droid's display name, else the id
    width = max(len(name(m)) + len(" " + m["effort"] if m.get("effort") else "") for m in shown)
    for m in shown:
        status = m["_status"]
        label = label_of(m)
        model = name(m)
        effort = (" " + m["effort"]) if m.get("effort") else ""
        who = "droid%s · %s%s%s%s · %s%s%s%s%s%s" % (GREY, RESET, label, " " * (lwidth - len(label)), GREY,
                                                       RESET + TEAL, model,
                                       RESET + GREY, effort, RESET, " " * (width - len(model + effort)))
        if status == "running":
            if hist is None:
                hist = history(folder, runs)
            elapsed = since(m.get("started"), now) or 0
            past = hist.get((m.get("model"), (m.get("round") or 1) > 1)) or []   # by id, not name
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
            # A finished run says so loudly: a solid bar where the progress
            # bar was, and the result in bold, in the run's colour.
            if status == "ok":
                review = (m.get("files") or {}).get("review") or ""
                line = "%s %s  %s  %s · %s turns · %s" % (
                    GREEN + BOLD + "✓" + RESET, who, solid(GREEN), GREEN + BOLD + "done in " + took + RESET,
                    m.get("turns"), GREY + link(review, os.path.join(os.path.dirname(folder), review)) + RESET)
            elif status == "failed":
                err = " ".join(str(m.get("error") or "").split())
                line = "%s %s  %s  %s  %s" % (RED + BOLD + "✗" + RESET, who, solid(RED),
                                              RED + BOLD + "failed after " + took + RESET, GREY + err + RESET)
            elif status == "interrupted":
                line = "%s %s  %s  %s" % (AMBER + BOLD + "✗" + RESET, who, solid(AMBER),
                                          AMBER + BOLD + "interrupted after " + took + RESET)
            else:
                line = "%s %s  %s  %s" % (AMBER + BOLD + "✗" + RESET, who, solid(AMBER),
                                          AMBER + BOLD + "stopped" + RESET + GREY + " (its process is gone)" + RESET)
        out.append(fit(line, columns))
    return out


ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def requote(words):
    """Words the shell already split and unquoted, as a command line again.
    Leading NAME=value words quote only the value: a quoted whole word would be
    a command name to the shell, not an assignment."""
    out, leading = [], True
    for w in words:
        a = ASSIGNMENT.match(w) if leading else None
        if a:
            out.append(a.group(0) + shlex.quote(w[a.end():]))
        else:
            leading = False
            out.append(shlex.quote(w))
    return " ".join(out)


def main(argv):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    # Anything after -- is the status line you already had: run it on the same
    # input and print it first, so these rows stack under it.
    # The shell that ran this already split and unquoted the words: quote them
    # again and hand them back to a shell, so quoting survives and a leading
    # VAR=value still sets a variable. One word is a whole command line already.
    if "--" in argv:
        cmd = argv[argv.index("--") + 1:]
        if cmd:
            try:
                r = subprocess.run(cmd[0] if len(cmd) == 1 else requote(cmd), shell=True, input=raw,
                                   capture_output=True, text=True, timeout=5)
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
