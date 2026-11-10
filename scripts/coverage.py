"""Which parts of each built dashboard came out empty. Run after adding companies:

    python3 scripts/coverage.py            # every company in library/
    python3 scripts/coverage.py rezera-inc # one

Prints one row per company: each core part is ok, or the reason it is empty. A part that is empty
because the filing itself leaves it blank (a price before the range is set) is marked "blank in filing",
which is fine; "NOT READ" is the program failing and needs a fix.
"""
import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "library"


def state(v):
    if v is None:
        return "NOT READ"
    if isinstance(v, list):
        return "ok" if v else "empty"
    if isinstance(v, dict):
        s = str(v.get("status", "")).lower()
        if not s:
            return "ok"
        if "blank" in s or "not printed" in s or s in ("not disclosed", "no revenue", "incorporated by reference"):
            return s
        return "NOT READ" if "not read" in s else s
    return "ok"


def parts(d):
    q, st, ql, sh = d.get("q", {}), d.get("statements", {}), d.get("qual", {}), d.get("shares", {})
    return {
        "income": state(st.get("income")),
        "balance": state(st.get("balance")),
        "cashflow": state(st.get("cashflow")),
        "revenue": state(q.get("q1_growth", {}).get("revenue")),
        "op cash": state(q.get("q2_funds_itself", {}).get("operating_cash_flow")),
        "cash": state(q.get("q3_debt", {}).get("cash")),
        "net income": state(q.get("q2_funds_itself", {}).get("net_income")),
        "equity": state(q.get("q3_debt", {}).get("equity")),
        "executives": state(ql.get("people", {}).get("executives")),
        "directors": state(ql.get("people", {}).get("directors")),
        "holders": state(ql.get("owners", {}).get("principal_holders")),
        "offer": state(ql.get("offer", {}).get("shares_offered")),
        "shares after": state(sh.get("outstanding_after")),
        "risks": "ok" if isinstance(ql.get("risks", {}).get("count"), int) else "NOT READ",
    } | ({k: "incorporated by reference" for k in ("revenue", "op cash", "cash", "net income", "equity")}
         if st.get("income", {}).get("status") == "incorporated by reference" else {}) \
      | ({"holders": "none: mutual conversion", "shares after": "range: mutual conversion"}
         if (ql.get("kind") or {}).get("kind") == "mutual conversion" else {}) \
      | ({"shares after": "none: resale"} if (ql.get("kind") or {}).get("kind") == "resale" else {}) \
      | ({k: "short form: incorporated by reference" for k in ("executives", "directors", "holders", "shares after", "risks", "offer")}
         if (ql.get("kind") or {}).get("kind") == "short form" else {})


def main(names):
    files = [LIB / f"{n}.json" for n in names] if names else sorted(LIB.glob("*.json"))
    bad = 0
    for f in files:
        d = json.loads(f.read_text())
        p = parts(d)
        fails = [k for k, v in p.items() if v == "NOT READ" or v == "not found"]
        bad += bool(fails)
        print(f"{d['meta']['name'][:34]:34}  {'all core parts read' if not fails else 'EMPTY: ' + ', '.join(fails)}")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if main(sys.argv[1:]) else 0)
