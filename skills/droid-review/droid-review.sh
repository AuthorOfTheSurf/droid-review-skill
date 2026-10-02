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
#   droid-review.sh luna                  # a shortcut: gpt-6-luna at reasoning max
#   droid-review.sh "gemini the auth changes"   # shortcut, then the emphasis
#   droid-review.sh "luna xhigh"          # shortcut with its effort overridden
#   droid-review.sh --model glm-5.2 --effort max
#   droid-review.sh --models              # list the shortcuts and exit
#   droid-review.sh --efforts [model]     # every model's effort levels and default, or one's
#   droid-review.sh --models gemini,luna,grok "<ask>"   # the same ask on each, in parallel
#   droid-review.sh "gemini,luna the auth changes"      # same fan-out, as the first word
#   droid-review.sh --checks docs/testing.md   # inline a file listing how to verify this repo
#   droid-review.sh --session <id> "re-check the fixes in HEAD"
#   droid-review.sh --session last        # the newest review's session, by file
#
# A continuation runs on the model and effort that wrote the review, read from
# the review file's header, so the reviewer that raised a finding is the one
# that grades the fix. Name a model (shortcut, --model, first word) to override.
#
# The positional argument is what you are asking droid for this time: emphasis
# on top of /review, the whole ask under --feedback, or the re-check
# instruction with --session. Its first word picks the model when it is exactly
# a shortcut (--models) or a droid model id, and the word after that sets the
# reasoning effort when it is exactly an effort level. --model wins over both.
# Without a model the default is glm. Efforts are checked against the levels
# each model supports before droid runs; --efforts lists them.
#
# Env overrides: DROID_REVIEW_BASE, DROID_REVIEW_MODEL, DROID_REVIEW_EFFORT
# (the effort applies only when the model has no pinned level).
#
# Needs: droid (https://docs.factory.ai/droid-cli/quickstart), git, python3.
#
# Prints two lines on stdout: the review file path and the droid session id.
# Exit 0 when droid finished; non-zero when it did not (auth, model, timeout).
# The review lands in .droid-reviews/ (gitignore that) as markdown, next to a
# .log of the same name that droid's progress streams into while it runs
# (one line per tool call: elapsed, turn, tool and target) — tail it to watch.
#
# Fan-out: --models a,b,c (or a comma list as the ask's first word) runs one
# child of this script per model, in parallel, each with that model's shortcut
# effort (--effort applies to all). --models alone lists the shortcuts, as
# before. --session and --model take one model, so they do not combine with it.
# stderr shows a status board: redrawn in place on a terminal, else one line
# per state change (started, a new turn at most every 30s, finished/failed).
# stdout gets one "model<TAB>status<TAB>path<TAB>session" line per model
# (status ok, failed or interrupted; path is the result, or the .log when there
# is none), then last the index file .droid-reviews/<stamp>-<branch>-multi.md
# tabling every run. Exit 0 when at least one model succeeded. Ctrl-C stops the
# runs still going and keeps the finished ones.
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

# The whole script is one { ... } block ending in exit: bash reads a script as it
# runs it, so without this an edit to the file (a git pull, a shortcut moved)
# lands in runs already in flight, mid-line.
{

usage() { sed -n '2,/^set -/p' "$0" | sed -n 's/^# \{0,1\}//p'; }
die()   { echo "$*" >&2; exit 2; }
need()  { [ $# -ge 2 ] || die "$1 needs a value (--help for usage)"; }

ORIG_PWD="$PWD"
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"   # fan-out children re-run it
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || true

# Shortcuts: name → "model [effort]". A pinned effort is the level that model
# should review at; without one, droid's per-model default applies. The family
# names (fable, opus, astra, sol, grok, qwen, kimi, deepseek) point at the newest
# model in the family as of droid 0.232.0 — move them when droid ships a newer one.
SHORTCUTS="glm gemini luna auto fable opus astra sol grok qwen kimi deepseek"
shortcut() {
  case "$1" in
    glm)    echo "glm-5.3-flash high" ;;
    gemini) echo "gemini-3.8-flash high" ;;
    luna)   echo "gpt-6-luna max" ;;
    auto)   echo "auto" ;;
    fable)  echo "claude-fable-5.1" ;;
    opus)   echo "claude-opus-5-5" ;;
    astra)  echo "gpt-6-astra" ;;
    sol)    echo "gpt-6.1-sol" ;;
    grok)   echo "grok-4.7" ;;
    qwen)   echo "qwen3.8-max" ;;
    kimi)   echo "kimi-k3" ;;
    deepseek) echo "deepseek-v4.1-flash" ;;
    *) return 1 ;;
  esac
}
is_effort() {
  case "$1" in off|none|minimal|low|medium|high|xhigh|max) return 0 ;; esac
  return 1
}

