"""Rezera Inc. S-1/A (9 Nov 2026, filing agent 0001104659). Its pages put zero-width characters in every
empty cell and above each statement title, and the first build (10 Nov 2026) read no statements at all,
so most of the dashboard was empty. Every expected value below was checked in the printed page text on
10 Nov 2026 (pages 9, F-3, F-4, F-6, F-31, 133). Run: python3 -m tests.test_rezera
"""
import glob

from prospectus.qual import Doc, people, principal_holders
from prospectus.questions import Filing, q1_growth
from prospectus.statements import run as statements

PATH = sorted(glob.glob("data/2141583/filings/*_S-1-A_0001104659-26-124074.htm"))[-1]
f = Filing(PATH)
st = statements(PATH)
ppl = people(Doc(PATH))
holders, _ = principal_holders(Doc(PATH))


def row(kind, label, col):
    for r in st[kind].get("rows", []):
        if r["label"].lower().startswith(label.lower()):
            return r["values"].get(col)
    return None


CHECKS = [
    ("income statement pages found", f.statement_groups("income")[:1], [["F-4", "F-5"]]),
    ("balance sheet pages found", f.statement_groups("balance")[:1], [["F-3"]]),
    ("cash flow pages found", f.statement_groups("cash")[:1], [["F-6"]]),
    ("R&D 2025, $M (F-4: 31,369)", row("income", "Research and development", "2025"), 31.369),
    ("total operating expenses 2025 (F-4: 40,991)", row("income", "Total operating expenses", "2025"), 40.991),
    ("R&D six months 2026 (F-31: 19,855)", row("income", "Research and development", "6M 2026"), 19.855),
    ("cash 2025 (F-3: 28,589)", row("balance", "Cash and cash equivalents", "2025"), 28.589),
    ("cash 2024 (F-3: 11,391)", row("balance", "Cash and cash equivalents", "2024"), 11.391),
    ("net loss 2025 (F-6: (42,179))", row("cashflow", "Net loss", "2025"), -42.179),
    ("no row label is blank", any(not r["label"].strip() for k in ("income", "balance", "cashflow")
                                  for r in st[k].get("rows", [])), False),
    ("no revenue yet, said plainly", q1_growth(f)["revenue"].get("status"), "no revenue"),
    ("executives read (p. 133)", len(ppl["executives"]), 5),
    ("chief executive (p. 133)", ppl["executives"][0]["name"], "Geoffrey McDonough, M.D."),
    ("directors read, accented name kept (p. 133)", "Elisabeth Björk, Ph.D." in [d["name"] for d in ppl["directors"]], True),
    ("footnote stars dropped from names", any("*" in d["name"] for d in ppl["directors"]), False),
    ("ownership table read, 5AM Ventures (p. 160: 479,643; 11.56%; 2.31%)",
     holders[0]["classes"].get("Common stock") if isinstance(holders, list) else holders,
     {"shares": 479643, "shares_after": None, "pct_before": 11.56, "pct_after": 2.31}),
]

if __name__ == "__main__":
    ok = 0
    for name, got, want in CHECKS:
        good = got == want
        ok += good
        print(("ok   " if good else "FAIL ") + f"{name}: {got!r}" + ("" if good else f" (want {want!r})"))
    print(f"\n{ok}/{len(CHECKS)} match")
    raise SystemExit(0 if ok == len(CHECKS) else 1)
