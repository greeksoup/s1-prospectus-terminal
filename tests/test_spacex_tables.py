"""SpaceX S-1 (20 May 2026): the table reader must reproduce the figures our June edition
checked by hand (output/spacex/2026-Q2/01-05 in the vault). Run: python3 -m tests.test_spacex_tables
"""
import glob
import re

from prospectus.tables import read

FILING = glob.glob("data/1181412/filings/2026-05-20_S-1_*.htm")[0]

# (page, row label starts with, values as printed, $ millions)
EXPECTED = [
    ("F-5", "Revenue", [18674, 14015, 10387]),
    ("F-5", "Net income (loss)", [-4937, 791, -4628]),
    ("F-8", "Net cash provided by operating activities", [6785, 5776, 4520]),
    ("F-8", "Purchases of property, plant, and equipment", [-20737, -11163, -4415]),
    ("F-57", "Revenue", [4086, 11387, 3201, 18674]),            # Space, Connectivity, AI, total, 2025
    ("F-57", "Capital expenditures", [3832, 4178, 12727, 20737]),
    ("F-58", "Revenue", [3796, 7599, 2620, 14015]),             # 2024
    ("F-58", "Revenue", [3557, 3869, 2961, 10387]),             # 2023
    ("F-33", "2029", [13539]),                                  # the maturity wall
]


def main():
    _, tables = read(FILING)
    found = {}
    for page, label, want in EXPECTED:
        rows = [r for t in tables if t["page"] == page for r in t["rows"]
                if r["label"].startswith(label)]
        got = None
        for r in rows:
            vals = [v for v in r["values"] if v is not None]
            if vals == want and (page, label, tuple(want)) not in found:
                got = vals
                found[(page, label, tuple(want))] = True
                break
        status = "ok  " if got else "MISS"
        print(f"{status} {page:<5} {label:<45} {want}")
        if not got:
            print("      read instead:", [r["values"] for r in rows][:3])
    misses = len(EXPECTED) - len(found)
    print(f"\n{len(EXPECTED) - misses}/{len(EXPECTED)} match")
    return misses


if __name__ == "__main__":
    raise SystemExit(main())
