#!/usr/bin/env bash
# Ask Factory's droid for a second opinion on this branch, non-interactively,
# and save it as markdown your main coding agent can triage. No copy-paste
# between two chat windows.
#
#   droid-review.sh                       # droid's /review on this branch vs the default branch
#   droid-review.sh "the auth changes"    # same, with something to weight
#   droid-review.sh --feedback "<ask>"    # not /review: ask droid for anything, in its own words
#   droid-review.sh --base origin/main
#   droid-review.sh --uncommitted         # only the working tree
#   droid-review.sh --model glm-5.2 --effort max
#   droid-review.sh --checks docs/testing.md   # inline a file listing how to verify this repo
#   droid-review.sh --session <id> "re-check the fixes in HEAD"
#   droid-review.sh --session last        # the newest review's session, by file
#
# The positional argument is what you are asking droid for this time: emphasis
# on top of /review, the whole ask under --feedback, or the re-check
# instruction with --session.
#
# Env overrides: DROID_REVIEW_BASE, DROID_REVIEW_MODEL, DROID_REVIEW_EFFORT.
#
# Needs: droid (https://docs.factory.ai/droid-cli/quickstart), git, python3.
#
# Prints two lines on stdout: the review file path and the droid session id.
# Exit 0 when droid finished; non-zero when it did not (auth, model, timeout).
# The review lands in .droid-reviews/ (gitignore that) as markdown.
#
# droid runs here at `--auto medium`, so inside your repo it can build, run
# tests, install packages, make network requests and commit locally. That is
# the point — a finding backed by a command it ran beats one read off the diff.
# ApplyPatch is removed so it cannot edit your files.
#
# No config files. How to test and verify the repo is read from its instructions
# file (AGENTS.md / CLAUDE.md), which droid loads by itself; --checks <path>
# inlines a specific file instead, for a repo that keeps that list elsewhere.
set -euo pipefail

usage() { sed -n '2,/^set -/p' "$0" | sed -n 's/^# \{0,1\}//p'; }
die()   { echo "$*" >&2; exit 2; }
need()  { [ $# -ge 2 ] || die "$1 needs a value (--help for usage)"; }

ORIG_PWD="$PWD"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || true
[ -n "$ROOT" ] || die "not a git repository: $ORIG_PWD"

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

MODE="review"
BASE="${DROID_REVIEW_BASE:-}"
MODEL="${DROID_REVIEW_MODEL:-glm-5.3-flash}"
EFFORT="${DROID_REVIEW_EFFORT:-high}"
SCOPE="branch"
CHECKS=""
SESSION=""
ASK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)    need "$@"; BASE="$2";    shift 2 ;;
    --model)   need "$@"; MODEL="$2";   shift 2 ;;
    --effort)  need "$@"; EFFORT="$2";  shift 2 ;;
    --checks)  need "$@"; CHECKS="$2";  shift 2 ;;
    --session) need "$@"; SESSION="$2"; shift 2 ;;
    --feedback) MODE="feedback";        shift ;;
    --uncommitted) SCOPE="uncommitted"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $1 (--help for usage)" ;;
    *) ASK="${ASK:+$ASK }$1"; shift ;;
  esac
done

cd "$ROOT"
[ -n "$BASE" ] || BASE="$(default_base)"

command -v droid >/dev/null || \
  die "droid CLI not installed: https://docs.factory.ai/droid-cli/quickstart"
command -v python3 >/dev/null || die "python3 not found (used to parse droid's JSON)"

if [ "$MODE" = "feedback" ] && [ -z "$SESSION" ] && [ -z "$ASK" ]; then
  die "--feedback needs an ask: droid-feedback.sh \"<what you want droid to look at>\""
fi

# --checks takes a path as typed (relative to where you ran this, or the repo).
if [ -n "$CHECKS" ]; then
  if   [ -f "$CHECKS" ];           then :   # absolute, or relative to the repo root
  elif [ -f "$ORIG_PWD/$CHECKS" ]; then CHECKS="$ORIG_PWD/$CHECKS"
  else die "checks file '$CHECKS' not found"
  fi
fi

# `--session last`: the id is in the newest review file's header, so the
# review → triage → re-check loop survives a lost conversation context.
if [ "$SESSION" = "last" ]; then
  LAST="$(ls -t .droid-reviews/*.md 2>/dev/null | head -1 || true)"  # pipefail
  [ -n "$LAST" ] || die "no review under .droid-reviews/ to continue"
  SESSION="$(sed -n 's/^- session: //p' "$LAST" | head -1)"
  [ -n "$SESSION" ] || die "$LAST has no session id"
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
  git rev-parse --verify -q "$BASE" >/dev/null || die "base ref '$BASE' does not exist"
  WHAT="this branch against $BASE: \`git diff $BASE...HEAD\` plus any uncommitted changes"
