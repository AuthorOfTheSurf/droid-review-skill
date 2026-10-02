---
name: maintain-droid-review-skill
description: Maintainer pass over the droid-review and droid-feedback skills — check them against the installed droid CLI (model catalog, effort levels, flags, the stream-json events the script parses), move the model shortcuts the user picks, run the script's paths against a stub droid, and keep README / SKILL.md / the script in agreement. Run only when the user asks to maintain, check, or update the droid skills or their shortcuts, or after a droid upgrade.
---

# Maintain the droid-review skill

`skills/droid-review/droid-review.sh` wraps a CLI this repo does not control,
and most of what it depends on breaks **silently**: droid ships a model and
`opus` keeps pointing at the old one because the old id still validates; a
help format changes and effort checks quietly switch off; a flag is renamed and
droid ignores the unknown one. This pass finds that drift, proves the script
still works, and ships the corrections.

Two kinds of change come out of it. **Contract breakage** (the script no longer
reads droid correctly) is a bug: fix it, show the evidence. **Which models earn
a shortcut** is the user's judgment, not yours: gather the evidence, recommend,
change only what they pick.

## 1. Get current

```bash
git pull
droid --version            # compare with "as of droid X" above shortcut() and in README.md
skills/droid-review/droid-review.sh --whats-new
```

