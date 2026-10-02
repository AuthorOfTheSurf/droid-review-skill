#!/usr/bin/env bash
# droid-reviews: this branch's droid reviews, newest first — each with its
# re-checks, the commit it reviewed, how far HEAD has moved since, and what was
# done about it. One implementation lives in the droid-review skill next door;
# install them together.
#
#   droid-reviews.sh          # this branch
#   droid-reviews.sh all      # every branch
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
IMPL="$DIR/../droid-review/droid-review.sh"
[ -x "$IMPL" ] || {
  echo "the droid-review skill is not installed next to this one." >&2
  echo "expected: $IMPL" >&2
  echo "droid-reviews shares its implementation; install both skills together." >&2
  exit 2
}
case "${1:-}" in
  "")          exec "$IMPL" --history ;;
  all|--all)   exec "$IMPL" --history --all ;;
  *) echo "droid-reviews takes nothing (this branch) or all (every branch)" >&2; exit 2 ;;
esac
