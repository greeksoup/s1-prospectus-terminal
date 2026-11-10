"""The five IPO questions, in order, answered from the filing's own statements.

1. Is revenue really growing, across years and by segment?
2. Does the business fund its own growth?
3. Is the debt sane, or do the lenders control it?
4. Does the reported profit show up as cash?
5. Only then: is the price sane?

Every figure carries the printed page it came from. What the filing does not give is
"not disclosed"; what the code could not read is "not read". Nothing is estimated.
"""
import json
import re
import sys
from pathlib import Path

from .tables import read as read_tables

YEAR = re.compile(r"(?:19|20)\d\d")
STATEMENTS = {
    # US titles first; IFRS filers (most F-1s) print "profit or loss" and "financial position", banks
    # often print "financial condition" (Windward Bio, Hometown Financial, Nov 2026)
    "income": re.compile(r"statements? of (?:operations|income|comprehensive (?:loss|income)|(?:consolidated )?"
                         r"profit (?:or|and) loss|loss(?:es)?\b|earnings)|\bincome statements?\b", re.I),
    "cash": re.compile(r"statements? of cash flows?|\bcash flow statements?\b", re.I),
    "balance": re.compile(r"balance sheets?|statements? of financial (?:position|condition)", re.I),
}


# ---------- columns ----------

def periods(table, fy_month="Dec"):
    """Name each column: ('FY', 2025) or ('9M', 2026) etc., from the header text.
    fy_month: the month the company's fiscal year ends (Oura: September)."""
    titles = table.get("columns") or []
    header = " ".join(titles)
    years = []
    for t in titles:
        found = YEAR.findall(t)
        years.append(int(found[-1]) if found else None)
    if not years or any(y is None for y in years):
        return None
    if not re.search(r"Months Ended", header, re.I):
        # a balance sheet dated mid-year ("September 30, 2026") is a snapshot, not a full year
        out = []
        for t, y in zip(titles, years):
            m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November)\s+\d", t)
            out.append((m.group(1)[:3], y) if m and m.group(1)[:3] != fy_month else ("FY", y))
        return out
    interim = re.search(r"(Three|Six|Nine) Months Ended", header, re.I)
    tag = {"three": "3M", "six": "6M", "nine": "9M"}[interim.group(1).lower()] if interim else None
    if interim and not re.search(r"Year Ended", header, re.I):
        return [(tag, y) for y in years]
    out, seen = [], set()
    for y in years:
        # in a table that mixes both, the interim columns repeat a year already shown as a full year
        if interim and (y in seen or out and out[-1][0] == tag):
            out.append((tag, y))
        else:
            out.append(("FY", y))
            seen.add(y)
    return out


def label(period):
    kind, year = period
    return str(year) if kind == "FY" else f"{kind} {year}"


# ---------- finding the statements ----------


INVISIBLE = "\u200b\u200c\u200d\u2060\ufeff\u00a0\u2009\u202f"


def head_lines(text, n):
    """The first n lines of a page that carry any visible character. Some filing agents put empty or
    zero-width lines above a statement's title (Rezera, Nov 2026), so counting raw lines misses it."""
    out = []
    for l in text.split("\n"):
        l = l.strip(INVISIBLE + " \t\r")
        if not l:
            continue
        if out and l[0].islower() and out[-1][-1:].isalpha() and len(out[-1]) < 40:
            out[-1] += l  # a title broken mid-word across two lines: "Consolidat" / "ed Balance Sheets"
            continue
        out.append(l)
        if len(out) == n:
            break
    return out


