"""SpaceX S-1 (20 May 2026): the five questions must reproduce the June edition's checked answers.
Differences from June are listed on purpose, never hidden. Run: python3 -m tests.test_spacex_questions
"""
import glob

from prospectus.questions import answer

q = answer(glob.glob("data/1181412/filings/2026-05-20_S-1_*.htm")[0])
g, c, d, p, v = q["q1_growth"], q["q2_funds_itself"], q["q3_debt"], q["q4_profit_real"], q["q5_price"]

CHECKS = [
    ("Q1 revenue 2023-25", g["revenue"]["values"], {"2023": 10387, "2024": 14015, "2025": 18674}),
    ("Q1 Connectivity 2025", g["segments"]["2025"]["by_segment"]["Connectivity"], 11387),
    ("Q1 AI 2023 (partly old X income)", g["segments"]["2023"]["by_segment"]["AI"], 2961),
    ("Q1 Q1-2026 segments tagged as three months", "3M 2026" in g["segments"], True),
    ("Q2 free cash flow", c["free_cash_flow"]["values"], {"2023": 105, "2024": -5387, "2025": -13952}),
    ("Q2 net financing 2025 (June: $26.4B)", c["outside_money_net"]["values"]["2025"], 26350),
    ("Q3 cash 2025", d["cash"]["values"]["2025"], 24747),
    ("Q3 equity 2024 -> 2025", d["equity"]["values"], {"2024": 4863, "2025": 2573}),
    ("Q3 net debt negative 2025", d["net_debt"]["values"]["2025"] < 0, True),
    ("Q3 shrinking-equity warning fires", "warning" in d["debt_to_equity"], True),
    ("Q3 2029 share of maturities (June: 61%)", d["maturities"]["largest_share_pct"], 61),
    ("Q4 cash above profit 2025 (June: >$11B)", p["gap"]["values"]["2025"], 11722),
    ("Q4 2023 writedown found (June: $3.8B)", any(i["values"].get("2023") == 3775
                                                  for i in p["largest_non_cash_items"]["items"]), True),
    ("Q5 price not disclosed", v["price"]["status"], "not disclosed"),
    ("Q5 high-vote class (June: ten votes)", v["votes_per_share_high_class"], "10"),
]
# Known, stated difference: June's debt to equity of 9.5x included operating leases; the program shows
# debt and finance leases only (8.9x) and says so on screen.

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
