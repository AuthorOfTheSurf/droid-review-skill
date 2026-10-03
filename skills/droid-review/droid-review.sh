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
#   droid-review.sh luna                  # a shortcut: gpt-6-luna at droid's default effort
#   droid-review.sh "gemini the auth changes"   # shortcut, then the emphasis
#   droid-review.sh "luna max"            # shortcut at an effort you name (higher is opt-in)
#   droid-review.sh --model glm-5.2 --effort max
#   droid-review.sh --models              # list the shortcuts and exit
#   droid-review.sh --efforts [model]     # every model's effort levels and default, or one's
#   droid-review.sh --whats-new           # models droid marks new, on sale or deprecated
#   droid-review.sh --models gemini,luna,grok "<ask>"   # the same ask on each, in parallel
#   droid-review.sh "gemini,luna the auth changes"      # same fan-out, as the first word
#   droid-review.sh --checks docs/testing.md   # inline a file listing how to verify this repo
#   droid-review.sh --session <id> "re-check the fixes in HEAD"
#   droid-review.sh --session last        # the newest review's session, by file
#   droid-review.sh --history [--all]     # this branch's reviews (--all: every branch), rounds and notes
#   droid-review.sh --note <review|session|last> "<what you did about it>"
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
# Env overrides: DROID_REVIEW_BASE, DROID_REVIEW_MODEL, DROID_REVIEW_EFFORT.
#
# Needs: droid (https://docs.factory.ai/droid-cli/quickstart), git, python3.
#
# Prints two lines on stdout: the review file path and the droid session id.
# Exit 0 when droid finished; non-zero when it did not (auth, model, timeout).
# The review lands in .droid-reviews/ (which ignores itself in git) as markdown,
# next to a .log of the same name that droid's progress streams into while it
# runs (one line per tool call: elapsed, turn, tool and target) — tail it to
# watch — and a .json of the run: status (running/ok/failed/interrupted), start
# and finish, the commit, branch and base it reviewed, and the uncommitted
# changes it saw. Compare those with the repo now to tell how fresh it is; the
# review file's header says the same in words.
#
# --history lists the reviews on this branch, newest first, each with its
# re-checks: when each round ran, how it ended, the commit it reviewed and how
# far HEAD has moved since. --note records one line on a finished review (the
# file, a session id for its newest round, or last): what the agent that
# triaged it did about it. It goes in the .json and under "## Response" in the
# review file, and --history shows it under its round.
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

# Shortcuts: name → model. None pins an effort: each runs at droid's per-model
# default (--efforts shows it), and a higher one is opt-in, named on the run
# ("luna max"), because a max-effort review can take half an hour. The family
# names (fable, opus, astra, sol, grok, qwen, kimi, deepseek) point at the newest
# model in the family as of droid 0.232.0 — move them when droid ships a newer one.
SHORTCUTS="glm gemini luna auto fable opus astra sol grok qwen kimi deepseek"
shortcut() {
  case "$1" in
    glm)    echo "glm-5.3-flash" ;;
    gemini) echo "gemini-3.8-flash" ;;
    luna)   echo "gpt-6-luna" ;;
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
WHATS_NEW=""     # --whats-new: new, discounted and deprecated models, then exit
ALL=""           # --all: --history on every branch
HISTORY=""       # --history: list this repo's reviews, then exit (--all: every branch)
NOTE=()          # --note <review> <text>: record what was done about a review
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
      for s in $SHORTCUTS; do printf '%-9s %s\n' "$s" "$(shortcut "$s")"; done
      exit 0 ;;
    --efforts)
      case "${2:-}" in ""|-*) EFFORTS="all"; shift ;; *) EFFORTS="$2"; shift 2 ;; esac ;;
    --whats-new) WHATS_NEW=1; shift ;;
    --history) HISTORY="history"; shift ;;
    --all)     ALL=1; shift ;;
    --note)
      [ $# -ge 3 ] || die "--note needs a review and a line: --note last \"fixed 2, rejected 1 as a false positive\""
      NOTE=("$2" "$3"); shift 3 ;;
    -h|--help) usage; exit 0 ;;
    -*) die "unknown option: $1 (--help for usage)" ;;
    *) ASK="${ASK:+$ASK }$1"; shift ;;
  esac
