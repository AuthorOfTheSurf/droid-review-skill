Checks, cheapest first; CLAUDE.md (loaded for you) has the detail:
- `ast-grep scan` — structural lint, under a second, always.
- `cd server && npm test && npm run typecheck && npm run verify:dashboard` — a second, for server changes.
- `ios/test.sh` — the iOS unit tests, seconds warm. It replaces the installed simulator app; that is fine, `ios/scenario.sh` rebuilds when stale.
- `ios/scenario.sh <preset>` then `agent-device` — put the app in a named state and read identifiers and values (never screenshots) when a finding depends on what the UI shows. docs/features/ has one map per flow with the exact tap sequences.
- `e2e/verify-purchases.sh` — about five minutes, drives the simulator through the whole purchase path; only when the purchase path changed.
Never pass a --device/--udid flag to agent-device; the simulator is the default.