**Echo the `--whats-new` output into your reply verbatim, every run**, before
anything else. It is what the user sees at the top of droid's `/model` picker
(new models, discounts and their end dates, deprecations with droid's fallback),
plus each shortcut checked against droid's own family order, and they decide
from it. Having it in the transcript is the point.

If droid itself is behind, everything below is too; say so, and let the user
decide whether to update droid first.

## 2. Contracts — does the script still read droid?

Each check is cheap and needs no model run unless it says so.

**Model catalog and efforts.** `catalog()` merges three sources: the ids
`droid exec -m x --list-tools` accepts (stderr), the `Model details:` in
`droid exec --help`, and the model registry built into the droid binary — the
same table the interactive `/model` picker shows, which fills in every model the
help leaves out.

```bash
d=skills/droid-review/droid-review.sh
$d --efforts                      # every accepted id: default, supported levels, shortcut
$d --efforts | awk '$3 ~ /^\(droid gives none\)/ && $1 !~ /^custom:/'   # must print nothing
```

Every built-in id must show levels. A built-in id with `(droid gives none)` means
the registry extraction stopped matching (droid changed its bundle): fix the
regex in `catalog()`. To confirm the extraction is still trustworthy, check it
against the help wherever both list a model — they must agree exactly:

```bash
droid exec --help | sed -n '/Model details:/,/^$/p' | grep ' - '   # eyeball against $d --efforts
```

`--whats-new` reads more of the same registry: the `newUntil` badge date,
`cost.promotions` (discount, start, expiry, label), `deprecation` with its
`fallbackModelId`, and the family list (`generations:[{id:...},...]`, newest
first). If every shortcut shows `(no family listed)`, or NEW / ON SALE /
DEPRECATED are all `(none)` while the user's `/model` shows badges, the
extraction stopped matching: fix the regexes in the `--efforts`/`--whats-new`
block.

When the user asks "what levels does X take", `$d --efforts X` is the answer;
never guess, and never probe with a real run — droid runs an unsupported effort
without complaint, so a reply proves nothing.

**Validation fires before droid runs** — both must exit 2 at once, not start a review:

```bash
$d --model droid-review-no-such-model      # "droid has no model ..."
$d "gemini max"                            # "... takes reasoning effort low,medium,high, not 'max'"
```

If either starts droid, the catalog came back empty: read the stderr line
("could not read droid's model list") and fix the parser.

**Reviewer tool set.** The script runs `--auto medium --remove-tools ApplyPatch`.

```bash
droid exec --auto medium --remove-tools ApplyPatch --list-tools
```

`ApplyPatch` must show `blocked`, and no other tool may appear under `Edit`. A
new editing tool (or a renamed ApplyPatch) means the reviewer can author: add it
to `--remove-tools` in `DROID_ARGS`. Execute stays allowed on purpose — the
reviewer runs the test suites.

**Stream-json events (one small model run — ask before spending it).**
`progress_filter` reads `system/init` (`session_id`, `model`, `reasoning_effort`),
`tool_call` (`messageId`, `toolName`, `parameters`), `error` (`message`) and
`completion` (`finalText`, `numTurns`, `durationMs`, `session_id`).

```bash
droid exec -o stream-json -m glm-5.3-flash -r low --remove-tools ApplyPatch \
  "Read the first line of README.md and reply with it." | head -c 4000
```

Every field above must be present under that name. A missing one breaks the
live log or loses the session id: fix `progress_filter` and the stub below.
Skip this run when a real review under `.droid-reviews/` already ran on the
current droid version and its `.log` shows turns and a `done` line.

## 3. Model shortcuts

Start from the SHORTCUTS section of `--whats-new`: it checks each shortcut
against droid's own family list, newest generation first, and names any newer
generation and any deprecation with droid's fallback. Do not infer newness from
the `--list-tools` order (it is not newest first: `gemini-3.1-pro-preview` sits
above `gemini-3.8-flash`). `--efforts` gives levels, price and notes per model.
Report, in one table (shortcut → current → candidate → why):

- **A shortcut's model marked `[Deprecated]` or gone.** These break for users
  once droid drops the id, so lead with them, and always propose a replacement:
  the newest non-deprecated model in the family, naming any tier change
  (pro → flash) and checking its levels against the pin. Moving off deprecated
  models is the expected outcome; only removing the shortcut needs the user to
  argue for it. droid's declared fallback is the default candidate.
- **A newer model in a shortcut's family** (`NEWER:` in `--whats-new`). Name the
  kind of change — a version bump, a different tier (pro vs. flash), a `-fast`
  variant, a preview. Only a plain version bump is like-for-like; the rest are
  choices.
- **A pinned effort the model no longer supports**, or a candidate whose levels
  differ from the pin (a pin of `max` cannot carry over to a model that tops out
  at `high`). An unpinned shortcut runs at droid's default — `--efforts` shows
  what that is.
- **New or discounted models** from `--whats-new` worth a shortcut or a move,
  with the discount's end date — a sale is a reason to try a model, not to pin
  a shortcut to it.
- **Families with no shortcut yet**, listed briefly. Do not propose adding them
  unless the user asks.

If nothing drifted, say so in one line. Apply only what the user picks: edit
`shortcut()`, the droid version in the comment above it, and the shortcut table
and version note in README.md — the three must agree. Update `argument-hint` in
both `skills/*/SKILL.md` only when a shortcut name is added or removed. Then:

```bash
$d --models | while read -r s id _; do
  $d --efforts "$id" >/dev/null 2>&1 && echo "$s $id ok" || echo "$s $id MISSING"
done
```

and check each pinned effort appears in that model's `--efforts` levels.

## 4. Regression — run the script's paths against a stub droid

`stub-droid` (next to this file) answers `exec` runs with canned stream-json
and forwards `--help` / `--list-tools` to the real droid, so this costs nothing.
Run in a throwaway repo so `.droid-reviews/` lands there:

```bash
r="$(git rev-parse --show-toplevel)"; d="$r/skills/droid-review/droid-review.sh"
t="$(mktemp -d)"; mkdir -p "$t/bin" "$t/repo"
ln -sf "$r/.claude/skills/maintain-droid-review-skill/stub-droid" "$t/bin/droid"
export REAL_DROID="$(command -v droid)"
cd "$t/repo" && git init -q -b master && git commit -q --allow-empty -m a \
  && git checkout -q -b feat && echo x > f && git add f && git commit -q -m b
run() { PATH="$t/bin:$PATH" "$@"; echo "exit=$?"; }
run "$d" --base master                          # review path + session id, exit 0
run "$d" --base master --session last           # "continuing ...", same model, exit 0
run "$d" --base master --models glm,gemini      # both ok, table + -multi.md index, exit 0
STUB_DROID_MODE=fail-silent run "$d" --base master --models glm,gemini  # both failed, index written, exit 1
STUB_DROID_MODE=error run "$d" --base master    # "droid reported an error", exit non-zero
run "$r/skills/droid-feedback/droid-feedback.sh" --base master "is this sane"  # feedback path, exit 0
cd "$r"
```

Each line's expectation is in its comment; any other outcome is a script bug.
Also run `bash -n` and `shellcheck` on both scripts (shellcheck: only report new
warnings). Add a stub mode when a fix covers a failure the stub cannot yet
produce.

## 5. Docs agree with the script

- Every flag `usage` prints (`$d --help`) is described in README.md, and the ones
  a skill user needs appear in `skills/droid-review/SKILL.md`.
- The shortcut table in README.md matches `$d --models`.
- `argument-hint` in both SKILL.md files lists exactly the shortcut names.
- Every `droid-review.sh` example in README.md and both SKILL.md files still
  parses: run it with a model/effort it names through `--efforts`, or with
  `--help`-only flags, rather than starting a review.

## 6. Report and commit

One table: check → result → what you changed. Then one commit, title only,
naming the moves (e.g. `Maintain: opus → claude-opus-5-6, drop deprecated
minimax, catalog reads droid 0.240 help`). Push when the user agrees. Users who
installed by symlink pick it up on their next `git pull`; nothing to restart.
