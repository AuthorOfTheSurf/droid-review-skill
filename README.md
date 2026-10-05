# droid-review

Ask [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart) to review your branch in the background, and give that feedback to your main coding agent to triage. Your main agent should fix what needs fixing, and then request a follow up review which should be fast to complete.

I do not believe that harnesses and models can effectively code-review themselves. This is because I believe they have the same approach to the tasks at hand, and so they will step through the problems and "think" about them in a similar way as the agent that wrote the code. *Therefore I believe that the best way to get an agentic code review and second-opinon is by using a different harness + different model.*

For your main coding agent AND your backup/review agent, you will want harness (Claude Code / Droid) and model (Opus, Fable / GLM, Gemini) combinations that are made by smart people that are competitive and care a lot about doing a good job. I believe my stack of CC Opus 5.5 + Droid w/ GLM 5.3 Flash/Gemini 3.8 Flash satisfies this requirement 

### Usage

```sh
/droid-review
# Or with options
/droid-review [glm|gemini|luna|auto|fable|opus|sonnet|astra|sol|grok|qwen|kimi|deepseek] [effort] [focus]
```

What happens:
- Your main agent (e.g. Claude) invokes the skill
- It will request `droid` to do a review in the background, and await the results
- It will receive the code review results within a couple minutes
- It will triage (prioritize, accept, reject) each point of feedback
- Your main agent will do the fixes and then request re-review from the same droid session, which re-uses the session cache resulting in a fast re-review (generally under 30-60 seconds)
- Done. 

Benefits:
- Review was solicited from a different coding harness and model resulting in a true second opinion
    - In my experience, GLM (5.2 and now 5.3 Flash) have been able to find issues in Claude Code's best models, and serve as nice secondary opinions. 
- Time
- No copy-pasting a review between two chat windows. One command runs the loop
- Easy to do on mobile
- Easy to enable automatically via `CLAUDE.md` and/or your prompt (e.g. "Fix this bug and solicit /droid-review") — so your agent will go off for longer, and come back with work that you can be more confident in
- In the short and long run I believe that only agents and verification tests will be able to review code correctness. Human review has a place, but the first step is automation (tests, guardrails) and further leveraging agentic coding skills (`/droid-review` skill, using different harness+model to get a review)

### The Skills

| | |
|---|---|
| **`/droid-review`** | wraps droid's own `/review` skill. Receive a structured code review: severity, file:line, the scenario that breaks. Triage is confirmed / pre-existing / false positive / nit, then fix and re-check. |
| **`/droid-feedback`** | an open-ended prompt, literally ask for feedback like "is this approach sane?". Receive prose back, no imposed format. Use when you want feedback, not code review |
| **`/droid-history`** | the history: this branch's reviews, each with its re-checks, the commit it reviewed and how far you've moved since, and what your agent did about it. Runs no model |

### When to use it

Near merge, on a branch you believe is code complete

### How to get the most out of it

The one thing `droid` needs from your repo is *how to check things* — the tests, the linter, the typechecker, the e2e suite, whatever drives the app.

The best way to provide this info is in **AGENTS.md / CLAUDE.md**, which droid always loads. In general it is good practice to list out your verification layer here; it helps humans and it helps agents

If the instructions for verification live somewhere else in your repo, point at it. This will help with efficiency rather than leaving it up to `droid` to figure it out

```bash
droid-review.sh --checks docs/testing.md
```

### What droid does in your repo

- The reviewer runs at droid's `--auto medium`, which means that inside your repo
it can run your build and test suites, install packages, make network requests,
and commit locally. 
- This is deliberate, finding should be backed by checks, and not just reading the diff
- The script removes droid's file-editing tools (`ApplyPatch`, `Edit`, `Create`) so it can't edit your files, and the prompt tells it not to commit
- If that's more autonomy than you want, drop `--auto medium` from the `DROID_ARGS` array in the script; droid then runs read-only and reviews from the diff alone. Not recommended, but the option is there for you

### Requirements

- **The `droid` CLI**, installed and authenticated: <https://docs.factory.ai/droid-cli/quickstart>.
  You need a Factory account with access to a model — the script defaults to
  `glm-5.3-flash`, but any model your plan can run works (`--model`).