fi

# How this repo proves things about itself. droid loads AGENTS.md / CLAUDE.md on
# its own, so the default is to point at it rather than keep a second copy of
# the same list in a file only this tool reads.
checks_block() {
  if [ -n "$CHECKS" ]; then
    cat "$CHECKS"
  else
    cat <<'TXT'
This repo's instructions file (AGENTS.md / CLAUDE.md, already loaded for you)
documents how it is tested and verified: read it for the commands, what each
one proves, and what it costs, and prefer the cheap ones. If it does not say,
fall back to README.md and the package manifest's scripts.
TXT
  fi
}

# The prompt, one sentence per array element; joined with newlines below. Shell
# has no template strings, so an array + printf is the idiomatic join.
if [ -n "$SESSION" ]; then
  if [ -n "$ASK" ]; then
    PROMPT="$ASK"
  else
    LINES=(
      "Re-review the current state of $WHAT."
      "For each finding or suggestion from your earlier review say whether it is"
      "now fixed, still open, or was a false positive, then list anything new in"
      "the same format, and end with the same 'Checks run' list."
    )
    PROMPT="$(printf '%s ' "${LINES[@]}")"
  fi
elif [ "$MODE" = "feedback" ]; then
  LINES=(
    "The change under review is $WHAT."
    "$ASK"
    "Do not reason off the diff alone: run the checks that bear on what you were"
    "asked, and cite them."
    "$(checks_block)"
    "Do not modify any tracked files or commit."
    "End with a short 'Checks run' list naming each command and its result, or 'none'."
  )
  PROMPT="$(printf '%s\n' "${LINES[@]}")"
else
  LINES=(
    "/review Review $WHAT."
  )
  [ -n "$ASK" ] && LINES+=("The user asked you to pay particular attention to: $ASK.")
  LINES+=(
    "Do not reason off the diff alone: run the checks that cover the changed"
    "files and cite them."
    "$(checks_block)"
    "Report every finding as a markdown bullet with: severity"
    "(critical/high/medium/low), file:line, what breaks and a concrete scenario"
    "that triggers it, and why you are confident — a check you ran beats a read."
    "Only report things you have verified, not style preferences."
    "Do not modify any tracked files or commit."
    "End with a short 'Checks run' list naming each command and its result."
    "If there are no findings, say exactly 'No findings.' before that list."
  )
  PROMPT="$(printf '%s\n' "${LINES[@]}")"
fi

JSON="$(mktemp)"
trap 'rm -f "$JSON"' EXIT

# `--auto medium` lets the reviewer build and run the test suites, which is the
# whole point; `--remove-tools ApplyPatch` drops the only file-editing tool, so
# it stays a reviewer and not an author. Check the pairing against your droid
# version with `droid exec --auto medium --remove-tools ApplyPatch --list-tools`
# — droid ignores unknown flags silently, so a rename here fails open.
DROID_ARGS=(
  exec -o json -m "$MODEL" -r "$EFFORT"
  --auto medium --remove-tools ApplyPatch
  --tag claude-triage
)
[ -n "$SESSION" ] && DROID_ARGS+=(-s "$SESSION")

set +e
droid "${DROID_ARGS[@]}" "$PROMPT" > "$JSON"
STATUS=$?
set -e

if ! python3 - "$JSON" "$OUT" "$MODEL" "$EFFORT" "$WHAT" "$MODE" "$ASK" <<'PY'
import json, sys, datetime
raw, out, model, effort, what, mode, ask = sys.argv[1:8]
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
    f.write("# droid %s\n\n" % ("feedback" if mode == "feedback" else "review"))
    f.write(f"- when: {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    f.write(f"- model: {model} (reasoning {effort})\n")
    f.write(f"- scope: {what}\n")
    if ask:
        f.write(f"- asked: {ask}\n")
    f.write(f"- session: {d.get('session_id')}\n")
    f.write(f"- turns: {d.get('num_turns')}, {d.get('duration_ms', 0)//1000}s\n\n")
    f.write(body + "\n")
print(out)
print(d.get("session_id") or "")
PY
then exit 1; fi

exit "$STATUS"
