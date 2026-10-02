#!/usr/bin/env bash
# Run droid-review.sh's paths against stub-droid in a throwaway repo and check
# what each one leaves behind: exit code, stdout, the review file's header, and
# the run metadata (.json) — commit, base, uncommitted counts, status. Costs no
# model run: the stub answers `exec`, the real droid answers --help,
# --list-tools and --version (so the catalog is real). Prints one line per
# check and exits non-zero when any failed.
#
#   .claude/skills/maintain-droid-review-skill/regress.sh
set -uo pipefail
# Run from inside a droid-review fan-out (a reviewer running this suite), the
# child markers would leak into every run below and change what they do.
unset _DROID_REVIEW_CHILD _DROID_REVIEW_STAMP _DROID_REVIEW_CATALOG

here="$(cd "$(dirname "$0")" && pwd)"
r="$(cd "$here/../../.." && pwd)"
d="$r/skills/droid-review/droid-review.sh"
REAL_DROID="$(command -v droid)" || { echo "needs the real droid on PATH" >&2; exit 2; }
export REAL_DROID

t="$(mktemp -d)"
trap 'rm -rf "$t"' EXIT
mkdir -p "$t/bin" "$t/repo"
ln -sf "$here/stub-droid" "$t/bin/droid"
cd "$t/repo" || exit 2
git init -q -b master && git commit -q --allow-empty -m base
git checkout -q -b feat
echo a > committed && git add committed && git commit -q -m "feat: one commit"
echo s > staged && git add staged          # 1 staged
echo u >> committed                        # 1 unstaged
echo n > untracked                         # 3 untracked: one file, and two
mkdir newdir && echo a > newdir/a && echo b > newdir/b   # in a new folder git folds into one line

