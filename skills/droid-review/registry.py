"""What droid's /model picker shows beside each model, read from the registry
built into the droid binary: its token-price multiplier and any promotion on it
(a discount until a date), the "new" badge, a deprecation with the model droid
falls back to, and the model families. These are droid internals, not an
interface: a field it cannot read is left out.

droid-review.sh reads it for --efforts and --whats-new, and for the price a run
records in its .json."""

import datetime as dt
import mmap
import os
import re
import shutil

day = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def read(now):
    """({model id: {price, promo, new, dep, fallback}}, {model id: (rank, generations)}) as of `now`."""
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
        for m in re.finditer(rb":\{id:\"([\w.:-]+)\",(?:newUntil:new Date\(\"([^\"]*)\"\),)?name:", t):
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
            new = g(r"newUntil:new Date\(\"([^\"]+)\"\)") or (m.group(2) or b"").decode() or None
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
    return info, family


def price(i):
    """The multiplier a model costs now, its promotion taken off; None when droid gives none."""
    if not i or i.get("price") is None:
        return None
    return round(i["price"] * (1 - i["promo"][0]), 4) if i.get("promo") else i["price"]
