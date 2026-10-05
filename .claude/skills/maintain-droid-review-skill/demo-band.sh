#!/usr/bin/env bash
# Watch the droid-review rows in the band of a real Claude Code session
# without spending a model run: runs stub reviews in this repo (stub-droid,
# slowed down), so a session open here shows them above its prompt.
# Deletes the stub reviews' files once their rows are gone, so they never count
# toward the time estimates or become what `--session last` continues.
#
#   .claude/skills/maintain-droid-review-skill/demo-band.sh [models] [seconds per event]
#   .claude/skills/maintain-droid-review-skill/demo-band.sh glm,gemini,luna 3
#
# Needs the band linked (README: "Live status in Claude Code").
set -euo pipefail
# Run from inside a droid-review fan-out (a reviewer trying this script), the
# child markers would make the demo write into that run's files.
unset _DROID_REVIEW_CHILD _DROID_REVIEW_STAMP _DROID_REVIEW_CATALOG

here="$(cd "$(dirname "$0")" && pwd)"
r="$(cd "$here/../../.." && pwd)"
models="${1:-glm,gemini}"
delay="${2:-3}"
REAL_DROID="$(command -v droid)" || { echo "needs the real droid on PATH (for its model list)" >&2; exit 2; }
export REAL_DROID

bin="$(mktemp -d)"
out="$bin/out"
root="$(git rev-parse --show-toplevel)"
# Remove the stub reviews' files, also when the demo is interrupted.
cleanup() {
  if [ -f "$out" ]; then
    while IFS=$'\t' read -r _ _ path _; do
      [ -n "$path" ] && [ "$path" != "-" ] || continue
      base="$root/${path%.*}"
      rm -f "$base.md" "$base.log" "$base.json"
    done < <(grep $'\t' "$out" || true)
    index="$(tail -1 "$out")"
    case "$index" in *-multi.md) rm -f "$root/$index" ;; esac
  fi
  rm -rf "$bin"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
ln -sf "$here/stub-droid" "$bin/droid"

echo "stub reviews on $models, ${delay}s per event; watch the band above the prompt in your Claude Code session" >&2
PATH="$bin:$PATH" STUB_DROID_DELAY="$delay" STUB_DROID_TURNS=8 \
  "$r/skills/droid-review/droid-review.sh" --models "$models" "band demo" > "$out" || true

echo "finished; the rows stay while this waits a minute, then it removes the stub files" >&2
sleep 61
echo "done" >&2