# droid's model catalog: one "<id> <efforts> <default>" line per model, efforts
# comma-separated, "-" for no reasoning setting and "?" when droid gives no
# details (default "-" when unknown). The ids are the ones `droid exec` accepts,
# which it lists when handed an unknown one. Efforts come from `droid exec
# --help`, which lags behind that list (new models missing, retired ones kept),
# and for a model it leaves out, from the model registry built into the droid
# binary — the same table its /model picker reads, which agrees with the help
# wherever both list a model. Empty if every format changed, in which case
# nothing is validated and droid gets the last word.
catalog() {
  HELP="$(droid exec --help 2>/dev/null || true)" \
  ACCEPTED="$(droid exec -m droid-review-no-such-model --list-tools 2>&1 >/dev/null || true)" \
  python3 -c '
import mmap, os, re, shutil
section, ids, details = None, [], {}
for line in os.environ["HELP"].splitlines():
    if line and not line[0].isspace():
        section = line.strip()
        continue
    if section in ("Available Models:", "Custom Models:"):
        m = re.match(r"\s+(\S+)\s{2,}(.+)$", line)
        if m:
            ids.append((m.group(1), re.sub(r" \(default\)$", "", m.group(2).strip())))
    elif section == "Model details:":
        m = re.match(r"\s+- (.+): supports reasoning: (\w+); supported: \[([^\]]*)\]; default: (\w+)", line)
        if m:
            efforts = m.group(3).replace(" ", "") if m.group(2) == "Yes" else "-"
            details[m.group(1)] = (efforts, m.group(4) if m.group(2) == "Yes" else "-")
efforts = {model_id: details[name] for model_id, name in ids if name in details}
# The registry in the binary: {id:"<id>",name:...,reasoningEffort:{supported:[...],default:"..."}.
# An id may be a constant (Mn.GPT_6_SOL), defined elsewhere as o.GPT_6_SOL="gpt-6-sol".
built = {}
try:
    with open(os.path.realpath(shutil.which("droid")), "rb") as f:
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    consts = dict(re.findall(rb"o\.([A-Z0-9_]+)=\"([^\"]+)\"", buf))
    for m in re.finditer(rb"\{id:(?:\"([^\"]+)\"|[\w$]+\.([A-Z0-9_]+)),name:\"[^\"]*\"[^\x00]{0,3000}?reasoningEffort:\{supported:\[([^\]]*)\],default:\"([^\"]*)\"", buf):
        if b"{id:" in m.group(0)[4:]:
            continue   # ran into the next model: this one sets no effort
        model_id = (m.group(1) or consts.get(m.group(2), m.group(2))).decode()
        levels = [v.strip(b"\" ").decode() for v in m.group(3).split(b",") if v.strip()]
        levels = ",".join(levels) if levels and levels != ["none"] else "-"
        built.setdefault(model_id, (levels, m.group(4).decode() if levels != "-" else "-"))
except (OSError, TypeError, ValueError):
    pass
accepted, listing = [], False
for line in os.environ["ACCEPTED"].splitlines():
    if re.match(r"Available (built-in|custom) models:$", line):
        listing = True
    elif listing and line.strip():
        for entry in line.split(","):
            model_id = entry.split()[0] if entry.split() else ""
            if model_id and model_id not in accepted:
                accepted.append(model_id)
        listing = False
for model_id in accepted or [model_id for model_id, _ in ids]:
    print(model_id, *efforts.get(model_id) or built.get(model_id) or ("?", "-"))
'
}