done

# --efforts and --whats-new answer "which model, at what level" without a git
# repo or a run. Both read what droid's /model picker shows beside each model
# from the registry in the droid binary (see catalog): the "new" badge (until a
# date), an active promotion (a discount off its token-price multiplier, until a
# date) and a deprecation with the model droid falls back to. These fields are
# droid internals, not an interface: a row it cannot read just shows less.
if [ -n "$EFFORTS" ] || [ -n "$WHATS_NEW" ]; then
  command -v droid >/dev/null || die "droid CLI not installed"
  CAT="$(catalog || true)"
  [ -n "$CAT" ] || die "could not read droid's model list"
  SC="$(for s in $SHORTCUTS; do echo "$s $(shortcut "$s")"; done)"
  want="$(shortcut "$EFFORTS" || echo "$EFFORTS")"
  CAT="$CAT" SC="$SC" DROID_VERSION="$(droid --version 2>/dev/null || true)" python3 -c '
import datetime as dt, mmap, os, re, shutil, sys
mode, want = sys.argv[1:3]
now = dt.datetime.now(dt.timezone.utc)
day = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
cat = [l.split() for l in os.environ["CAT"].splitlines() if l.strip()]
names = {}
for l in os.environ["SC"].splitlines():
    s, mid = l.split()
    names.setdefault(mid, []).append(s)
info, family = {}, {}
try:
    with open(os.path.realpath(shutil.which("droid")), "rb") as f:
        t = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # Match from the literal: a leading [\w$]+ makes the scan of the binary take seconds.
    promos = {}
    for m in re.finditer(rb"=\{discount:([\d.]+),startsAt:new Date\(\"([^\"]+)\"\),expiresAt:new Date\(\"([^\"]+)\"\),label:\"([^\"]*)\"\}", t):
        name = re.search(rb"([\w$]+)$", t[max(0, m.start() - 40):m.start()])
        if name:
            promos[name.group(1).decode()] = (float(m.group(1)), day(m.group(2).decode()), day(m.group(3).decode()), m.group(4).decode())
    # Keys are quoted ("gpt-6-sol":{id:...) or bare (inkling:{id:...).
    for m in re.finditer(rb":\{id:\"([\w.:-]+)\",name:", t):
        mid = m.group(1).decode()
        key = re.search(rb"[{,]\"?([\w.:-]+)\"?$", t[max(0, m.start() - 80):m.start()])
        if not key or key.group(1) != m.group(1) or mid in info:
            continue
        body = t[m.end():m.end() + 4000].decode("latin-1")
        nxt = re.search(r",\"?[\w.:-]+\"?:\{id:\"", body)
        body = body[:nxt.start()] if nxt else body
        g = lambda rx: (re.search(rx, body) or [None, None])[1]
        price = g(r"cost:\{tokenMultiplier:([\d.]+)")
        promo = None
        for ref in (g(r"promotions:\[([^\]]*)\]") or "").split(","):
            p = promos.get(ref.strip())
            if p and p[1] <= now < p[2]:
                promo = p
                break
        new = g(r"newUntil:new Date\(\"([^\"]+)\"\)")
        info[mid] = {
            "price": float(price) if price else None, "promo": promo,
            "new": new[:10] if new and now < day(new) else None,
            "dep": g(r"deprecation:\{date:\"([^\"]+)\""), "fallback": g(r"fallbackModelId:\"([^\"]+)\""),
        }
    # Families, newest generation first: {generations:[{id:"glm-5.3"},{id:"glm-5.2",variants:["glm-5.2-fast"]},...]}
    first = t.find(b"generations:[{id:")
    if first >= 0:
        for fam in re.findall(rb"generations:\[((?:\{[^{}]*\},?)+)\]", t[first:first + 30000]):
            gens = [(g.decode(), [v.decode() for v in re.findall(rb"\"([^\"]+)\"", vs)])
                    for g, vs in re.findall(rb"\{id:\"([^\"]+)\"(?:,variants:\[([^\]]*)\])?", fam)]
            for rank, (g, variants) in enumerate(gens):
                for mid in [g] + variants:
                    family.setdefault(mid, (rank, gens))