fails=0
check() {  # check <name> <command...>: passes when the command succeeds
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $name"; else echo "FAIL  $name"; fails=$((fails + 1)); fi
}
run() {  # run <outfile> <args...>: the script under the stub; sets RC
  local out="$1"; shift
  PATH="$t/bin:$PATH" "$d" "$@" > "$out" 2> "$out.err"; RC=$?
}
# json <file> <python expression over m>: true when it holds
json() { python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$1" "$2"; }
meta_of() { printf '%s' "${1%.md}.json"; }
newest_meta() { ls -t .droid-reviews/*.json | head -1; }
head_sha="$(git rev-parse HEAD)"
base_sha="$(git rev-parse master)"

# 1. A review.
run "$t/o1" --base master
md="$(sed -n 1p "$t/o1")"; m="$(meta_of "$md")"
check "review: exit 0"                     [ "$RC" = 0 ]
check "review: prints path and session"    [ "$(wc -l < "$t/o1")" -eq 2 ]
check "review: metadata next to it"        [ -f "$m" ]
check "review: status ok, times, pid"      json "$m" 'm["status"]=="ok" and m["started"] and m["finished"] and isinstance(m["pid"],int) and m["duration_s"]>=0'
check "review: head and branch"            json "$m" "m['head']=='$head_sha' and m['branch']=='feat' and m['head_subject']=='feat: one commit'"
check "review: base, 1 ahead, 0 behind"    json "$m" "m['base']['ref']=='master' and m['base']['sha']=='$base_sha' and m['base']['merge_base']=='$base_sha' and m['base']['ahead']==1 and m['base']['behind']==0"
check "review: uncommitted 1/1/3"          json "$m" 'm["uncommitted"]=={"staged":1,"unstaged":1,"untracked":3}'
check "review: diff counts tracked files"  json "$m" 'm["diff"]["files"]==2'
check "review: session, turns, droid ver"  json "$m" 'm["session"] and m["turns"]==2 and m["droid_version"]'
check "review: files point at each other"  json "$m" "m['files']['review']=='$md' and m['files']['log']=='${md%.md}.log'"
for f in round started finished model scope branch base "uncommitted at start" "diff reviewed" droid metadata session turns; do
  check "review: header has '$f'"          grep -q "^- $f: " "$md"
done
check "review: turns is the last header line" sh -c "sed -n '/^- /p' '$md' | head -20 | tail -1 | grep -q '^- turns: '"
check "review: .droid-reviews ignores itself" [ -z "$(git status --porcelain --untracked-files=all .droid-reviews)" ]

# 2. Continue it.
run "$t/o2" --base master --session last
m2="$(meta_of "$(sed -n 1p "$t/o2")")"
check "session last: exit 0"               [ "$RC" = 0 ]
check "session last: says continuing"      grep -q '^continuing ' "$t/o2.err"
check "session last: records what it continues" json "$m2" "m['continues']['review']=='$md'"
check "session last: same model"           json "$m2" 'm["model"]=="glm-5.3-flash" and m["effort"] is None'
check "review: droid's name for the model" json "$m" 'm["model_name"]=="GLM-5.3-Flash"'
check "review: round 1, no effort pinned"  json "$m" 'm["round"]==1 and m["effort"] is None'
check "session last: round 2"              json "$m2" 'm["round"]==2'
check "session last: title says round 2"   grep -qx '# droid review, round 2' "$(sed -n 1p "$t/o2")"
run "$t/o2b" --base master --session last
check "session last again: round 3"        json "$(meta_of "$(sed -n 1p "$t/o2b")")" 'm["round"]==3'

# A level named on the run is the run's, and a continuation keeps it.
run "$t/o2c" --base master "glm max"
run "$t/o2d" --base master --session last
check "named effort: used"                 json "$(meta_of "$(sed -n 1p "$t/o2c")")" 'm["effort"]=="max"'
check "named effort: kept by its re-check" json "$(meta_of "$(sed -n 1p "$t/o2d")")" 'm["effort"]=="max" and m["round"]==2'

# 3. Fan-out.
run "$t/o3" --base master --models glm,gemini
check "fan-out: exit 0"                    [ "$RC" = 0 ]
check "fan-out: two ok lines"              [ "$(grep -c "	ok	" "$t/o3")" = 2 ]
for p in $(grep '	' "$t/o3" | cut -f3); do
  check "fan-out: $(basename "$p") metadata ok" json "$(meta_of "$p")" 'm["status"]=="ok"'
done
idx="$(tail -1 "$t/o3")"
check "fan-out: index has started/branch"  sh -c "grep -Eq '^- started: [0-9]{4}-[0-9]{2}-[0-9]{2}T' '$idx' && grep -q '^- branch: feat at ' '$idx'"

# 4. Both fail without a word on stderr.
STUB_DROID_MODE=fail-silent run "$t/o4" --base master --models glm,gemini
check "fail-silent: exit 1"                [ "$RC" = 1 ]
check "fail-silent: both failed"           [ "$(grep -c "	failed	" "$t/o4")" = 2 ]
for j in $(ls -t .droid-reviews/*.json | head -2); do   # completion, then exit 1
  check "fail-silent: $(basename "$j") metadata failed" json "$j" 'm["status"]=="failed" and "exited 1" in m["error"]'
done

# 5. droid reports an error.
STUB_DROID_MODE=error run "$t/o5" --base master
check "error: exit non-zero"               [ "$RC" != 0 ]
check "error: says so"                     grep -q 'droid reported an error' "$t/o5.err"
check "error: metadata failed + message"   json "$(newest_meta)" 'm["status"]=="failed" and "stub: model unavailable" in m["error"] and m["finished"]'

# 6. droid prints something that is not JSON.
STUB_DROID_MODE=garbage run "$t/o6" --base master
check "garbage: exit non-zero"             [ "$RC" != 0 ]
check "garbage: metadata failed"           json "$(newest_meta)" 'm["status"]=="failed"'

# 7. Interrupted: TERM to the whole process group, as a supervisor stopping a
# background job does (and as Ctrl-C does with INT).
# The TERM goes once droid is running: once every run (1, or one per fan-out
# model) has written metadata that says "running".
interrupt() {  # interrupt <out> <runs> <args...>
  local out="$1" runs="$2"; shift 2
  PATH="$t/bin:$PATH" STUB_DROID_DELAY=2 python3 -c '
import glob, json, os, signal, subprocess, sys, time
def running():
    n = 0
    for f in glob.glob(".droid-reviews/*.json"):
        try:
            n += json.load(open(f)).get("status") == "running"
        except ValueError:
            pass
    return n
p = subprocess.Popen(sys.argv[3:], stdout=open(sys.argv[1], "w"), stderr=open(sys.argv[1] + ".err", "w"), start_new_session=True)
deadline = time.time() + 60
while running() < int(sys.argv[2]) and time.time() < deadline and p.poll() is None:
    time.sleep(0.2)
time.sleep(1)
os.killpg(p.pid, signal.SIGTERM)
rc = p.wait()
sys.exit(rc if rc >= 0 else 128 - rc)
' "$out" "$runs" "$d" "$@"
  RC=$?
}
interrupt "$t/o7" 1 --base master
m7="$(newest_meta)"
check "interrupt: exit 130"                [ "$RC" = 130 ]
check "interrupt: metadata interrupted"    json "$m7" 'm["status"]=="interrupted" and m["finished"]'
check "interrupt: log says interrupted"    sh -c "tail -1 '${m7%.json}.log' | grep -q 'interrupted$'"

interrupt "$t/o8" 2 --base master --models glm,gemini
check "fan-out interrupt: exit 130"        [ "$RC" = 130 ]
check "fan-out interrupt: both interrupted" [ "$(grep -c "	interrupted	" "$t/o8")" = 2 ]
for j in $(ls -t .droid-reviews/*.json | head -2); do
  check "fan-out interrupt: $(basename "$j") interrupted" json "$j" 'm["status"]=="interrupted"'
done

# 8. droid-feedback.
PATH="$t/bin:$PATH" "$r/skills/droid-feedback/droid-feedback.sh" --base master "is this sane" > "$t/o9" 2>&1; RC=$?
check "feedback: exit 0"                   [ "$RC" = 0 ]
check "feedback: metadata kind feedback"   json "$(newest_meta)" 'm["kind"]=="feedback" and m["asked"]=="is this sane"'

# 9. The status line, live: mid-run it shows the run and its turn; just after,
# the result. (Its own states are unit-tested in statusline_test.py, run below.)
sl() { echo "{\"workspace\":{\"current_dir\":\"$t/repo\"}}" | COLUMNS=200 python3 "$r/skills/droid-review/statusline.py" | sed 's/\x1b\[[0-9;]*m//g; s/\x1b\]8;;[^\x1b]*\x1b\\//g'; }
PATH="$t/bin:$PATH" STUB_DROID_DELAY=2 "$d" --base master --models glm,gemini > "$t/o10" 2>&1 &
live=""
for _ in $(seq 1 60); do
  sleep 0.5
  live="$(sl)"
  case "$live" in *"turn 1 · Read"*) break ;; esac
done
check "status line: a row per running model" [ "$(printf '%s\n' "$live" | grep -c '^[◐◓◑◒] droid · ')" = 2 ]
check "status line: shows the turn"        sh -c "printf '%s' \"\$1\" | grep -q 'turn 1 · Read README.md'" _ "$live"
wait
after="$(sl)"
# (droid-feedback finished moments ago too, so its row is there as well.)
check "status line: then both results"     sh -c "printf '%s' \"\$1\" | grep -q '^✓ droid · review *· Gemini 3.8 Flash .* done in ' && printf '%s' \"\$1\" | grep -q '^✓ droid · review *· GLM-5.3-Flash .* done in '" _ "$after"
check "status line: nothing still running" sh -c "! printf '%s' \"\$1\" | grep -q '^[◐◓◑◒]'" _ "$after"
check "status line: unit tests"            python3 "$here/statusline_test.py"

# 10. No run left a temp file or a "running" status behind.
check "no .tmp files left"                 [ -z "$(ls .droid-reviews/*.tmp 2>/dev/null)" ]
check "no run still marked running"        sh -c "! grep -l '\"status\": \"running\"' .droid-reviews/*.json"

echo
[ "$fails" = 0 ] && echo "all checks passed" || echo "$fails check(s) failed"
[ "$fails" = 0 ]
