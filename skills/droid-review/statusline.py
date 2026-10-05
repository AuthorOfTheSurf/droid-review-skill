#!/usr/bin/env python3
"""droid reviews in Claude Code's status line: one row per review running in
this repo, under whatever status line you already have.

    ◐ droid-review (GLM-5.3-Flash)        [ 0:25 / ~0:40               ]  reading files · turn 3 · Read src/auth.ts
    ◐ droid-review 2 (Gemini 3.8 Flash)   [ 4:12 / ~1:30               ]  running checks for 0:50 · turn 9 · Execute npm test
    ✓ droid-feedback (GPT-6 Luna max)     [ done in 2:14 · 21 turns    ]  3m ago · not triaged yet

It reads what droid-review.sh writes to .droid-reviews/: each run's .json
(status, model, round, start, pid) and the end of its .log (the turn and the
tool calls droid has made). "droid-review 2" is a re-check (--session), the
second round; the brackets hold the model, and the effort if one was named.

The bar is one piece: its text sits inside it and its ground fills from the
left as time passes, measured against the median time of this model's
finished runs of the same kind (review or feedback, first round or re-check)
in the same folder. It reaches four fifths at that estimate and stops there,
turning amber once the run is past it: how much is left is not known, and
the open fifth says so. Only a finished run fills the bar: the same bar then
holds the result. Without any history a block drifts across it instead.

After the bar comes what droid is doing, worked out from the kinds of tool it
called in its last three turns, not from what the calls said: reading files
(Read, Grep, Glob, LS, and commands that only look, such as git diff),
running checks (any other command), researching (WebSearch, FetchUrl),
planning (TodoWrite), working (any other tool), and thinking when nothing has
been logged for half a minute, since droid logs tool calls and neither its
reasoning nor the writing of its answer. The log does say when a command
comes back, so a check still going after half a minute stays "running
checks" and one that has returned does not. Either way the row then says for
how long.

A finished run keeps its row a while: its result, how long ago it ended, and
what has come of it — "not triaged yet", then the note the triaging agent
left (droid-review.sh --note). The row goes fifteen minutes after it ended,
or after that note if it came later; one still not triaged stays an hour.

Nothing running, nothing printed — your status line looks as it did.

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
                  alive, clock, find_reviews, log_ends, log_tail, silent_for)

SHOW_FINISHED_S = 900     # a finished row stays this long after the last thing that happened to it
SHOW_UNTRIAGED_S = 3600   # and one nobody has said anything about yet, this long
SPIN = "◐◓◑◒"
# Escapes that take no width: colours.
ANSI = re.compile(r"\033\[[0-9;]*m")


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
    """(kind, model, is a re-check) -> finished durations in seconds: from
    .json, and from the .log of runs older than the metadata (their first line
    names the model, their last says done in N seconds; counted as first
    rounds of a review). A re-check takes a fraction of a first review, and
    feedback as long as its ask, so each is timed against its own kind."""
    out, seen = {}, set()
    for m in runs:
        seen.add(m["_name"])
        if m.get("status") == "ok" and m.get("model") and m.get("duration_s") is not None:
            out.setdefault(timed_as(m), []).append(m["duration_s"])
    for name in os.listdir(folder):
        if not name.endswith(".log") or name[:-4] in seen:
            continue
        first, last = log_ends(os.path.join(folder, name))
        s, d = STARTED.match(first or ""), DONE.search(last or "")
        if s and d:
            out.setdefault(("review", s.group(1), False), []).append(int(d.group(1)))
    return out


def timed_as(m):
    return (m.get("kind") or "review", m.get("model"), (m.get("round") or 1) > 1)


BAR_W = 28   # cells between the brackets: room for "interrupted after 1:02:33"
# Grounds for the bar (background colours) and the text that sits on them.
ON_GREEN, ON_AMBER, ON_RED, ON_TEAL, ON_EMPTY = (
    "\033[48;2;32;110;58m", "\033[48;2;140;98;20m", "\033[48;2;150;44;40m",
    "\033[48;2;30;104;96m", "\033[48;2;46;46;46m")
INK = "\033[1;97m"   # bold bright white: Claude Code dims a status line's default colour


def bar(text, ground, fraction=1.0, now=None):
    """One bar with its text inside: [ 0:25 / ~0:40      ], the first
    fraction of its cells on the ground colour. fraction None is a run with
    nothing to measure against: a block drifts across instead."""
    cells = (" " + text).ljust(BAR_W)[:BAR_W]
    if fraction is None:
        at = int(now or 0) % (BAR_W - 3)
        parts = ((ON_EMPTY, cells[:at]), (ground, cells[at:at + 4]), (ON_EMPTY, cells[at + 4:]))
    else:
        n = max(0, min(BAR_W, int(BAR_W * fraction)))
        parts = ((ground, cells[:n]), (ON_EMPTY, cells[n:]))
    return GREY + "[" + RESET + "".join(g + INK + c + RESET for g, c in parts if c) + GREY + "]" + RESET


RUNNING_FULL = 0.8


def progress(elapsed, estimate):
    """How full a running bar is: RUNNING_FULL at the estimate, and no more
    however late the run is. The rest is what nobody knows; a bar is full
    when the run is done."""
    return RUNNING_FULL * min(1.0, elapsed / estimate)


READS = {"Read", "Grep", "Glob", "LS"}
WEB = {"WebSearch", "FetchUrl"}
# Commands that only look. Anything else droid executes is taken for a check.
LOOKS = {"git", "cat", "ls", "grep", "rg", "sed", "head", "tail", "find", "wc", "diff", "awk", "nl",
         "tree", "stat", "file", "which", "command", "echo", "printf", "pwd", "jq"}
CALL = re.compile(r"^\[[^]]*\] turn (\d+) · (\S+) ?(.*)$")
# A command came back: "turn 6 ↳ Execute returned in 55s" (", 1 still running").
BACK = re.compile(r"^\[[^]]*\] turn \d+ ↳ Execute \w+ in \d+s(, \d+ still running)?$")
QUIET_S = 30    # nothing logged this long: droid is thinking, or a command is still going
RECENT_TURNS = 3


def activity(tool, target):
    """The kind of work one tool call is, from the tool alone (and for
    Execute, the command's first word)."""
    if tool in READS:
        return "reading"
    if tool in WEB:
        return "researching"
    if tool == "TodoWrite":
        return "planning"
    if tool in ("Skill", "ToolSearch"):
        return None   # setting up, not the work
    if tool == "Execute":
        cmd = re.sub(r"^(?:[A-Za-z_]\w*=\S*\s+)+", "", uncd(target))   # VAR=x ...
        word = os.path.basename(cmd.split()[0]).rstrip(");") if cmd.split() else ""
        return "reading" if word in LOOKS else "running"
    return "working"


def uncd(command):
    """A command without the "cd somewhere &&" it opens with: what it runs."""
    return re.sub(r"^(?:\(?\s*cd\s+\S+\s*(?:&&|;)\s*)+", "", command)


def ago(seconds):
    """How long since a run ended, in a row: "just now", "3m ago", "2h ago"."""
    m = int(seconds) // 60
    return "just now" if m < 1 else "%dm ago" % m if m < 60 else "%dh ago" % (m // 60)


def phase(lines, quiet, kind="review"):
    """What droid is doing, in a word or two: the commonest kind of call in
    its last RECENT_TURNS turns (the latest wins a tie). Gone quiet, it is
    thinking, unless a command it started has not come back."""
    calls, going = [], None   # going: the kind of command still out, if one is
    for line in lines:
        back = BACK.match(line)
        if back:
            going = going if back.group(1) else None
            continue
        hit = CALL.match(line)
        if hit:
            a = activity(hit.group(2), hit.group(3))
            if a:
                calls.append((int(hit.group(1)), a))
            if hit.group(2) == "Execute":
                going = a
    if not calls:
        return "starting"
    recent = [a for turn, a in calls if turn > calls[-1][0] - RECENT_TURNS]
    if quiet >= QUIET_S:
        top = going or "thinking"
    else:
        top = max(set(recent), key=lambda a: (recent.count(a), len(recent) - recent[::-1].index(a)))
    return {"reading": "reading files", "running": "running checks" if kind == "review" else "running commands"}.get(top, top)


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


def triage(m, now):
    """What has come of a finished review: the note the agent that triaged it
    left (droid-review.sh --note), and when; or that there is none yet.
    Returns (text, seconds since the note or None)."""
    notes = [n for n in m.get("responses") or [] if isinstance(n, dict) and n.get("text")]
    if not notes:
        return AMBER + "not triaged yet" + RESET, None
    noted = since(notes[-1].get("at"), now)
    return (GREEN + "triaged" + RESET + GREY + (" " + ago(noted) if noted is not None else "") + ": "
            + " ".join(str(notes[-1]["text"]).split()) + RESET), noted


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
        m["_triage"], m["_noted"] = triage(m, now)
    # A finished row stays a quarter of an hour after it ended, or after it was
    # triaged if that came later; a review still waiting to be triaged, an hour.
    def lingers(m):
        last = min(m["_ago"], m["_noted"]) if m["_noted"] is not None else m["_ago"]
        return last <= SHOW_FINISHED_S or (m["_status"] == "ok" and m["_noted"] is None and m["_ago"] <= SHOW_UNTRIAGED_S)
    shown = [m for m in runs if m["_ago"] is None or lingers(m)]
    if not shown:
        return []
    shown.sort(key=lambda r: r.get("started") or "")
    # "droid-review 2 (Gemini 3.8 Flash)": the command that ran, the round if
    # it is a re-check, and in the brackets droid's name for the model (else
    # its id) with the effort when one was named. In the terminal's own
    # colour, padded to the widest shown so the bars line up.
    def who_of(m):
        label = "droid-feedback" if m.get("kind") == "feedback" else "droid-review"
        if (m.get("round") or 1) > 1:
            label += " %d" % m["round"]
        model = m.get("model_name") or m.get("model") or "?"
        return "%s (%s%s)" % (label, model, " " + m["effort"] if m.get("effort") else "")
    width = max(len(who_of(m)) for m in shown)
    for m in shown:
        status = m["_status"]
        who = who_of(m).ljust(width)
        if status == "running":
            if hist is None:
                hist = history(folder, runs)
            elapsed = since(m.get("started"), now) or 0
            past = hist.get(timed_as(m)) or []   # by id, not name
            estimate = statistics.median(past) if past else None
            lines = log_tail(os.path.join(folder, m["_name"] + ".log"))
            # The last call it made, as "turn 6 · Execute npm test".
            last = next((c for c in map(CALL.match, reversed(lines)) if c), None)
            doing = "turn %s · %s" % (last.group(1), " ".join((last.group(2), uncd(last.group(3)))).strip()) if last else ""
            quiet = silent_for(folder, m, now)
            now_doing = phase(lines, quiet, m.get("kind") or "review")
            if quiet >= QUIET_S and now_doing != "starting":
                doing = "for %s%s" % (clock(quiet), " · " + doing if doing else "")   # thinking for, running checks for
            if estimate:
                meter = bar("%s / ~%s" % (clock(elapsed), clock(estimate)),
                            ON_AMBER if elapsed > estimate else ON_GREEN, progress(elapsed, estimate))
            else:
                meter = bar(clock(elapsed), ON_TEAL, None, now)
            line = "%s %s  %s  %s%s" % (TEAL + SPIN[int(now) % len(SPIN)] + RESET, who, meter,
                                        INK + now_doing + RESET,
                                        GREY + (" " if doing.startswith("for ") else " · ") + doing + RESET if doing else "")
        else:
            took = clock(m["duration_s"]) if m.get("duration_s") is not None else "?"
            when = ago(m["_ago"])
            # A finished run says so in the same bar, full, in its result's colour.
            if status == "ok":
                line = "%s %s  %s  %s" % (
                    GREEN + BOLD + "✓" + RESET, who, bar("done in %s · %s turns" % (took, m.get("turns")), ON_GREEN),
                    GREY + when + " · " + RESET + m["_triage"])
            elif status == "failed":
                err = " ".join(str(m.get("error") or "").split())
                line = "%s %s  %s  %s" % (RED + BOLD + "✗" + RESET, who, bar("failed after " + took, ON_RED),
                                          GREY + when + (" · " + err if err else "") + RESET)
            elif status == "interrupted":
                line = "%s %s  %s  %s" % (AMBER + BOLD + "✗" + RESET, who, bar("interrupted after " + took, ON_AMBER),
                                          GREY + when + RESET)
            else:
                line = "%s %s  %s  %s" % (AMBER + BOLD + "✗" + RESET, who, bar("stopped", ON_AMBER),
                                          GREY + when + " · its process is gone" + RESET)
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
