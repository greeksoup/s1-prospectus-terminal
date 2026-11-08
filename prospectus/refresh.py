"""Has EDGAR got a newer filing than the one the dashboard was built from?

A prospectus changes: an amendment adds the price range, the final 424B sets the price. The page
asks this once a day while it is open; `python3 -m prospectus refresh` checks every company in library/
and rebuilds the ones with something new (GitHub's free scheduler can run it daily)."""
import json

from .dashboard import LIB
from .fetch import registration_filings


def check(cik, known=None):
    """{"new": [{"form", "date"}...]} for registration filings newer than the ones on record."""
    if known is None:
        from .ask import find_bundle
        b = find_bundle(cik) or {}
        known = b.get("meta", {}).get("filings", [])
    have = {(f["form"], f["date"]) for f in known}
    latest = max((f["date"] for f in known), default="")
    new = [{"form": f["form"], "date": f["date"]} for f in registration_filings(int(cik))
           if (f["form"], f["date"]) not in have and f["date"] >= latest]
    return {"new": new}


def run(rebuild=True):
    from .__main__ import build
    out = []
    for p in sorted(LIB.glob("*.json")):
        meta = json.loads(p.read_text())["meta"]
        try:
            r = check(meta["cik"], meta.get("filings", []))
        except Exception as e:  # SEC down or rate-limited: say so, keep going
            out.append((meta["name"], f"could not check ({e})"))
            continue
        if r["new"] and rebuild:
            build(str(meta["cik"]), open_browser=False)
        out.append((meta["name"], ", ".join(f"{n['form']} {n['date']}" for n in r["new"]) or "nothing new"))
    return out