class Filing:
    def __init__(self, path):
        self.path = Path(path)
        pages_file = self.path.with_suffix(".pages.json")
        if not pages_file.exists():
            from .pages import main as split_pages
            split_pages(path)
        self.pages = json.loads(pages_file.read_text())
        self.layout, self.tables = read_tables(path)
        self.page_text = {p["page"]: p["text"] for p in self.pages if p["page"] != "unnumbered"}
        fy = re.search(r"(?:Fiscal )?Years? Ended\s+(January|February|March|April|May|June|July|August|September|October|November|December)",
                       " ".join(p["text"][:1500] for p in self.pages if p["page"].startswith("F-")))
        self.fy_month = fy.group(1)[:3] if fy else "Dec"

    def statement_groups(self, kind):
        """Runs of F-pages holding one statement: the page titled with it plus the untitled
        pages that continue it. The first run is the audited annual statement."""
        pat = STATEMENTS[kind]
        any_title = re.compile("|".join(p.pattern for p in STATEMENTS.values()) + r"|notes to", re.I)
        fpages = [p for p in self.pages if p["page"].startswith("F-")]
        groups, i = [], 0
        while i < len(fpages):
            head = [l for l in head_lines(fpages[i]["text"], 6) if len(l) < 90]
            index_page = any(re.search(r"^index to|report of independent", l, re.I) for l in head[:3]) \
                and not any(re.search(r"^(?:unaudited |interim |condensed |consolidated |combined )*" + pat.pattern, l, re.I) for l in head[:2])
            if any(pat.search(l) for l in head) and not any(re.search(r"notes to", l, re.I) for l in head) and not index_page:
                group = [fpages[i]["page"]]
                j = i + 1
                while j < len(fpages) and j <= i + 2:
                    nhead = [l for l in head_lines(fpages[j]["text"], 6) if len(l) < 90]
                    same = any(pat.search(l) for l in nhead) and not any(re.search(r"notes to", l, re.I) for l in nhead)
                    if any(any_title.search(l) for l in nhead) and not same:
                        break
                    group.append(fpages[j]["page"])
                    j += 1
                numeric_rows = sum(1 for t in self.tables if t["page"] in group
                                   for r in t["rows"] if any(v is not None for v in r["values"]))
                if numeric_rows >= 5:  # an auditor's report names the statements but holds no numbers
                    groups.append(group)
                i = j
            else:
                i += 1
        return groups

    def interim_tag(self, page):
        """'3M ' etc. when a page sits in the interim (unaudited) financial statements, else ''.
        The interim set starts at the first income statement whose columns are months, not years."""
        if not hasattr(self, "_interim"):
            self._interim = (None, "")
            seq = {p["page"]: p["seq"] for p in self.pages}
            for g in self.statement_groups("income"):
                text = " ".join(self.page_text.get(pg, "")[:800] for pg in g)
                m = re.search(r"(Three|Six|Nine) Months Ended", text, re.I)
                if m and not re.search(r"Year Ended", text, re.I):
                    self._interim = (seq[g[0]], {"three": "3M ", "six": "6M ", "nine": "9M "}[m.group(1).lower()])
                    break
        start, tag = self._interim
        seq = next((p["seq"] for p in self.pages if p["page"] == page), 0)
        return tag if start and seq >= start else ""

    def statement_pages(self, kind):
        return [p for g in self.statement_groups(kind) for p in g]

    def rows(self, pages):
        """Every row on these pages, with the periods of its table (carried forward when a
        statement is split into several blocks on one page)."""
        out, last = [], None
        for t in self.tables:
            if t["page"] not in pages:
                continue
            per = periods(t, self.fy_month)
            if per is None and last is not None:
                per = last
            last = per or last
            for r in t["rows"]:
                vals = r["values"]
                if per and len(vals) == len(per) and any(v is not None for v in vals):
                    out.append({"label": r["label"], "page": t["page"], "series": dict(zip(map(label, per), vals))})
        return out

    def find(self, kind, pattern, annual=False):
        """First row in the statement whose label matches; returns (series, page) or (None, None)."""
        groups = self.statement_groups(kind)
        rx = re.compile(pattern, re.I)
        # the first statement is usually the audited year; some filers print the interim set first
        # (ConnectM, Nov 2026), so an annual search moves on to the next statement when it finds no years
        for pages in (groups if annual else groups[:1]) or [[]]:
            for r in self.rows(pages):
                if rx.search(r["label"]):
                    series = r["series"]
                    if annual:
                        series = {k: v for k, v in series.items() if k.isdigit()}
                    if series and any(v is not None for v in series.values()):
                        return series, r["page"]
        return None, None

    def interim(self, kind, pattern):
        pages = self.statement_pages(kind)
        rx = re.compile(pattern, re.I)
        for r in self.rows(pages):
            if rx.search(r["label"]):
                s = {k: v for k, v in r["series"].items() if not k.isdigit()}
                if s:
                    return s, r["page"]
        return None, None


def fact(series, page, note=""):
    if series is None:
        return {"status": "not read", "note": note}
    return {"values": dict(sorted(series.items())), "page": page, "note": note}


def growth(series):
    years = sorted(k for k in series if k.isdigit())
    out = {}
    for a, b in zip(years, years[1:]):
        if series[a]:
            out[b] = round((series[b] / series[a] - 1) * 100, 1)
    return out


# ---------- the five questions ----------

