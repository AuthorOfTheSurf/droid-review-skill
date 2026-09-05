#!/usr/bin/env bash
# Ask Factory's droid to review this branch, non-interactively, and save the
# review to a file Claude can triage. No copy-paste, no human in the loop.
#
#   droid-review.sh                  # branch vs the default branch (+ uncommitted)
#   droid-review.sh --base origin/main
#   droid-review.sh --uncommitted    # only the working tree
#   droid-review.sh --model glm-5.2 --effort max
#   droid-review.sh --session <id> "re-check the fixes in HEAD"
#   droid-review.sh --session last   # the newest review's session, by file
#   droid-review.sh --focus "the purchase chaining in PaywallView"
#   droid-review.sh --rubric copy.md --model gemini-3.8-flash   # not a code review
#
# Prints two lines on stdout: the review file path and the droid session id.
# Exit 0 when droid finished; non-zero when it did not (auth, model, timeout).
# The review lands in .droid-reviews/ (gitignored) as markdown.
#
# Portable: this file and SKILL.md are the whole thing. The repo-specific part —
# which checks the reviewer should run — is checks.md next to this script; drop
# it and the prompt falls back to "follow the project's instructions file".
# A rubric (--rubric, a file here or a path) replaces the code-review prompt
# with another kind of review; copy.md reviews the app's user-facing copy.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$(git rev-parse --show-toplevel)"

# The default branch: origin/HEAD when the clone knows it, else whichever of
# main/master exists. DROID_REVIEW_BASE or --base overrides.
default_base() {
  local ref
  if ref="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"; then
    echo "${ref#origin/}"; return
  fi
  for ref in main master; do
    git rev-parse --verify -q "$ref" >/dev/null && { echo "$ref"; return; }
  done
  echo "main"
}

BASE="${DROID_REVIEW_BASE:-$(default_base)}"
MODEL="${DROID_REVIEW_MODEL:-glm-5.3-flash}"
EFFORT="${DROID_REVIEW_EFFORT:-high}"
SCOPE="branch"
FOCUS=""
RUBRIC=""
SESSION=""
EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --effort) EFFORT="$2"; shift 2 ;;
    --uncommitted) SCOPE="uncommitted"; shift ;;
    --focus) FOCUS="$2"; shift 2 ;;
    --rubric) RUBRIC="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) EXTRA="$EXTRA $1"; shift ;;
  esac
done

command -v droid >/dev/null || {
  echo "droid CLI not installed: https://docs.factory.ai/droid-cli/quickstart" >&2
  exit 2
}

# `--session last`: the id is in the newest review file's header, so the
# review → triage → re-check loop survives a lost conversation context.
if [ "$SESSION" = "last" ]; then
  LAST="$(ls -t .droid-reviews/*.md 2>/dev/null | head -1 || true)"  # pipefail
  [ -n "$LAST" ] || { echo "no review under .droid-reviews/ to continue" >&2; exit 2; }
  SESSION="$(sed -n 's/^- session: //p' "$LAST" | head -1)"
  [ -n "$SESSION" ] || { echo "$LAST has no session id" >&2; exit 2; }
  echo "continuing $LAST ($SESSION)" >&2
fi

OUT_DIR=".droid-reviews"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BRANCH="$(git branch --show-current | tr '/' '-')"
OUT="$OUT_DIR/${STAMP}-${BRANCH:-detached}.md"

if [ "$SCOPE" = "uncommitted" ]; then
  WHAT="the uncommitted changes in the working tree"
  WHAT+=" (\`git diff\` and \`git diff --cached\`, plus untracked files)"
else
  if ! git rev-parse --verify -q "$BASE" >/dev/null; then
    echo "base ref '$BASE' does not exist" >&2; exit 2
  fi
  WHAT="this branch against $BASE: \`git diff $BASE...HEAD\` plus any uncommitted changes"
fi