# The default branch, as a ref that actually resolves here: origin/HEAD when
# the clone knows it, else the first of origin/main, origin/master, main,
# master that exists. Keep the remote form — a worktree or CI checkout may
# have no local branch of that name, and a stale local one diffs against old
# commits. DROID_REVIEW_BASE or --base overrides.
default_base() {
  local ref
  if ref="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null)"; then
    echo "$ref"; return
  fi
  for ref in origin/main origin/master main master; do
    git rev-parse --verify -q "$ref" >/dev/null && { echo "$ref"; return; }
  done
  echo "main"
}

MODE="review"
BASE="${DROID_REVIEW_BASE:-}"
MODEL="${DROID_REVIEW_MODEL:-}"
NAMED_MODEL=""   # set when the caller named one; a continuation then keeps it
EFFORT=""
SCOPE="branch"
CHECKS=""
SESSION=""
MODELS=""        # comma list: fan out, one child run per model
EFFORTS=""       # --efforts: list levels instead of running ("all" or a model)
ASK=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)    need "$@"; BASE="$2";    shift 2 ;;
    --model)   need "$@"; MODEL="$2"; NAMED_MODEL=1; shift 2 ;;
    --effort)  need "$@"; EFFORT="$2";  shift 2 ;;
    --checks)  need "$@"; CHECKS="$2";  shift 2 ;;
    --session) need "$@"; SESSION="$2"; shift 2 ;;
    --feedback) MODE="feedback";        shift ;;
    --uncommitted) SCOPE="uncommitted"; shift ;;
    --models)
      # A value that looks like a model list fans out; alone, before another
      # flag, or before a sentence, it lists the shortcuts as it always did.
      case "${2:-}" in
        ""|-*|*[[:space:]]*) ;;
        *) MODELS="$2"; shift 2; continue ;;
      esac
      for s in $SHORTCUTS; do
        set -- $(shortcut "$s")
        printf '%-9s %-18s %s\n' "$s" "$1" "${2:-droid default}"
      done
      exit 0 ;;
    --efforts)
      case "${2:-}" in ""|-*) EFFORTS="all"; shift ;; *) EFFORTS="$2"; shift 2 ;; esac ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $1 (--help for usage)" ;;
    *) ASK="${ASK:+$ASK }$1"; shift ;;
  esac
done

# --efforts answers "what levels does this model take" without a git repo or a
# run: id, droid's default, every supported level, and the shortcuts naming it.
if [ -n "$EFFORTS" ]; then
  command -v droid >/dev/null || die "droid CLI not installed"
  rows="$(catalog || true)"
  [ -n "$rows" ] || die "could not read droid's model list"
  want="$EFFORTS"; spec="$(shortcut "$want" || true)"; [ -z "$spec" ] || want="${spec%% *}"
  found=""
  while read -r id levels def; do
    [ "$want" = all ] || [ "$id" = "$want" ] || continue
    names=""
    for s in $SHORTCUTS; do spec="$(shortcut "$s")"; [ "${spec%% *}" = "$id" ] && names="${names:+$names,}$s${spec#"$id"}"; done
    case "$levels" in -) levels="(no reasoning setting)" ;; \?) levels="(droid gives none)" ;; esac
    found+="$(printf '%-30s %-8s %-38s %s' "$id" "$def" "$levels" "$names")"$'\n'
  done <<<"$rows"
  [ -n "$found" ] || die "droid has no model '$EFFORTS' (shortcuts: $SHORTCUTS)"
  printf '%-30s %-8s %-38s %s\n' model default supported shortcut
  printf '%s' "$found"
  exit 0
fi

[ -n "$ROOT" ] || die "not a git repository: $ORIG_PWD"
cd "$ROOT"
[ -n "$BASE" ] || BASE="$(default_base)"

command -v droid >/dev/null || \
  die "droid CLI not installed: https://docs.factory.ai/droid-cli/quickstart"
command -v python3 >/dev/null || die "python3 not found (used to parse droid's JSON)"

# A fan-out child is handed the parent's catalog rather than asking droid again.
CATALOG="${_DROID_REVIEW_CATALOG:-}"
[ -n "$CATALOG" ] || CATALOG="$(catalog || true)"
[ -n "$CATALOG" ] || echo "could not read droid's model list; skipping model checks" >&2
catalog_entry() { printf '%s\n' "$CATALOG" | awk -v m="$1" '$1 == m { print $2; exit }'; }

