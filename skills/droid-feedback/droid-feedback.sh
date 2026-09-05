#!/usr/bin/env bash
# droid-feedback: ask droid for a second opinion in its own words, rather than
# running its /review. One implementation lives in the droid-review skill next
# door, so the two commands cannot drift apart — install them as a pair.
#
#   droid-feedback.sh "<what you want droid to look at>"
#
# Every flag droid-review.sh takes works here too; --help prints them.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
IMPL="$DIR/../droid-review/droid-review.sh"
[ -x "$IMPL" ] || {
  echo "the droid-review skill is not installed next to this one." >&2
  echo "expected: $IMPL" >&2
  echo "droid-feedback shares its implementation; install both skills together." >&2
  exit 2
}
exec "$IMPL" --feedback "$@"
