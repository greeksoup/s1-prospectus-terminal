"""The three primary statements, every printed row (prospectus/statements.py).
Anthropic figures checked by eye on SEC's rendered S-1/A pages (F-5, F-6, F-7, F-12) on 8 Nov 2026;
the other three filings get a sanity check: each statement read with at least 8 rows, or an honest
"not read". Run: python3 -m tests.test_statements
"""
import json

from prospectus.fetch import filing_path
from prospectus.statements import run


def newest(cik):
    return filing_path(json.load(open(f"data/{cik}/filings.json"))["filings"][-1]["path"])


def row(st, label, period):
    """The value printed for this row and period."""
    for r in st.get("rows", []):
        if r["label"] == label:
            return r["values"].get(period)
    return f"no row {label!r}"


a = run(newest(2130357))
inc, bal, cf = a["income"], a["balance"], a["cashflow"]
CHECKS = [
    ("Anthropic income statement is on F-7", inc.get("pages"), ["F-7"]),
    ("F-7 revenue 2023-25", [row(inc, "Revenue", y) for y in ("2023", "2024", "2025")], [41, 386, 4585]),
    ("F-7 revenue nine months", [row(inc, "Revenue", y) for y in ("9M 2025", "9M 2026")], [2545, 33242]),
    ("F-7 columns oldest left, annual then interim", inc.get("columns"), ["2023", "2024", "2025", "9M 2025", "9M 2026"]),
    ("F-7 net loss nine months 2026", row(inc, "Net loss", "9M 2026"), -104039),
    ("F-7 'Operating expenses' is a heading", next(r["kind"] for r in inc["rows"] if r["label"] == "Operating expenses"), "header"),
    ("F-7 per-share row keeps its unit", next(r.get("unit") for r in inc["rows"] if r["label"].startswith("Net loss per share")), "per share"),
    ("F-7 loss per share 9M 2026 not rescaled", next(r["values"]["9M 2026"] for r in inc["rows"] if r["label"].startswith("Net loss per share")), -50.10),
    ("Anthropic cash flow statement is on F-12, F-13", cf.get("pages"), ["F-12", "F-13"]),
    ("F-12 operating cash flow nine months 2026", row(cf, "Net cash provided by (used in) operating activities", "9M 2026"), 6569),
    ("F-12 capex nine months 2026", row(cf, "Purchases of property and equipment", "9M 2026"), -925),
    ("F-12 net loss starts the cash flow", next(r["label"] for r in cf["rows"] if r["kind"] != "header"), "Net loss"),
    ("Anthropic balance sheet is on F-5, F-6", bal.get("pages"), ["F-5", "F-6"]),
    ("F-5 convertible notes 30 Sep 2026", row(bal, "Convertible notes payable", "Sep 2026"), 130502),
    ("F-5 convertible preferred 30 Sep 2026",
     next(r["values"]["Sep 2026"] for r in bal["rows"] if r["label"].startswith("Redeemable convertible preferred stock")), 157510),
    ("F-6 stockholders' deficit 30 Sep 2026", row(bal, "Total stockholders’ deficit", "Sep 2026"), -149873),
    ("F-5 total assets 30 Sep 2026", row(bal, "Total assets", "Sep 2026"), 154320),
    ("F-5 total assets is a total", next(r["kind"] for r in bal["rows"] if r["label"] == "Total assets"), "total"),
    ("no auditor or notes text in any row", any("accompanying notes" in r["label"].lower() or "opinion" in r["label"].lower()
                                                for s in (inc, bal, cf) for r in s["rows"]), False),
]

for name, cik in (("SpaceX", 1181412), ("Cerebras", 2021728), ("Oura", 2133022), ("Anthropic", 2130357)):
    out = a if cik == 2130357 else run(newest(cik))
    for kind in ("income", "balance", "cashflow"):
        st = out[kind]
        ok = st.get("status") == "not read" or (len(st["rows"]) >= 8 and st["columns"]
                                                and all(set(r["values"]) == set(st["columns"]) for r in st["rows"]))
        CHECKS.append((f"{name} {kind}: {st.get('status') or str(len(st['rows'])) + ' rows on ' + ', '.join(st['pages'])}",
                       ok, True))

# Oura reports in thousands with a September year: dollars must arrive in millions
o = run(newest(2133022))
CHECKS.append(("Oura total assets 30 Sep 2025 in $M", row(o["balance"], "Total assets", "2025"), 1403.214))
CHECKS.append(("Oura total assets 30 Jun 2026 in $M", row(o["balance"], "Total assets", "Jun 2026"), 1063.188))
CHECKS.append(("Oura income from operations FY2025 in $M", row(o["income"], "Income from operations", "2025"), 45.332))

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
