#!/usr/bin/env python3
"""Play scripted runs into .droid-reviews/ so the band above the prompt has
something to draw: no droid, no model cost. Run it while a
Claude Code session with the band is open there, and watch.

    demo-bar.py            # one pass, about half a minute, then the demo's files are removed
    demo-bar.py --loop     # again and again until ^C
    demo-bar.py --keep     # leave the finished rows up afterwards

Three rows, each showing one thing the bar does:
  A  has history (~10s): grows to the stop, bounces there, rests, finishes late.
  B  has no history: the blob flies wall to wall, then the run fails.
  C  has history (~12s) but finishes early at 6s: the rush from part-way.

Each demo run's model is an id of its own (demo-a, ...), so its estimate
comes only from the demo's own history log and the real runs' do not move.
"""

import datetime
import json
import os
import pathlib
import signal
import sys
import time

FOLDER = pathlib.Path(__file__).resolve().parents[3] / ".droid-reviews"  # this repo's, wherever it is run from
PREFIX = "00000000-000000-demo-"  # sorts first, and says what it is
PID = os.getpid()  # alive while the demo plays: the band calls a run with a gone pid stopped

ROWS = {
    "a": {"kind": "review", "model_name": "GLM-5.3-Flash", "price": 0.5, "past": 10},
    "b": {"kind": "feedback", "model_name": "Muse Spark 1.2", "price": 0.4, "past": None},
    "c": {"kind": "review", "model_name": "Gemini 3.8 Flash", "price": 1, "effort": "high", "past": 12},
}
# (second, row, what happens): "start", a tool call as droid's log writes it, or how it ended.
SCRIPT = [
    (0, "a", "start"),
    (0, "b", "start"),
    (1, "a", "Skill review"),
    (2, "b", "Read README.md"),
    (3, "a", "Execute git diff --stat origin/master...HEAD"),
    (4, "c", "start"),
    (5, "b", "Grep band"),
    (6, "a", "Read skills/droid-reviews/hooks/rows.ts"),
    (7, "c", "Read AGENTS.md"),
    (9, "a", "Execute npm test"),
    (10, "c", "ok"),
    (12, "b", "Read skills/droid-reviews/hooks/band.tsx"),
    (16, "a", "ok"),
    (20, "b", "failed"),
]
HOLD_S = 8  # the finished rows stay this long before the files go


def iso(t):
    return datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def write(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def mine():
    return sorted(FOLDER.glob(PREFIX + "*"))


def clean(*_):
    for p in mine():
        p.unlink(missing_ok=True)
    if _:
        sys.exit(130)


def play():
    t0 = time.time()
    turns = {k: 0 for k in ROWS}
    started = {}
    lines = {k: [] for k in ROWS}

    def stamp(k):
        s = int(time.time() - started[k])
        return "[%dm%02ds]" % (s // 60, s % 60)

    def save(k, **fields):
        row = ROWS[k]
        meta = {"status": "running", "kind": row["kind"], "model": "demo-" + k, "model_name": row["model_name"],
                "price": row["price"], "effort": row.get("effort"), "round": 1, "pid": PID,
                "started": iso(started[k])}
        meta.update(fields)
        write(FOLDER / (PREFIX + k + ".json"), json.dumps(meta))
        write(FOLDER / (PREFIX + k + ".log"), "\n".join(lines[k]) + "\n")

    # Earlier runs of the same model: a log with no .json beside it counts toward
    # a bar's estimate and is never shown as a row.
    for k, row in ROWS.items():
        if row["past"]:
            write(FOLDER / (PREFIX + k + "-past.log"),
                  "[0m01s] started demo-%s (reasoning high) session past\n[0m%02ds] done · 5 turns · %ds\n"
                  % (k, row["past"], row["past"]))

    for at, k, what in SCRIPT:
        time.sleep(max(0, t0 + at - time.time()))
        if what == "start":
            started[k] = time.time()
            lines[k].append("%s started demo-%s (reasoning high) session demo-%s" % (stamp(k), k, k))
            save(k)
        elif what in ("ok", "failed"):
            took = int(time.time() - started[k])
            lines[k].append("%s done · %d turns · %ds" % (stamp(k), turns[k], took))
            save(k, status=what, finished=iso(time.time()), duration_s=took, turns=turns[k],
                 error="demo: a scripted failure" if what == "failed" else None)
        else:
            turns[k] += 1
            lines[k].append("%s turn %d · %s" % (stamp(k), turns[k], what))
            save(k)
    time.sleep(HOLD_S)


def main():
    args = set(sys.argv[1:])
    if args - {"--loop", "--keep"}:
        sys.exit(__doc__)
    FOLDER.mkdir(exist_ok=True)
    signal.signal(signal.SIGINT, clean)
    signal.signal(signal.SIGTERM, clean)
    clean()
    while True:
        play()
        if "--loop" not in args:
            break
        clean()
    if "--keep" not in args:
        clean()


main()
