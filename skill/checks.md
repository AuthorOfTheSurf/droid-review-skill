Checks, cheapest first — edit this list for your repo. The reviewer runs these
before trusting a claim about behavior; a finding backed by a check beats a
finding backed by reading the diff.

- `<lint/typecheck command>` — fast, no build, run on every review.
- `<unit test command>` — the test suite (or the slice covering changed files).
- `<integration/e2e command>` — slower, end-to-end checks; only when the
  changed path is the one they cover.
- `<UI or manual-verification tool, if any>` — if the repo has a way to drive
  the app and read its state (a simulator harness, a browser automation tool,
  a CLI), name it and say when to reach for it.

Delete this file entirely to fall back to whatever the project's own
instructions file (AGENTS.md / CLAUDE.md) says about testing — the reviewer is
told to read that when there's no checks.md here.