- **git** and **python3** (the script parses droid's JSON output with it)
- **A primary coding agent with its own subscription** to do the triage/fix step. This is generally the same agent that did the implementation. I recommend [Claude Code]( https://claude.ai/ ) but alternatives like Cursor, Codex, Pi, etc. work too

A run takes anywhere from ~40s to ~8 minutes depending on model, branch size, and how many checks it decides to run, and it bills against your Factory plan. Your agent should run it in the background automatically. It should be run in the background, or at minimum with a large timeout.

### Install

Install the three skills together — `droid-feedback` and `droid-history` are thin wrappers around the script in `droid-review`, so they share one implementation and can't drift apart. Have your main coding agent help you with this, they are great at this sort of task!

The usual way: clone this repo and link the skills into your personal skills
folder, so a `git pull` here updates every project:

```bash
git clone https://github.com/AuthorOfTheSurf/droid-review-skill
cd droid-review-skill
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/droid-review" "$PWD/skills/droid-feedback" "$PWD/skills/droid-history" ~/.claude/skills/
```

Run `git pull` in the clone now and then to pick up new model shortcuts. To
remove it, delete the three links.

Or copy them into one project (a copy never updates):

```bash
mkdir -p .claude/skills
cp -r path/to/droid-review-skill/skills/droid-review path/to/droid-review-skill/skills/droid-feedback path/to/droid-review-skill/skills/droid-history .claude/skills/
```

Reviews land in `.droid-reviews/` in whichever repo you run from. The folder
ignores itself (the script puts a `.gitignore` of `*` in it), so no repo needs
a line for it.

Usually you will need to restart your `claude` in order to pick up new skills. After restart you should see `/droid-review`, `/droid-feedback` and `/droid-history` autocomplete and be available

### Model shortcuts

- First parameter allows optional specification of a model, e.g. (glm = GLM 5.3 Flash)
- Second parameter is an effort level, overriding droid's default for that one run (`/droid-review luna max`)
- Anything else is the focus, so `/droid-review the gemini integration` is a GLM review about Gemini

| Shortcut | Model | droid's default effort | Levels it takes |
|---|---|---|---|
| `glm` (default) | `glm-5.3-flash` | high | low, high, max |
| `gemini` | `gemini-3.8-flash` | high | low, medium, high |
| `luna` | `gpt-6-luna` | medium | none … max |
| `auto` | `auto` | none (droid picks) | — |
| `fable` | `claude-fable-5.1` | high | off … max |
| `opus` | `claude-opus-5-5` | medium | low … max |
| `sonnet` | `claude-sonnet-5-5` | high | low … max |
| `astra` | `gpt-6-astra` | medium | low … max |
| `sol` | `gpt-6.1-sol` | medium | low … max |
| `grok` | `grok-4.7` | high | low … xhigh |
| `qwen` | `qwen3.8-max` | xhigh | low, medium, xhigh |
| `kimi` | `kimi-k3` | high | off, low, high, max |
| `deepseek` | `deepseek-v4.1-flash` | high | off, low, high, max |

No shortcut pins an effort: each runs at droid's default for that model, and
a higher level is opt-in for the run you name it on (`/droid-review luna max`).
A max-effort review can take half an hour.

A comma list where some names are models and some are not (`glm,sonet`) stops
before anything runs and names each one that is not, with the ids it could
have meant.

Any other model id droid accepts works as the first word too (`droid exec -m x
--list-tools` lists them all; `droid exec --help` lags behind). A shortcut at
droid's default effort starts at once: there is nothing to check, so droid is
asked nothing first. An effort you name is checked against the levels that
model supports before droid starts, so `gemini max` fails at once with the
levels Gemini takes, and so is a model id that is not a shortcut, against the
ids your droid install lists (about a second; only an id it does not list is
put to droid itself, which takes ten or so). `droid-review.sh --efforts` prints every model's levels and default
(`--efforts luna` just one) — the same table droid's `/model` picker shows,
read from the droid install, so it covers models `droid exec --help` leaves
out — with each model's price multiplier and whether it is new, on sale or
deprecated. `--whats-new` prints what the top of `/model` shows: new models,
discounts and when they end, deprecated models with droid's replacement, and
whether each shortcut is the newest generation in droid's own family order. The
table lives in `shortcut()` in the script; the family names point at the newest
model as of droid 0.232.0, so move them when droid ships a newer one.

### Just the script

`skills/droid-review/droid-review.sh` runs standalone from any shell:

```bash
droid-review.sh                          # /review, branch vs. detected default branch
droid-review.sh "the payment retry logic" # same, with something to weight
droid-review.sh --feedback "<ask>"        # plain-words feedback instead of /review
droid-review.sh --uncommitted
droid-review.sh "luna the payment retry logic" # a model shortcut first
droid-review.sh --models                 # list the shortcuts
droid-review.sh --efforts luna           # a model's effort levels and default (alone: every model)
droid-review.sh --whats-new              # new, discounted and deprecated models; shortcuts vs. newest
droid-review.sh --models glm,gemini,grok "the auth changes"   # all three, in parallel
droid-review.sh "glm,gemini the auth changes"                 # same fan-out, as the first word
droid-review.sh --base origin/main --effort max
droid-review.sh --checks docs/testing.md
droid-review.sh --session last "re-check the fixes in HEAD"
droid-review.sh --note last "fixed 2; the race is a false positive"   # what came of a review
droid-review.sh --history                # this branch's reviews (--all: every branch)
droid-review.sh --compare                # the newest review against the repo now (or: --compare <review|session>)
droid-review.sh --help
```

The positional argument is what you're asking droid for this time: emphasis on
top of `/review`, the whole ask under `--feedback`, or the re-check instruction
with `--session`

A `--session` run keeps the model and effort that wrote the
review, read from the review file's header, unless you name a model.
`DROID_REVIEW_BASE`, `DROID_REVIEW_MODEL` and `DROID_REVIEW_EFFORT` set the
defaults.

It prints the file it saved to and the droid session id; paste both into
whatever you're using to do the triage. While droid works, its progress streams
into a `.log` of the same name (one line per tool call: elapsed, turn, tool,
target), so `tail -f` shows what it is doing.

Each run also writes a `.json` of the same name: its status (`running`, then
`ok`, `failed` or `interrupted`), when it started and finished, the branch,
commit and base it reviewed, and how many files were staged, unstaged and
untracked at the time. The review file's header carries the same facts, so you
(or your agent) can tell how fresh an old review is against the repo now.

**Several models.** `--models a,b,c` (or a comma list as the first word) runs
the same ask on each model in parallel, each at its shortcut's effort. On a
terminal, stderr shows a board redrawn in place, one line per model; elsewhere
(an agent's shell, CI) it prints one line per state change. stdout gets
`model<TAB>status<TAB>path<TAB>session` per model and, last, an index file
`.droid-reviews/<stamp>-<branch>-multi.md` tabling status, time, words, session
and result for each. Exit 0 if any model succeeded; Ctrl-C stops the rest and
keeps what finished. `--models` with no list still prints the shortcuts.

### History, and what came of each review

`/droid-history` (or `droid-review.sh --history`) lists the reviews on this
branch, newest first, each with its re-checks:

```
droid reviews · review-status-mod · HEAD 82474b1 · clean

GLM-5.3-Flash · review · 2 rounds · session 71feef9c-4f42-4fac-90c1-99274f49d494
  1  today 23:18       ok in 3:02 · 12 turns       at 0cf440d, 9 commits behind
     → fixed date -r and the quoting after --; rejected the pid race as a false positive
  2  today 23:55       ok in 3:07 · 21 turns       at 274a06f, 8 commits behind
     → all three fixes confirmed; nothing new
```

Each round says when it ran, how it ended, and the commit it reviewed against
HEAD now, so you can tell a fresh review from a stale one. `all` (`--all`)
lists every branch.

The `→` lines are notes. After triage, the skill has your agent record what it
did about the review in one line (`droid-review.sh --note <review> "<line>"`),
before it asks for the re-check. Read down a thread and you get the finding,
what was done, and the reviewer's verdict on it. A note is the agent's own
account, kept in the run's `.json` and under `## Response` in the review file.

### Is a review still current, and is a finding yours?

`droid-review.sh --compare` (the newest finished review; or `--compare <review
file | session id>`) sets a review against the repo as it is now. No model
runs.

```
GLM-5.3-Flash · review · round 1 · today 00:24
reviewed c7d7fb5 · HEAD is 4073ac9, 2 commits on
uncommitted then: none · now: 2 files

changed since the review: 3 files
  README.md                          committed
  skills/droid-review/statusline.py  committed, uncommitted
  notes.txt                          uncommitted (untracked)

cited in the review: 2
  skills/droid-review/statusline.py:47  changed on this branch · changed since (committed)
  skills/droid-review/runs.py:12        not changed on this branch · unchanged, now line 14
```

- **Changed since** is measured against your working tree, not just HEAD:
  staged, unstaged and untracked changes count. Before paying for a re-check,
  this says whether anything the review looked at has moved.
- **Each `file:line` the review cites** gets two answers. Did this branch
  change that line (`changed on this branch`, `new on this branch`), or was it
  already there (`not changed on this branch`) — a finding about code the
  branch did not touch is likely pre-existing. And has the line changed since
  the review, in a commit or uncommitted; if not, where it sits now.
- A reviewer's line number is approximate and a fix often lands beside it, so
  a change within 3 lines counts.
- A review can run on a dirty tree. Each run records the content hash of every
  file that was uncommitted then, so such a file is later either the same as
  the reviewer saw or `uncommitted then, different now`, in which case its
  lines cannot be compared. Reviews from before this was recorded say so.

The citations are read out of the review's prose, so one written as
"line 40 of the script" is not seen. `not changed on this branch` is where to
look, not a verdict: a branch can break old code without touching it.

### Live status in Claude Code (optional)

Reviews usually run in the background while you keep working. To see them as
they go, add rows to Claude Code's status line, one per running review, under
the status line you already have:

```
⠹ droid-review · GLM-5.3-Flash               [ ⠹ 25s / ~40s               ]  reading files · turn 3 · Read src/auth.ts
⠹ droid-review · Gemini 3.8 Flash (round 2)  [ ⠹ 4m 12s / ~1m 30s         ]  running checks for 50s · turn 9 · Execute npm test
✓ droid-feedback · GPT-6 Luna max            [ ✓ 2m 14s · 21 turns        ]  awaiting triage for 3m
```

Each row opens with the command that ran, then the model, with the effort
when you named one. "(round 2)" is a re-check (`--session`), the second round
of that review; the review file's title and metadata carry the round too.

**The bar** is one piece, with its text inside. Its ground fills from the left
against the time after `~`: the median of that model's earlier finished runs of
the same kind in the repo (review or feedback, first round or re-check). The
cell at the edge of the fill shades in gradually, so the bar moves at every
repaint. It reaches four fifths at the estimate and stops there, still green,
however late the run is: the open fifth is the part nobody knows. Only a
finished run fills the bar. Until there is any history a block drifts across
it. When the run ends, the same bar holds the result. With nothing to show it
prints nothing.

**After the bar** is what droid is doing right now, which is the thing to read
when a run is well past its estimate. It is worked out from the kinds of tool
droid called in its last three turns, not from what the calls said:

| It says | When droid's recent calls are mostly |
|---|---|
| `starting` | none yet |
| `reading files` | Read, Grep, Glob, LS, or a command that only looks (`git diff`, `cat`, `ls` …) |
| `running checks` | any other command (`running commands` in a feedback run) |
| `researching` | WebSearch, FetchUrl |
| `planning` | TodoWrite |
| `working` | any other tool (Skill and ToolSearch aside: those are droid setting up, and are not counted) |
| `thinking` | nothing logged for 30 seconds, and no command still out |

droid logs its tool calls, not its reasoning or the writing of its answer, so
`thinking` covers both. The log does record when a command comes back, so a
check that is still going after 30 seconds stays `running checks`, and one
that has returned does not. Either way the row then says for how long:
`thinking for 48s`, `running checks for 3m 20s`. The last call follows in grey,
without the `cd … &&` a command opens with.

**A finished row** stays a while, and says what has come of the review:
`awaiting triage for 3m`, then the note your agent left when it triaged it
(`triaged 2m ago: fixed 2; rejected the race as a false positive`). A run that
failed or was interrupted says how long ago. The row goes fifteen minutes
after the run ended, or after that note if it came later; a review still
waiting to be triaged stays an hour.

It is one script, `skills/droid-review/statusline.py`, set in
`~/.claude/settings.json`. Put the status line command you already have, if
any, after `--`: it runs first, on the same input, and these rows go under it.
If that command has a pipe, `&&` or `;` in it, give it as one quoted string
(`-- 'mine.sh | cut -c1-80'`): unquoted, the shell would send these rows into
the pipe along with yours.

```json
"statusLine": {
  "type": "command",
  "command": "python3 /path/to/droid-review-skill/skills/droid-review/statusline.py -- <your current statusLine command>",
  "refreshInterval": 1
}
```

`refreshInterval` re-runs the line every second (the lowest Claude Code takes), so the elapsed time moves
while the session is idle. To undo, put your old command back.

### Maintaining it

droid changes under the script without warning: new models, retired ids,
renamed flags, a different help format. In this repo, `/maintain-droid-review-skill`
(a project skill under `.claude/skills/`) checks the script against the
installed droid, proposes shortcut moves for you to pick from, runs every
script path against a stub droid, and keeps the docs in agreement. Run it after
a droid upgrade.

## License

MIT — see [LICENSE](LICENSE).