def q1_growth(f):
    rev, page = f.find("income", r"^(total )?revenues?$|^total net revenues?$|^net revenues?$", annual=True)
    ans = {"revenue": fact(rev, page)}
    if rev is None:
        grp = f.statement_groups("income")
        text = " ".join(f.page_text.get(pg, "")[:1500] for g in grp[:1] for pg in g)
        if grp and not re.search(r"\brevenues?\b|\bnet sales\b|\bsales\b", text, re.I):
            # the income statement was read and carries no revenue line at all (a company before its first sale)
            ans["revenue"] = {"status": "no revenue", "page": grp[0][0],
                              "note": "the income statement has no revenue line: no revenue reported yet"}
    if rev:
        ans["growth_pct"] = growth(rev)
    irev, ipage = f.interim("income", r"^(total )?revenues?$|^net revenues?$")
    if irev:
        ans["revenue_interim"] = fact(irev, ipage)
    ans["segments"] = segments(f)
    return ans


def segments(f):
    """Segment revenue tables: a Revenue row whose column titles name businesses, not dates."""
    out = {}
    for t in f.tables:
        if not t["page"].startswith("F-"):
            continue
        titles = t.get("columns") or []
        names = [re.sub(r"(?:Year|Three|Six|Nine) (?:Months )?Ended.*?,|December 31,|March 31,|June 30,|September 30,"
                        r"|\(unaudited\)|(?:19|20)\d\d|\$|\(?[\d,]+\)?", "", c) for c in titles]
        names = [re.sub(r"\s+", " ", n).strip() for n in names]
        if len(names) < 2 or not all(names) or not re.search(r"segment", " ".join(titles) + t["caption"], re.I):
            continue
        header = " ".join(titles) + " " + t["caption"]
        years = YEAR.findall(" ".join(titles))
        if not years:
            continue
        tag = f.interim_tag(t["page"])
        for r in t["rows"]:
            if re.match(r"^(total )?revenues?$", r["label"], re.I) and len(r["values"]) == len(names):
                year = int(years[0])
                key = tag + str(year)
                while key in out:  # the second table on a page is the earlier period
                    year -= 1
                    key = tag + str(year)
                out[key] = {"page": t["page"], "by_segment": dict(zip(names, r["values"]))}
                break
    return out or {"status": "not disclosed"}


def q2_funds_itself(f):
    ni, p1 = f.find("cash", r"^net (income|loss|income \(loss\)|\(loss\) income)$"
                       r"|^net \(?(?:loss|income)\)?\s*/\s*\(?(?:income|loss|profit)\)?$|^(?:loss|profit|income) for the (?:year|period)$")
    ocf, p2 = f.find("cash", r"^(?:net )?cash (?:flows? )?(?:\(?(?:provided by|used in|generated from|generated by|from|\(used in\)|provided)\)?[\s/,]*(?:and |or )?)+operating activities")
    capex, p3 = f.find("cash", r"^purchases? of property|^capital expenditures|^purchases? of property and equipment")
    fin, pf = f.find("cash", r"^net cash (?:flows? )?(provided by|used in|provided by \(used in\)|\(used in\) provided by|from) financing")
    raised = {}
    for kind_rx in (r"^proceeds from (the )?issuance of (capital|common|preferred|convertible preferred|redeemable)",
                    r"^proceeds from (debt|borrowings|issuance of debt|long-term debt|term loan)"):
        s_, p_ = f.find("cash", kind_rx)
        if s_:
            raised[p_ + ": " + kind_rx] = s_
    ans = {"net_income": fact(ni, p1), "operating_cash_flow": fact(ocf, p2), "capex": fact(capex, p3)}
    if ocf and capex:
        ans["free_cash_flow"] = {"values": {y: ocf[y] + capex[y] for y in ocf if y in capex},
                                 "page": ", ".join(dict.fromkeys([p2, p3])), "note": "derived: operating cash flow less capex"}
    if fin:
        ans["outside_money_net"] = fact(fin, pf, "net cash from financing: what came in from shareholders and "
                                        "lenders after repayments")
    if raised:
        years = set.intersection(*(set(v) for v in raised.values()))
        ans["outside_money_gross"] = {"values": {y: sum(v[y] or 0 for v in raised.values()) for y in sorted(years)},
                                      "page": ", ".join(sorted({k.split(":")[0] for k in raised})),
                                      "note": "derived: proceeds from issuing shares and borrowing, before repayments"}
    return ans


