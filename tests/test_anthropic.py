"""Anthropic S-1/A (2 Nov 2026): figures checked by eye on SEC's rendered pages on 8 Nov 2026
(F-5, F-6, F-7, F-12). Run: python3 -m tests.test_anthropic
"""
import glob

from prospectus.flags import run
from prospectus.questions import answer

path = glob.glob("data/2130357/filings/2026-11-02_S-1-A_*.htm")[0]
q = answer(path)
flags = run(path)["flags"]
titles = [f["title"] for f in flags]
conv = next((f for f in flags if "turns into shares" in f["title"]), {})
g, c, d = q["q1_growth"], q["q2_funds_itself"], q["q3_debt"]

CHECKS = [
    ("F-7 revenue 2023-25 ($M)", g["revenue"]["values"], {"2023": 41, "2024": 386, "2025": 4585}),
    ("F-7 revenue nine months", g["revenue_interim"]["values"], {"9M 2025": 2545, "9M 2026": 33242}),
    ("F-12 net loss nine months 2026", c["net_income"]["values"]["9M 2026"], -104039),
    ("F-12 operating cash flow nine months 2026", c["operating_cash_flow"]["values"]["9M 2026"], 6569),
    ("F-12 capex nine months 2026", c["capex"]["values"]["9M 2026"], -925),
    ("F-5 convertible notes 30 Sep 2026", d["debt"]["values"]["Sep 2026"], 130502),
    ("F-5 convertible preferred 30 Sep 2026", d["redeemable_preferred"]["values"]["Sep 2026"], 157510),
    ("F-6 stockholders' deficit 30 Sep 2026", d["equity"]["values"]["Sep 2026"], -149873),
    ("flag: 9M 2026 loss mostly not cash", any("9M 2026 loss is not cash" in t for t in titles), True),
    ("flag: funding converts at the offering", any("turns into shares" in t for t in titles), True),
    ("p. 59: Amazon Notes above the ownership cap stay debt after the IPO", conv.get("stays"), "59"),
    ("flag: Founder LLC 50.1% of the vote", any("50.1%" in t for t in titles), True),
    ("flag: SpaceX contract cancellable on 90 days", any("90 days" in t and "SpaceX" in t for t in titles), True),
]
misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
