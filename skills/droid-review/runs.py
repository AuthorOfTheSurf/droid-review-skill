"""What statusline.py and reviews.py both read from .droid-reviews/: where
it is, whether a run's process is alive, the ends of its log, and the colours
both print in. Neither script needs the other."""

import os

# A run killed outright (SIGKILL, a reboot) never records its end, and its pid
# can be reused; a log silent this long means it is not running any more.
STALE_S = 3600

RESET, BOLD = "\033[0m", "\033[1m"
TEAL, GREEN, AMBER, RED, GREY = (
    "\033[38;2;94;196;182m", "\033[38;2;63;185;80m", "\033[38;2;230;180;80m",
    "\033[38;2;248;81;73m", "\033[38;5;245m")


def find_reviews(start):
    """The nearest .droid-reviews/ at or above start, or None."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, ".droid-reviews")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def alive(pid):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, TypeError, ValueError):
        return True   # exists but not ours, or unknowable: do not call it dead
    return True


def log_ends(path):
    """First and last non-empty line of a log, reading only its ends."""
    try:
        with open(path, "rb") as f:
            first = f.readline().decode("utf-8", "replace").strip()
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", "replace").strip().splitlines()
    except OSError:
        return None, None
    return first, (tail[-1] if tail else None)


def clock(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60) if s < 3600 else "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


def silent_for(folder, m, now):
    """Seconds since the run's log was last written (0 when there is no log yet)."""
    try:
        return now - os.path.getmtime(os.path.join(folder, m["_name"] + ".log"))
    except OSError:
        return 0