# The ask's first word picks the model when it is exactly a shortcut or a model
# id, and the next word the effort when it is exactly an effort level. The rest
# of the ask is left as typed, newlines included.
drop_word() { ASK="${ASK#"$1"}"; ASK="${ASK#"${ASK%%[![:space:]]*}"}"; }
is_model() { shortcut "$1" >/dev/null || [ -n "$(catalog_entry "$1")" ]; }
# A comma list of models as the first word is a fan-out, like --models.
is_model_list() {
  local m
  case "$1" in *,*) ;; *) return 1 ;; esac
  for m in ${1//,/ }; do is_model "$m" || return 1; done
}
WORD_EFFORT=""
if [ -z "$MODELS" ] && [ -z "$NAMED_MODEL" ] && [ -n "$ASK" ] && is_model_list "${ASK%%[[:space:]]*}"; then
  MODELS="${ASK%%[[:space:]]*}"; drop_word "$MODELS"
fi
if [ -n "$MODELS" ]; then
  [ -z "$NAMED_MODEL" ] || die "--model names one model; list them all in --models instead"
  [ -z "$SESSION" ] || die "--session continues one model's session; run it without --models"
  # Children get --model, so a model word left in the ask would reach droid as text.
  word="${ASK%%[[:space:]]*}"
  if [ -n "$word" ] && is_model "$word"; then
    die "'$word' is a model; name the models in --models only (effort: --effort)"
  fi
  for m in ${MODELS//,/ }; do
    shortcut "$m" >/dev/null || [ -z "$CATALOG" ] || [ -n "$(catalog_entry "$m")" ] || \
      die "droid has no model '$m' (shortcuts: $SHORTCUTS; every id: droid exec -m x --list-tools)"
  done
elif [ -z "$MODEL" ] && [ -n "$ASK" ]; then
  word="${ASK%%[[:space:]]*}"
  if is_model "$word"; then
    MODEL="$word"; NAMED_MODEL=1; drop_word "$word"
    word="${ASK%%[[:space:]]*}"
    if [ -n "$word" ] && is_effort "$word"; then WORD_EFFORT="$word"; drop_word "$word"; fi
  fi
fi

# A continuation keeps the reviewer that wrote the review: every review file's
# header records the model and effort beside the session id. `last` is the
# newest file; an id is looked up across the files. A model the caller named
# wins; a session no file records runs on the default and says so.
SESSION_EFFORT=""
if [ -n "$SESSION" ]; then
  if [ "$SESSION" = "last" ]; then
    # Skip fan-out indexes: they table several sessions and record none.
    SESSION_FILE="$(ls -t .droid-reviews/*.md 2>/dev/null | grep -v -- '-multi\.md$' | head -1 || true)"  # pipefail
    [ -n "$SESSION_FILE" ] || die "no review under .droid-reviews/ to continue"
    SESSION="$(sed -n 's/^- session: //p' "$SESSION_FILE" | head -1)"
    [ -n "$SESSION" ] || die "$SESSION_FILE has no session id"
  else
    SESSION_FILE="$(grep -lx -- "- session: $SESSION" $(ls -t .droid-reviews/*.md 2>/dev/null) 2>/dev/null | head -1 || true)"
  fi
  if [ -n "$SESSION_FILE" ]; then
    echo "continuing $SESSION_FILE ($SESSION)" >&2
    if [ -z "$NAMED_MODEL" ]; then
      header="$(sed -n 's/^- model: //p' "$SESSION_FILE" | head -1)"  # "<id> (reasoning <level|droid default>)"
      [ -n "$header" ] || die "$SESSION_FILE has no model line; name one (--model)"
      MODEL="${header%% *}"
      level="${header#*(reasoning }"; level="${level%)}"
      [ "$level" = "droid default" ] || SESSION_EFFORT="$level"
    fi
  else
    echo "no review under .droid-reviews/ records session $SESSION; running on ${MODEL:-glm}" >&2
  fi
fi

# Effort, most specific first: --effort, the word after the model, the session's
# level, the shortcut's pinned level, DROID_REVIEW_EFFORT, then droid's per-model
# default.
# A fan-out leaves all of this to its children, one model each.
PINNED=""
if [ -z "$MODELS" ] && spec="$(shortcut "${MODEL:-glm}")"; then
  MODEL="${spec%% *}"
  [ "$spec" = "$MODEL" ] || PINNED="${spec#* }"
fi
[ -n "$MODELS" ] || EFFORT="${EFFORT:-${WORD_EFFORT:-${SESSION_EFFORT:-${PINNED:-${DROID_REVIEW_EFFORT:-}}}}}"

if [ -n "$CATALOG" ] && [ -z "$MODELS" ]; then
  supported="$(catalog_entry "$MODEL")"
  [ -n "$supported" ] || \
    die "droid has no model '$MODEL' (shortcuts: $SHORTCUTS; every id: droid exec -m x --list-tools)"
  if [ -n "$EFFORT" ]; then
    case "$supported" in
      -) die "$MODEL has no reasoning effort setting; drop '$EFFORT'" ;;
      \?) ;;
      *) case ",$supported," in
           *",$EFFORT,"*) ;;
           *) die "$MODEL takes reasoning effort $supported, not '$EFFORT'" ;;
         esac ;;
    esac
  fi