except (OSError, TypeError, ValueError):
    pass
fmt = lambda x: ("%g" % x) + "x"
def price(mid):
    i = info.get(mid) or {}
    if i.get("price") is None:
        return "-"
    return fmt(i["price"] * (1 - i["promo"][0])) if i.get("promo") else fmt(i["price"])
def notes(mid):
    i, out = info.get(mid) or {}, []
    if i.get("new"):
        out.append("new until " + i["new"])
    if i.get("promo"):
        d, _, end, label = i["promo"]
        out.append("%s until %s (was %s)" % (label, end.strftime("%Y-%m-%d"), fmt(i["price"])))
    if i.get("dep"):
        out.append("deprecated %s -> %s" % (i["dep"], i.get("fallback") or "no fallback declared"))
    return "; ".join(out)
sc = lambda mid: ",".join(names.get(mid, []))
if mode == "efforts":
    rows = [r for r in cat if want == "all" or r[0] == want]
    if not rows:
        sys.exit(1)
    print("%-28s %-8s %-38s %-12s %-7s %s" % ("model", "default", "supported", "shortcut", "price", "notes"))
    for mid, levels, default in rows:
        levels = {"-": "(no reasoning setting)", "?": "(droid gives none)"}.get(levels, levels)
        print(("%-28s %-8s %-38s %-12s %-7s %s" % (mid, default, levels, sc(mid), price(mid), notes(mid))).rstrip())
    sys.exit(0)
accepted = [r[0] for r in cat]
def section(title, pick, line):
    hits = [m for m in accepted if pick(info.get(m) or {})]
    print(title)
    for m in hits:
        print("  %-26s %-14s %s" % (m, sc(m) or "-", line(m, info[m])))
    if not hits:
        print("  (none)")
    print()
print("droid models as of %s UTC (droid %s), from the /model picker data\n" % (now.strftime("%Y-%m-%d %H:%M"), os.environ.get("DROID_VERSION", "?")))
section("NEW", lambda i: i.get("new"), lambda m, i: "new until " + i["new"])
section("ON SALE", lambda i: i.get("promo"), lambda m, i: "%s: %s -> %s until %s" % (
    i["promo"][3], fmt(i["price"]), price(m), i["promo"][2].strftime("%Y-%m-%d")))
section("DEPRECATED", lambda i: i.get("dep"), lambda m, i: "since %s -> %s" % (
    i["dep"], i.get("fallback") or "no fallback declared"))
print("SHORTCUTS against the model families droid lists (newest generation first)")
for l in os.environ["SC"].splitlines():
    s, mid = l.split()[:2]
    rank, gens = family.get(mid, (None, []))
    dep = (info.get(mid) or {}).get("dep")
    if rank is None:
        verdict = "(no family listed)"
    elif rank == 0:
        verdict = "newest in its family"
    else:
        verdict = "NEWER: " + ", ".join(g for g, _ in gens[:rank])
    if dep:
        verdict += "; DEPRECATED -> " + ((info.get(mid) or {}).get("fallback") or "no fallback declared")
    line = " > ".join(g for g, _ in gens[:4]) + (" > ..." if len(gens) > 4 else "")
    print("  %-9s %-22s %s" % (s, mid, verdict) + ("   [" + line + "]" if len(gens) > 1 else ""))
' "$([ -n "$WHATS_NEW" ] && echo new || echo efforts)" "${want:-all}" \
    || die "droid has no model '$EFFORTS' (shortcuts: $SHORTCUTS)"
  exit 0
fi

[ -n "$ROOT" ] || die "not a git repository: $ORIG_PWD"
cd "$ROOT"

# --history and --note read and write .droid-reviews/ only; no droid needed.
[ -z "$ALL" ] || [ -n "$HISTORY" ] || die "--all goes with --history"
if [ -n "$HISTORY" ]; then
  exec python3 "$(dirname "$SELF")/reviews.py" history ${ALL:+--all}