# The prompt, one sentence per array element; joined with spaces below. Shell
# has no template strings, so an array + printf is the idiomatic join.
if [ -n "$SESSION" ]; then
  if [ -n "$EXTRA" ]; then
    PROMPT="${EXTRA# }"
  else
    LINES=(
      "Re-review the current state of $WHAT."
      "For each finding from your earlier review say whether it is now fixed,"
      "still open, or was a false positive, then list any new findings in the"
      "same format, and end with the same 'Checks run' list."
    )
    PROMPT="$(printf '%s ' "${LINES[@]}")"
  fi
elif [ -n "$RUBRIC" ]; then
  [ -f "$RUBRIC" ] || RUBRIC="$HERE/$RUBRIC"
  [ -f "$RUBRIC" ] || { echo "rubric '$RUBRIC' not found" >&2; exit 2; }
  LINES=(
    "The change under review is $WHAT."
    "$(cat "$RUBRIC")"
  )
  [ -n "$FOCUS" ] && LINES+=("Pay particular attention to: $FOCUS.")
  [ -n "$EXTRA" ] && LINES+=("${EXTRA# }")
  PROMPT="$(printf '%s\n' "${LINES[@]}")"
else
  LINES=(
    "/review Review $WHAT."
  )
  [ -n "$FOCUS" ] && LINES+=("Pay particular attention to: $FOCUS.")
  LINES+=(
    "Do not reason off the diff alone: this repo is built so an agent can verify"
    "claims cheaply. Run the checks that cover the changed files and cite them."
  )
  if [ -f "$HERE/checks.md" ]; then
    LINES+=("$(cat "$HERE/checks.md")")
  else
    LINES+=(
      "The project's instructions file (AGENTS.md / CLAUDE.md, loaded for you)"
      "names the test and verification commands; use those."
    )
  fi
  LINES+=(
    "Report every finding as a markdown bullet with: severity"
    "(critical/high/medium/low), file:line, what breaks and a concrete scenario"
    "that triggers it, and why you are confident — a check you ran beats a read."
    "Only report things you have verified, not style preferences."
    "Do not modify any tracked files or commit."
    "End with a short 'Checks run' list naming each command and its result."
    "If there are no findings, say exactly 'No findings.' before that list."
  )
  [ -n "$EXTRA" ] && LINES+=("${EXTRA# }")
  PROMPT="$(printf '%s\n' "${LINES[@]}")"
fi

JSON="$(mktemp)"
trap 'rm -f "$JSON"' EXIT

# `--auto medium` lets the reviewer build and run the test suites and the
# simulator scripts (read-only autonomy blocks xcodebuild); disabling Create
# and Edit keeps it a reviewer, not an author.
DROID_ARGS=(
  exec -o json -m "$MODEL" -r "$EFFORT"
  --auto medium --disabled-tools Create,Edit
  --tag claude-triage
)
[ -n "$SESSION" ] && DROID_ARGS+=(-s "$SESSION")

set +e
droid "${DROID_ARGS[@]}" "$PROMPT" > "$JSON"
STATUS=$?
set -e

if ! python3 - "$JSON" "$OUT" "$MODEL" "$EFFORT" "$WHAT" "$RUBRIC" <<'PY'
import json, sys, datetime
raw, out, model, effort, what, rubric = sys.argv[1:7]
text = open(raw).read().strip()
try:
    d = json.loads(text.splitlines()[-1])
except Exception:
    sys.stderr.write("droid did not return JSON:\n" + text[-2000:] + "\n")
    sys.exit(1)
if d.get("is_error"):
    sys.stderr.write("droid reported an error: " + str(d.get("result"))[:2000] + "\n")
    sys.exit(1)
body = (d.get("result") or "").strip()
with open(out, "w") as f:
    f.write("# droid review\n\n")
    f.write(f"- when: {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    f.write(f"- model: {model} (reasoning {effort})\n")
    f.write(f"- scope: {what}\n")
    if rubric:
        f.write(f"- rubric: {rubric}\n")
    f.write(f"- session: {d.get('session_id')}\n")
    f.write(f"- turns: {d.get('num_turns')}, {d.get('duration_ms', 0)//1000}s\n\n")
    f.write(body + "\n")
print(out)
print(d.get("session_id") or "")
PY
then exit 1; fi

exit "$STATUS"