fi

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

OUT_DIR=".droid-reviews"
mkdir -p "$OUT_DIR"
STAMP="${_DROID_REVIEW_STAMP:-$(date +%Y%m%d-%H%M%S)}"   # a fan-out shares one stamp
BRANCH="$(git branch --show-current | tr '/' '-')"
# The model is in the name so parallel runs on different models are told apart at a
# glance; the file itself is claimed just before writing (see claim_out below).
MODEL_TAG="$(printf '%s' "${MODEL:-glm}" | tr -c 'A-Za-z0-9.-' '-')"
OUT_BASE="$OUT_DIR/${STAMP}-${BRANCH:-detached}-${MODEL_TAG}"
OUT="$OUT_BASE.md"

# Claim OUT atomically (noclobber), adding -2, -3 ... if a run that started the same
# second with the same model already took it. Without this, parallel runs overwrote
# each other's reviews.
claim_out() {
  local n=2
  while ! ( set -C; : > "$OUT" ) 2>/dev/null; do
    OUT="$OUT_BASE-$n.md"
    n=$((n + 1))
  done
}

if [ "$SCOPE" = "uncommitted" ]; then
  WHAT="the uncommitted changes in the working tree"
  WHAT+=" (\`git diff\` and \`git diff --cached\`, plus untracked files)"
else
  git rev-parse --verify -q "$BASE" >/dev/null || die "base ref '$BASE' does not exist"
  WHAT="this branch against $BASE: \`git diff $BASE...HEAD\` plus any uncommitted changes"
fi

# Claim the live log the same way, at start. A suffix it needs moves OUT_BASE
# with it, so the review and its log keep one name.
claim_log() {
  local n=2 base="$OUT_BASE"
  LOG="$OUT_BASE.log"
  while ! ( set -C; : > "$LOG" ) 2>/dev/null; do
    OUT_BASE="$base-$n"; LOG="$OUT_BASE.log"
    n=$((n + 1))
  done
  OUT="$OUT_BASE.md"
}

# ---- Fan-out -----------------------------------------------------------------
# One child run of this script per model, in parallel, so scope, prompt, file
# naming and the result writer are the single-model path's, unchanged. Children
# run a frozen copy of the script: bash reads a script as it goes, so an edit to
# it during a long run would otherwise reach runs already in flight. Each child
# reports its log path through a file, its result on stdout, its error on
# stderr, and its exit status in <i>.rc; the parent only watches and tables.
elapsed() { printf '%dm%02ds' $(($1 / 60)) $(($1 % 60)); }
words() {  # "3.7k words" in the body, below the header's "- turns:" line
  local n; n="$(sed '1,/^- turns:/d' "$1" | wc -w | tr -d ' ')"
  if [ "$n" -ge 1000 ]; then
    printf '%d.%dk words' $((n / 1000)) $((n % 1000 / 100))
  else
    printf '%d words' "$n"
  fi
}
# bash 3.2 has no `kill -- -pgid` worth relying on here (background jobs share
# our process group), so walk the tree: droid is the child's grandchild.
kill_tree() {
  local c
  for c in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$c"; done
  kill -TERM "$1" 2>/dev/null || true
}