fi
if [ ${#NOTE[@]} -gt 0 ]; then
  exec python3 "$(dirname "$SELF")/reviews.py" note "${NOTE[0]}" "${NOTE[1]}"
fi
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
# level, DROID_REVIEW_EFFORT, then droid's per-model default.
# A fan-out leaves all of this to its children, one model each.
if [ -z "$MODELS" ]; then
  MODEL="$(shortcut "${MODEL:-glm}" || echo "$MODEL")"
  EFFORT="${EFFORT:-${WORD_EFFORT:-${SESSION_EFFORT:-${DROID_REVIEW_EFFORT:-}}}}"
fi

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
# The folder ignores itself, so no repo needs a .gitignore line for it.
[ -e "$OUT_DIR/.gitignore" ] || echo '*' > "$OUT_DIR/.gitignore"
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

# Run metadata: <base>.json beside the review and its log. It holds what an
# agent (or the droid-review-ui mod) needs to tell how fresh a review is — the
# commit, branch and base it ran against, the uncommitted changes it saw, when
# it started and finished — and whether it is still going (status, pid).
#   run_meta start  <json>          before droid runs: status "running"
#   run_meta finish <json> <result> after: status ok/failed, writes the review
#                                   file from it and prints its path + session
#   run_meta status <json> <status> just the status (interrupted)
# Each write replaces the file atomically. An "interrupted" status is kept by a
# later finish: the parent of a fan-out sets it while the child may still be
# writing its own end.
run_meta() {
  ROOT="$ROOT" MODE="$MODE" SCOPE="$SCOPE" BASE="$BASE" WHAT="$WHAT" \
  MODEL="${MODEL:-}" EFFORT="${EFFORT:-}" ASK="${ASK:-}" CHECKS="${CHECKS:-}" \
  SESSION="${SESSION:-}" SESSION_FILE="${SESSION_FILE:-}" \
  OUT="${OUT:-}" LOG="${LOG:-}" PID="$$" DROID_EXIT="${DROID_EXIT:-}" \
  python3 - "$@" <<'PY'
import datetime, json, os, re, subprocess, sys
mode, meta = sys.argv[1], sys.argv[2]
env = lambda k: os.environ.get(k) or None

def now():
    return datetime.datetime.now().astimezone()

def git(*args, raw=False):
    r = subprocess.run(("git",) + args, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.strip()

def load():
    try:
        with open(meta) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save(m):
    tmp = "%s.%d.tmp" % (meta, os.getpid())
    with open(tmp, "w") as f:
        json.dump(m, f, indent=2)
        f.write("\n")
    os.replace(tmp, meta)

def ended(m, status):
    t = now()
    m["finished"] = t.isoformat(timespec="seconds")
    if m.get("started"):
        m["duration_s"] = int((t - datetime.datetime.fromisoformat(m["started"])).total_seconds())
    head = git("rev-parse", "HEAD")
    if head and head != m.get("head"):
        m["head_at_finish"] = head
    if m.get("status") != "interrupted":
        m["status"] = status

def worktree():
    c = {"staged": 0, "unstaged": 0, "untracked": 0}
    for line in (git("status", "--porcelain=v1", "--untracked-files=all", raw=True) or "").splitlines():
        if line.startswith("??"):
            c["untracked"] += 1
            continue
        c["staged"] += line[0] != " "
        c["unstaged"] += line[1] != " "
    return c

def model_name(mid):
    """What droid's /model picker calls the model ("GPT-6.1 Sol"), for people to
    read: from the registry built into the droid binary, then the help's model
    list (it lags, but has "auto"). None when neither has it."""
    if not mid:
        return None
    import mmap, shutil
    try:
        with open(os.path.realpath(shutil.which("droid") or ""), "rb") as f:
            t = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        hit = re.search(rb'\{id:"%s",name:"([^"]+)"' % re.escape(mid.encode()), t)
        if not hit:   # the id may be a constant: o.GPT_6_SOL="gpt-6-sol", then {id:Mn.GPT_6_SOL,name:...}
            const = re.search(rb'\.([A-Z0-9_]+)="%s"' % re.escape(mid.encode()), t)
            if const:
                hit = re.search(rb'\{id:[\w$]+\.%s,name:"([^"]+)"' % const.group(1), t)
        if hit:
            return hit.group(1).decode()
    except (OSError, ValueError, TypeError):
        pass
    try:
        out = subprocess.run(("droid", "exec", "--help"), capture_output=True, text=True, timeout=10).stdout
        hit = re.search(r"^\s+%s\s{2,}(.+?)(?: \(default\))?$" % re.escape(mid), out, re.M)
        return hit.group(1).strip() if hit else None
    except (OSError, subprocess.SubprocessError):
        return None

def shortstat(*args):
    s = git("diff", "--shortstat", *args) or ""
    out = {}
    for key, word in (("files", "file"), ("insertions", "insertion"), ("deletions", "deletion")):
        m = re.search(r"(\d+) %s" % word, s)
        out[key] = int(m.group(1)) if m else 0
    return out

if mode == "start":
    m = {
        "kind": env("MODE"), "status": "running",
        "started": now().isoformat(timespec="seconds"), "finished": None,
        "pid": int(os.environ["PID"]),
        "model": env("MODEL"), "effort": env("EFFORT"),
        "droid_version": None,
        "asked": env("ASK"), "checks": env("CHECKS"),
        "continues": {"session": env("SESSION"), "review": env("SESSION_FILE")} if env("SESSION") else None,
        "round": 1,
        "repo": env("ROOT"), "branch": git("branch", "--show-current") or None,
        "head": git("rev-parse", "HEAD"), "head_subject": git("log", "-1", "--format=%s"),
        "scope": env("SCOPE"), "scope_text": env("WHAT"), "base": None,
        "uncommitted": worktree(),
        "session": None, "turns": None,
        "files": {"review": None, "log": env("LOG"), "meta": meta},
    }
    # A continuation is the next round of the review it continues: 2 for the
    # first re-check, and so on (a review from before rounds counts as 1).
    if env("SESSION"):
        prev = {}
        if env("SESSION_FILE"):
            try:
                with open(env("SESSION_FILE")[:-3] + ".json") as f:
                    prev = json.load(f)
            except (OSError, ValueError):
                pass
        m["round"] = (prev.get("round") or 1) + 1
    m["model_name"] = model_name(m["model"])
    try:
        r = subprocess.run(("droid", "--version"), capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            m["droid_version"] = r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    if m["scope"] == "branch":
        base = env("BASE")
        mb = git("merge-base", base, "HEAD")
        m["base"] = {
            "ref": base, "sha": git("rev-parse", base), "merge_base": mb,
            "ahead": int(git("rev-list", "--count", base + "..HEAD") or 0),
            "behind": int(git("rev-list", "--count", "HEAD.." + base) or 0),
        }
        m["diff"] = shortstat(mb) if mb else None   # merge-base to the working tree
    else:
        m["diff"] = shortstat("HEAD")
    save(m)

elif mode == "status":
    m = load()
    # Only a run still going takes a new status: a Ctrl-C that lands after
    # the review was written must not turn its "ok" into "interrupted".
    if m.get("status", "running") != "running":
        sys.exit(0)
    m["status"] = sys.argv[3]
    ended(m, sys.argv[3])
    save(m)

elif mode == "finish":
    m, out = load(), env("OUT")
    text = open(sys.argv[3]).read().strip()
    try:
        d = json.loads(text.splitlines()[-1])
    except Exception:
        d = {"is_error": True, "result": "droid did not return JSON:\n" + text[-2000:]}
    m["session"] = d.get("session_id") or m.get("session")
    if d.get("is_error"):
        ended(m, "failed")
        m["error"] = str(d.get("result"))[:2000]
        save(m)
        prefix = "" if m["error"].startswith("droid did not") else "droid reported an error: "
        sys.stderr.write(prefix + m["error"] + "\n")
        sys.exit(1)
    rc = int(env("DROID_EXIT") or 0)
    ended(m, "ok" if rc == 0 else "failed")
    if rc != 0:
        m["error"] = "droid exited %d after reporting completion" % rc
    m["turns"] = d.get("num_turns")
    m["droid_duration_s"] = (d.get("duration_ms") or 0) // 1000
    m["files"]["review"] = out
    short = lambda sha: (sha or "?")[:7]
    lines = ["- round: %s" % m.get("round", 1),
             "- started: %s" % m.get("started"),
             "- finished: %s (%ss)" % (m["finished"], m.get("duration_s", "?")),
             "- model: %s (reasoning %s)" % (m.get("model"), m.get("effort") or "droid default"),
             "- scope: %s" % m.get("scope_text")]
    where = "%s at %s" % (m.get("branch") or "detached HEAD", short(m.get("head")))
    if m.get("head_subject"):
        where += ' "%s"' % m["head_subject"]
    lines.append("- branch: %s (%s)" % (where, os.path.basename(m.get("repo") or "")))
    b = m.get("base")
    if b:
        lines.append("- base: %s at %s; merge-base %s; %d ahead, %d behind"
                     % (b["ref"], short(b["sha"]), short(b["merge_base"]), b["ahead"], b["behind"]))
    u = m.get("uncommitted") or {}
    lines.append("- uncommitted at start: %d staged, %d unstaged, %d untracked files"
                 % (u.get("staged", 0), u.get("unstaged", 0), u.get("untracked", 0)))
    df = m.get("diff")
    if df:
        lines.append("- diff reviewed: %d files, +%d -%d (tracked files; untracked not counted)"
                     % (df["files"], df["insertions"], df["deletions"]))
    if m.get("head_at_finish"):
        lines.append("- HEAD moved while it ran: %s -> %s" % (short(m.get("head")), short(m["head_at_finish"])))
    if m.get("asked"):
        lines.append("- asked: %s" % m["asked"])
    c = m.get("continues")
    if c:
        lines.append("- continues: %s" % (c.get("review") or c.get("session")))
    lines.append("- droid: %s" % (m.get("droid_version") or "?"))
    lines.append("- metadata: %s" % meta)
    lines.append("- session: %s" % m["session"])
    lines.append("- turns: %s, %ss" % (m["turns"], m["droid_duration_s"]))   # last: words() reads after it
    with open(out, "w") as f:
        title = "feedback" if m.get("kind") == "feedback" else "review"
        if (m.get("round") or 1) > 1:
            title += ", round %d" % m["round"]
        f.write("# droid %s\n\n" % title)
        f.write("\n".join(lines) + "\n\n" + (d.get("result") or "").strip() + "\n")
    save(m)
    print(out)
    print(m["session"] or "")
PY
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
  local t0=$SECONDS t0_iso drawn=""
  t0_iso="$(date +%Y-%m-%dT%H:%M:%S%z)"
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
        if [ -n "${LOGS[i]}" ]; then
          echo "[$(elapsed "$now")] interrupted" >> "${LOGS[i]}"
          run_meta status "${LOGS[i]%.log}.json" interrupted || true
        fi
        say "$i" "interrupted  $(elapsed "$now")"
      done
      break
    fi
    # A TERM to the whole process group kills this sleep too; under set -e
    # that would end the parent before the trap above got to tidy up.
    sleep 1 || true
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
    echo "- started: $t0_iso"
    echo "- finished: $(date +%Y-%m-%dT%H:%M:%S%z)"
    echo "- scope: $WHAT"
    echo "- branch: ${BRANCH:-detached HEAD} at $(git rev-parse --short HEAD)"
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
META="$OUT_BASE.json"
run_meta start "$META"
# Interrupted (Ctrl-C, or TERM from a fan-out parent): say so in the log and
# the metadata, so nothing reads this run as still going. bash runs the trap
# once the droid pipeline it is waiting on has ended.
# A fan-out child leaves the log line to its parent, which writes one too.
trap '[ -n "${_DROID_REVIEW_CHILD:-}" ] || echo "[$(elapsed "$SECONDS")] interrupted" >> "$LOG"
      run_meta status "$META" interrupted; exit 130' INT TERM

set +e
droid "${DROID_ARGS[@]}" "$PROMPT" | progress_filter "$LOG" "$JSON" "$MODEL" "$EFFORT"
STATUS=${PIPESTATUS[0]}
set -e

claim_out
DROID_EXIT="$STATUS" run_meta finish "$META" "$JSON" || { rm -f "$OUT"; exit 1; }

exit "$STATUS"
}
