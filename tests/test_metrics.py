"""prospectus/metrics.py against figures read by eye from each filing's page text on 8 Nov 2026.
Anthropic S-1/A (pp. 24, 160, 173), SpaceX 424B4 (p. 24, F-46, F-53), Cerebras 424B4 (pp. 104, 108, F-33),
Oura S-1/A (pp. 98, 109, 111). Run: python3 -m tests.test_metrics
"""
import glob

from prospectus.metrics import run

ANT = run(glob.glob("data/2130357/filings/2026-11-02_S-1-A_*.htm")[0])
SPX = run(glob.glob("data/1181412/filings/2026-06-12_424B4_*.htm")[0])
CBR = run(glob.glob("data/2021728/filings/*424B4*.htm")[-1])
OURA = run(glob.glob("data/2133022/filings/2026-09-21_S-1-A_*.htm")[0])


def q(d, label, col):
    return next((r["values"].get(col) for r in d["quarterly"].get("rows", []) if r["label"] == label), None)


def kpi(d, label, col):
    return next((k["values"][col] for k in d["key_metrics"] if k["label"] == label and col in k["values"]), None)


CHECKS = [
    ("ANT p160 seven quarters", len(ANT["quarterly"].get("columns", [])), 7),
    ("ANT p160 revenue Mar 2025 (oldest left)", ANT["quarterly"]["rows"][0]["values"].get("Mar 2025"), 376.0),
    ("ANT p160 revenue Sep 2026", q(ANT, "Revenue", "Sep 2026"), 16956.0),
    ("ANT p173 contractual obligations total", ANT["commitments"].get("total"), 319993.0),
    ("ANT p173 2027 obligations", ANT["commitments"]["by_year"].get("2027"), 29165.0),
    ("ANT p24 unrecognized SBC (24.1 + 2.1 $B)", ANT["sbc"]["unrecognized"], 26200.0),
    ("SPX no quarterly table", "status" in SPX["quarterly"], True),
    ("SPX F-53 commitments 2027", SPX["commitments"]["by_year"].get("2027"), 21476.0),
    ("SPX F-53 commitments total", SPX["commitments"].get("total"), 25451.0),
    ("SPX F-46 unrecognized SBC and years", (SPX["sbc"]["unrecognized"], SPX["sbc"]["recognition_years"]), (4842.0, 3.2)),
    ("SPX p24 Starlink subscribers 3M 2026 (millions)", kpi(SPX, "Starlink Subscribers", "3M 2026"), 10.3),
    ("SPX p24 launches 2025", kpi(SPX, "Launches", "2025"), 170.0),
    ("CBR p104 eight quarters", len(CBR["quarterly"].get("columns", [])), 8),
    ("CBR p104 total revenue Dec 2025", q(CBR, "Total revenue", "Dec 2025"), 171.443),
    ("CBR p108 purchase commitments 2026", CBR["commitments"]["by_year"].get("2026"), 4.1),
    ("CBR F-33 unrecognized options in the total", any(b["amount"] == 33.2 for b in CBR["sbc"].get("built_from", [])), True),
    ("OURA p109 total revenue Jun 2026", q(OURA, "Total revenue", "Jun 2026"), 408.724),
    ("OURA p109 newest quarter on the right", OURA["quarterly"]["columns"][-1], "Jun 2026"),
    ("OURA p111 Rings Sold Jun 2026 (million)", kpi(OURA, "Rings Sold", "Jun 2026"), 1.0),
    ("OURA p98 Paid Members 9M 2026 (million)", kpi(OURA, "Paid Members", "9M 2026"), 5.0),
]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