fan_out() {
  local i m n now line turn board="" cols=100 rc mark t
  tmpd="$(mktemp -d)"   # global: the EXIT trap outlives this function
  trap 'rm -rf "$tmpd"' EXIT
  cp "$SELF" "$tmpd/droid-review.sh"
  [ -t 2 ] && board=1 && cols="$(tput cols 2>/dev/null || echo 100)"

  # What every child gets besides its --model. --base is always set by now,
  # which also keeps this array non-empty (bash 3.2 + set -u).
  local args=(--base "$BASE")
  [ "$MODE" = "feedback" ] && args+=(--feedback)
  [ "$SCOPE" = "uncommitted" ] && args+=(--uncommitted)
  [ -n "$EFFORT" ] && args+=(--effort "$EFFORT")
  [ -n "$CHECKS" ] && args+=(--checks "$CHECKS")
  [ -n "$ASK" ] && args+=("$ASK")

  # Per-model state, in parallel indexed arrays (bash 3.2: no associative ones).
  NAMES=() STATE=() LOGS=() RESULT=() SESS=() DUR=() INFO=() TURN=() NOTED=()
  n=0
  for m in ${MODELS//,/ }; do
    NAMES[n]="$m"; STATE[n]="run"; LOGS[n]=""; RESULT[n]=""; SESS[n]=""
    DUR[n]=0; INFO[n]="starting"; TURN[n]=0; NOTED[n]=-999
    (
      rc=0
      _DROID_REVIEW_CHILD="$tmpd/$n.log" _DROID_REVIEW_STAMP="$STAMP" \
        _DROID_REVIEW_CATALOG="$CATALOG" \
        bash "$tmpd/droid-review.sh" "${args[@]}" --model "$m" \
        > "$tmpd/$n.out" 2> "$tmpd/$n.err" || rc=$?
      echo "$rc" > "$tmpd/$n.rc.tmp" && mv "$tmpd/$n.rc.tmp" "$tmpd/$n.rc"
    ) &
    PIDS[n]=$!
    n=$((n + 1))
  done

  interrupted=""        # global, set from the trap
  trap 'interrupted=1' INT TERM
  local t0=$SECONDS drawn=""
  say() { [ -n "$board" ] || printf '%-9s %s\n' "${NAMES[$1]}" "$2" >&2; }
  while :; do
    now=$((SECONDS - t0))
    local running=0
    for ((i = 0; i < n; i++)); do
      [ "${STATE[i]}" = "run" ] || continue
      if [ -z "${LOGS[i]}" ] && [ -s "$tmpd/$i.log" ]; then
        LOGS[i]="$(cat "$tmpd/$i.log")"
        say "$i" "started  log ${LOGS[i]}"
      fi
      if [ -f "$tmpd/$i.rc" ]; then
        rc="$(cat "$tmpd/$i.rc")"; DUR[i]=$now
        if [ "$rc" = 0 ]; then
          STATE[i]="ok"
          RESULT[i]="$(sed -n 1p "$tmpd/$i.out")"; SESS[i]="$(sed -n 2p "$tmpd/$i.out")"
          INFO[i]="$(words "${RESULT[i]}")"
          say "$i" "ok  $(elapsed "$now")  ${INFO[i]}  ${RESULT[i]}"
        else
          STATE[i]="failed"
          INFO[i]="$(grep -v '^[[:space:]]*$' "$tmpd/$i.err" | tail -1 | cut -c1-300 || true)"
          [ -n "${INFO[i]}" ] || INFO[i]="exit $rc"
          say "$i" "FAILED  $(elapsed "$now")  ${INFO[i]}"
        fi
        continue
      fi
      running=1
      # Progress is the log's last line: "[1m05s] turn 3 · Read calc.py".
      if [ -n "${LOGS[i]}" ] && line="$(tail -n 1 "${LOGS[i]}" 2>/dev/null)" && [ -n "$line" ]; then
        INFO[i]="${line#\[*\] }"
        case "${INFO[i]}" in "started "*) INFO[i]="started" ;; esac
        turn="$(printf '%s' "$line" | sed -n 's/^\[[^]]*\] turn \([0-9]*\) .*/\1/p')"
        # Without a board, a new turn is worth a line at most every 30s.
        if [ -n "$turn" ] && [ "$turn" -gt "${TURN[i]}" ]; then
          TURN[i]=$turn
          if [ $((now - NOTED[i])) -ge 30 ]; then
            NOTED[i]=$now; say "$i" "$(elapsed "$now")  ${INFO[i]}"
          fi
        fi
      fi
    done
    if [ -n "$board" ]; then
      [ -z "$drawn" ] || printf '\033[%dA' "$n" >&2
      drawn=1
      for ((i = 0; i < n; i++)); do
        case "${STATE[i]}" in
          ok) mark="✓"; t="${DUR[i]}" ;; failed|interrupted) mark="✗"; t="${DUR[i]}" ;;
          *) mark="…"; t=$now ;;
        esac
        line="$(printf '%-9s %s %6s  %s' "${NAMES[i]}" "$mark" "$(elapsed "$t")" "${INFO[i]}")"
        printf '\r\033[K%s\n' "${line:0:$((cols - 1))}" >&2
      done
    fi
    [ "$running" = 1 ] || break
    if [ -n "$interrupted" ]; then
      for ((i = 0; i < n; i++)); do
        [ "${STATE[i]}" = "run" ] || continue
        disown "${PIDS[i]}" 2>/dev/null || true   # no "Terminated" job notice
        kill_tree "${PIDS[i]}"
        STATE[i]="interrupted"; INFO[i]="interrupted"; DUR[i]=$now
        [ -z "${LOGS[i]}" ] || echo "[$(elapsed "$now")] interrupted" >> "${LOGS[i]}"
        say "$i" "interrupted  $(elapsed "$now")"
      done
      break
    fi
    sleep 1
  done
  trap - INT TERM

  # The index: one row per model, and the machine-readable lines on stdout.
  local index="$OUT_DIR/${STAMP}-${BRANCH:-detached}-multi.md" base="$OUT_DIR/${STAMP}-${BRANCH:-detached}-multi"
  local k=2
  while ! ( set -C; : > "$index" ) 2>/dev/null; do index="$base-$k.md"; k=$((k + 1)); done
  local ok=0 path cell
  {
    echo "# droid $([ "$MODE" = feedback ] && echo feedback || echo review), ${n} models"
    echo
    echo "- when: $(date +%Y-%m-%dT%H:%M:%S)"
    echo "- scope: $WHAT"
    [ -z "$ASK" ] || echo "- asked: $ASK"
    [ -z "$EFFORT" ] || echo "- effort: $EFFORT"
    echo
    echo "| model | status | time | words | session | result |"
    echo "|---|---|---|---|---|---|"
  } > "$index"
  for ((i = 0; i < n; i++)); do
    # A run that did not finish still has a session worth continuing.
    [ -n "${SESS[i]}" ] || [ -z "${LOGS[i]}" ] || \
      SESS[i]="$(sed -n 's/^\[[^]]*\] started .* session \([^ ]*\)$/\1/p' "${LOGS[i]}" | head -1)"
    path="${RESULT[i]:-${LOGS[i]:--}}"
    if [ "${STATE[i]}" = "ok" ]; then
      ok=$((ok + 1)); cell="${INFO[i]% words}"
      printf '| %s | ok | %s | %s | %s | %s |\n' "${NAMES[i]}" "$(elapsed "${DUR[i]}")" \
        "$cell" "${SESS[i]:--}" "$path" >> "$index"
    else
      cell="$(printf '%s' "${INFO[i]}" | sed 's/|/\\|/g')"
      [ "$cell" = "${STATE[i]}" ] || cell="${STATE[i]}: $cell"
      printf '| %s | %s | %s | - | %s | %s |\n' "${NAMES[i]}" "$cell" \
        "$(elapsed "${DUR[i]}")" "${SESS[i]:--}" "$path" >> "$index"
      if [ "${STATE[i]}" = "${INFO[i]}" ]; then echo "${NAMES[i]} ${STATE[i]}" >&2
      else echo "${NAMES[i]} ${STATE[i]}: ${INFO[i]}" >&2; fi
    fi
    printf '%s\t%s\t%s\t%s\n' "${NAMES[i]}" "${STATE[i]}" "$path" "${SESS[i]:--}"
  done
  echo "$index"
  [ -z "$interrupted" ] || exit 130
  [ "$ok" -gt 0 ] || exit 1
  exit 0
}

