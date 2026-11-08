"""SpaceX S-1 (20 May 2026): the flags must catch what the June edition caught by hand.
Run: python3 -m tests.test_spacex_flags
"""
import glob

from prospectus.flags import run

flags = run(glob.glob("data/1181412/filings/2026-05-20_S-1_*.htm")[0])["flags"]
titles = [(x["title"], x["page"]) for x in flags]

CHECKS = [
    ("technical default and waiver on F-30 (June: F-30)", any("default or lender waiver" in t and "F-30" in p for t, p in titles)),
    ("2029 debt wall", any("falls due in 2029" in t for t, _ in titles)),
    ("debt to equity moved by shrinking equity", any("shrinking equity" in t for t, _ in titles)),
    ("Anthropic rate in the body, missing from the notes (June: p. 14 vs F-63; printed pages are 13 and F-62)",
     any(t.startswith("Anthropic: $1.25 billion") and p == "13 vs F-62" for t, p in titles)),
    ("Anthropic deal cancellable on 90 days' notice", any("90 days" in t and "Anthropic" in t for t, _ in titles)),
    ("2025 loss mostly not cash", any("2025 loss is not cash" in t for t, _ in titles)),
    ("no price yet", any("No price" in t for t, _ in titles)),
]
misses = 0
for name, ok in CHECKS:
    misses += not ok
    print("ok  " if ok else "MISS", name)
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} caught")
raise SystemExit(misses)
