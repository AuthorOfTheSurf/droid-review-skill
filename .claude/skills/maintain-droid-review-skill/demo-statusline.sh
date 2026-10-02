#!/usr/bin/env bash
# Watch the droid-review status line rows in a real Claude Code session
# without spending a model run: runs stub reviews in this repo (stub-droid,
# slowed down), so a session open here shows them under its status line.
# Deletes the stub reviews' files once their rows are gone, so they never count
# toward the time estimates or become what `--session last` continues.
#
#   .claude/skills/maintain-droid-review-skill/demo-statusline.sh [models] [seconds per event]
#   .claude/skills/maintain-droid-review-skill/demo-statusline.sh glm,gemini,luna 3
#
# Needs the status line set up (README: "Live status in Claude Code").
set -euo pipefail

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

echo "stub reviews on $models, ${delay}s per event; watch the status line in your Claude Code session" >&2
PATH="$bin:$PATH" STUB_DROID_DELAY="$delay" STUB_DROID_TURNS=8 \
  "$r/skills/droid-review/droid-review.sh" --models "$models" "status line demo" > "$out" || true

echo "finished; rows stay 30s, then this removes the stub files" >&2
sleep 31
echo "done" >&2