def q3_debt(f):
    cash, p1 = f.find("balance", r"^cash and cash equivalents$")
    if not cash:  # "Cash" alone (SeeQC), with restricted cash, or a bank's "cash and due from banks"
        cash, p1 = f.find("balance", r"^(?:total )?cash(?: and cash equivalents)?(?:,? (?:and )?restricted cash(?: and cash equivalents)?)?(?:, net)?$"
                          r"|^cash and (?:due from banks|amounts due from (?:depository institutions|banks))$|^total cash and cash equivalents$")
    equity, p2 = f.find("balance", r"^total (stockholders|shareholders)[’'] (equity|deficit)|^total (stockholders|shareholders)[’'] equity \(deficit\)"
                         r"|^total (?:stockholders|shareholders)[’'] equity\s*/\s*\(?deficit\)?|^total (?:equity|deficit)$|^total (?:stockholders|shareholders)[’']? (?:equity|deficit)$")
    debt, p3 = f.find("balance", r"^long-term debt|^debt\b.*net of current|^debt, (noncurrent|non-current|long-term)|^(convertible )?notes payable(, net of current.*|, noncurrent)?$")
    debt_cur, p4 = f.find("balance", r"^current portion of (long-term )?debt|^short-term debt|^debt\b[^,]*, current")
    ans = {"cash": fact(cash, p1), "equity": fact(equity, p2)}
    pref, pp = f.find("balance", r"^redeemable convertible preferred stock|^convertible preferred stock")
    assets, _ = f.find("balance", r"^total assets$")
    if pref and assets:
        # a share count printed beside the dollar figure must never be read as dollars
        pref = {k: v for k, v in pref.items() if v is not None and k in assets and assets[k] and abs(v) <= 3 * abs(assets[k])}
    if pref:
        ans["redeemable_preferred"] = fact(pref, pp, "sits between liabilities and equity until it converts")
    debt_label = None
    for r in f.rows(f.statement_groups("balance")[0] if f.statement_groups("balance") else []):
        if re.search(r"^long-term debt|^debt\b|^(convertible )?notes payable", r["label"], re.I):
            debt_label = re.sub(r"\s*\(.*|,\s*(net of )?current.*", "", r["label"])
            break
    total = None
    if debt:
        total = {y: (debt[y] or 0) + ((debt_cur or {}).get(y) or 0) for y in debt}
        ans["debt"] = {"values": total, "page": ", ".join(p for p in (p3, p4) if p),
                       "note": "balance sheet debt, current plus long-term, as labelled in the filing ("
                       + (debt_label or "") + "); operating leases are not included"}
    else:
        ans["debt"] = {"status": "not read"}
    if total and cash:
        ans["net_debt"] = {"values": {y: total[y] - cash[y] for y in total if y in cash}, "note": "derived"}
    if total and equity:
        de = {y: round(total[y] / equity[y], 1) for y in total if y in equity and equity[y] and equity[y] > 0}
        if any(equity[y] < 0 for y in total if y in equity and equity[y] is not None):
            ans["equity_negative"] = {"values": {y: equity[y] for y in equity if equity[y] is not None and equity[y] < 0},
                                      "note": "equity is below zero, so debt to equity has no meaning for these periods"}
        ans["debt_to_equity"] = {"values": de, "note": "derived"}
        ys = sorted(de)
        if len(ys) >= 2:
            a, b = ys[-2], ys[-1]
            debt_move = (total[b] / total[a] - 1) if total[a] else 0
            eq_move = (equity[b] / equity[a] - 1) if equity[a] else 0
            # how much of the ratio's rise came from each side: debt multiplies it, shrinking equity divides it
            debt_factor, eq_factor = 1 + debt_move, (1 / (1 + eq_move)) if eq_move > -1 else float("inf")
            if de[b] > de[a] * 1.5 and eq_move < 0 and eq_factor > debt_factor:
                ans["debt_to_equity"]["warning"] = (
                    f"The ratio rose from {de[a]}x to {de[b]}x. Debt rose {debt_move:+.0%}, but equity fell "
                    f"{eq_move:+.0%}, and the shrinking equity moved the ratio more than the new debt did. "
                    f"Net debt is the better read.")
    ans["maturities"] = maturities(f)
    return ans


def maturities(f):
    """The table of principal due by year: rows named 2026, 2027 ... Thereafter."""
    for t in f.tables:
        if not t["page"].startswith("F-"):
            continue
        labels = [r["label"] for r in t["rows"]]
        yrs = [l for l in labels if re.fullmatch(r"(?:19|20)\d\d", l)]
        if len(yrs) >= 4 and any(re.match(r"thereafter", l, re.I) for l in labels):
            sched = {}
            for r in t["rows"]:
                vals = [v for v in r["values"] if v is not None]
                if (re.fullmatch(r"(?:19|20)\d\d", r["label"]) or re.match(r"thereafter", r["label"], re.I)) and vals:
                    sched[r["label"]] = vals[-1]
            # only the words right above the table: earlier sentences in the caption belong to other things
            context = (t.get("caption") or "")[-110:] + " " + " ".join(t.get("columns") or [])
            if re.search(r"debt|notes|loan|borrowing|principal", context, re.I) and not re.search(r"lease", context, re.I):
                total = sum(sched.values())
                peak = max(sched, key=sched.get)
                return {"page": t["page"], "schedule": sched,
                        "largest_year": peak, "largest_share_pct": round(sched[peak] / total * 100) if total else None}
    return {"status": "not found", "note": "no table of debt principal due by year was found"}