[ -z "$MODELS" ] || fan_out

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
#
# `-o stream-json` emits one event per line as droid works (init, tool_call,
# tool_result, message, error, completion); progress_filter below turns those
# into the live log and leaves the final result where `-o json` would have.
DROID_ARGS=(
  exec -o stream-json -m "$MODEL"
  --auto medium --remove-tools ApplyPatch
  --tag claude-triage
)
[ -n "$EFFORT" ] && DROID_ARGS+=(-r "$EFFORT")
[ -n "$SESSION" ] && DROID_ARGS+=(-s "$SESSION")

# Reads droid's event stream on stdin. Writes a line per event worth watching
# to the log ($1) — "[1m05s] turn 3 · Read src/app.ts" — and at the end one
# `-o json`-shaped line (result, is_error, session_id, num_turns, duration_ms)
# to $2 for the writer below. A turn is one assistant message that called tools.
# Output that is not an event (droid's own errors) is passed through as is.
progress_filter() {
  python3 -u -c '
import json, os, sys, time
log, out, model, effort = sys.argv[1:5]
t0, turn, last_msg, raw = time.time(), 0, None, []
done = err = None
session = ""
def note(text):
    s = int(time.time() - t0)
    with open(log, "a", encoding="utf-8") as f:
        f.write("[%dm%02ds] %s\n" % (s // 60, s % 60, text))
def target(p):
    keys = ("file_path", "path", "pattern", "patterns", "command", "url", "query", "description", "prompt")
    for key in keys + tuple(k for k in p if k not in keys):  # then any other argument
        v = p.get(key)
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            v = " ".join(v)
        if isinstance(v, str) and v:
            if key in ("file_path", "path") and v.startswith(os.getcwd() + "/"):
                v = v[len(os.getcwd()) + 1:]
            v = " ".join(v.split())
            return v if len(v) <= 70 else v[:67] + "..."
    return ""
for line in iter(sys.stdin.readline, ""):
    try:
        e = json.loads(line)
    except ValueError:
        if line.strip():
            raw.append(line)
            note(line.strip()[:200])
        continue
    kind = e.get("type")
    if kind == "system" and e.get("subtype") == "init":
        session = e.get("session_id") or ""
        note("started %s (reasoning %s) session %s" % (e.get("model") or model, e.get("reasoning_effort") or effort or "droid default", session))
    elif kind == "tool_call":
        if e.get("messageId") != last_msg:
            turn, last_msg = turn + 1, e.get("messageId")
        name = e.get("toolName") or e.get("toolId") or "tool"
        tgt = target(e.get("parameters") or {})
        note("turn %d · %s%s" % (turn, name, " " + tgt if tgt else ""))
    elif kind == "error":
        err = e.get("message") or json.dumps(e)
        note("error: " + " ".join(str(err).split())[:300])
    elif kind == "completion":
        done = e
        note("done · %s turns · %ss" % (e.get("numTurns"), (e.get("durationMs") or 0) // 1000))
with open(out, "w") as f:
    if done is not None:
        f.write(json.dumps({"is_error": False, "result": done.get("finalText") or "",
                            "session_id": done.get("session_id") or session,
                            "num_turns": done.get("numTurns"),
                            "duration_ms": done.get("durationMs") or 0}) + "\n")
    elif err is not None:
        f.write(json.dumps({"is_error": True, "result": err, "session_id": session}) + "\n")
    else:
        f.write("".join(raw) or "(no output from droid)\n")
' "$@"
}

claim_log
if [ -n "${_DROID_REVIEW_CHILD:-}" ]; then
  printf '%s\n' "$LOG" > "$_DROID_REVIEW_CHILD"   # tells the fan-out parent
else
  echo "live log: $LOG" >&2
fi

set +e
droid "${DROID_ARGS[@]}" "$PROMPT" | progress_filter "$LOG" "$JSON" "$MODEL" "$EFFORT"
STATUS=${PIPESTATUS[0]}
set -e

claim_out
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
    f.write(f"- model: {model} (reasoning {effort or 'droid default'})\n")
    f.write(f"- scope: {what}\n")
    if ask:
        f.write(f"- asked: {ask}\n")
    f.write(f"- session: {d.get('session_id')}\n")
    f.write(f"- turns: {d.get('num_turns')}, {d.get('duration_ms', 0)//1000}s\n\n")
    f.write(body + "\n")
print(out)
print(d.get("session_id") or "")
PY
then rm -f "$OUT"; exit 1; fi

exit "$STATUS"
}