def q4_profit_real(f):
    ni, p1 = f.find("cash", r"^net (income|loss|income \(loss\)|\(loss\) income)$"
                       r"|^net \(?(?:loss|income)\)?\s*/\s*\(?(?:income|loss|profit)\)?$|^(?:loss|profit|income) for the (?:year|period)$")
    ocf, p2 = f.find("cash", r"^(?:net )?cash (?:flows? )?(?:\(?(?:provided by|used in|generated from|generated by|from|\(used in\)|provided)\)?[\s/,]*(?:and |or )?)+operating activities")
    ans = {}
    if ni and ocf:
        ans["gap"] = {"values": {y: ocf[y] - ni[y] for y in ni if y in ocf},
                      "page": ", ".join(dict.fromkeys([p1, p2])), "note": "derived: operating cash flow minus net income. "
                      "Positive means cash came in above the reported profit (the safe direction)."}
    # the non-cash items between net income and the working-capital heading, in printed order
    groups = f.statement_groups("cash")
    pages = groups[0] if groups else []
    adj, inside, per = [], False, None
    for t in f.tables:
        if t["page"] not in pages:
            continue
        per = periods(t, f.fy_month) or per
        for r in t["rows"]:
            if re.match(r"^net (income|loss)", r["label"], re.I):
                inside = True
                continue
            if inside and re.match(r"^changes in (operating )?assets|^net cash", r["label"], re.I):
                inside = None
                break
            if inside and per and len(r["values"]) == len(per) and any(v for v in r["values"]):
                vals = {label(k): v for k, v in zip(per, r["values"])}
                if vals:
                    adj.append({"label": r["label"], "page": t["page"], "values": vals})
        if inside is None:
            break
    if adj:
        adj.sort(key=lambda a: -max(abs(v or 0) for v in a["values"].values()))
        ans["largest_non_cash_items"] = {"note": "ranked by their largest size in any year", "items": adj[:5]}
    return ans or {"status": "not read"}


def q5_price(f):
    cover = "\n".join(p["text"] for p in f.pages[:6])
    ans = {}
    m = re.search(r"between\s*\$\s*(\d+(?:\.\d+)?)\s*and\s*\$\s*(\d+(?:\.\d+)?)", cover)
    flat = re.sub(r"\s+", " ", cover)
    # "initial public offering price is $135.00 per share", "... price per share of our Class A common
    # stock is $185.00", or the 424B4 cover line "PRICE $185.00 A SHARE"
    fixed = (re.search(r"public offering price(?: per share)?(?: of (?:our|the) [\w ]+?stock)? (?:is|of) \$\s?(\d+(?:\.\d+)?)", flat)
             or re.search(r"\bPRICE \$\s?(\d+(?:\.\d+)?) (?:A|PER) SHARE\b", flat))
    if fixed:
        ans["price"] = {"value": float(fixed.group(1)), "note": "set in this filing"}
    elif m:
        ans["price_range"] = {"low": float(m.group(1)), "high": float(m.group(2))}
    elif re.search(r"between\s*\$\s*and\s*\$|price per share will be between\s*\$", cover.replace("\n", " ")):
        ans["price"] = {"status": "not disclosed",
                        "note": "the price fields are blank in this filing; multiples cannot be computed yet"}
    else:
        ans["price"] = {"status": "not read"}
    votes = re.search(r"(\d{1,2}(?:\.\d+)?)\s*votes? per share", " ".join(p["text"] for p in f.pages[:60]))
    if votes:
        ans["votes_per_share_high_class"] = votes.group(1)
    return ans


def answer(path):
    f = Filing(path)
    return {
        "filing": f.path.name,
        "layout": f.layout,
        "q1_growth": q1_growth(f),
        "q2_funds_itself": q2_funds_itself(f),
        "q3_debt": q3_debt(f),
        "q4_profit_real": q4_profit_real(f),
        "q5_price": q5_price(f),
    }


def main(path):
    out = Path(path).with_suffix(".questions.json")
    result = answer(path)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2)[:6000])
    return out


if __name__ == "__main__":
    main(sys.argv[1])
