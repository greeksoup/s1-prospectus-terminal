"""Other filings that name this company: the other side of its contracts, and the funds that
already own it.

A prospectus is the company describing itself. Its suppliers, customers, partners and investors
describe it too, in their own filings, under their own lawyers. SEC's full-text search finds them;
code reads the sentences that carry a number. No AI.
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from .fetch import DATA, get

COMPANY_FORMS = ["10-K", "10-Q", "8-K", "S-1", "S-1/A", "424B4", "20-F", "6-K", "F-1"]
SEARCH = "https://efts.sec.gov/LATEST/search-index?q={q}&forms={form}&dateRange=custom&startdt={start}&enddt={end}"


def search(term, form, start, end):
    url = SEARCH.format(q=urllib.parse.quote(f'"{term}"'), form=urllib.parse.quote(form), start=start, end=end)
    return json.loads(get(url))["hits"]["hits"]


def doc_url(hit):
    adsh, filename = hit["_id"].split(":", 1)
    cik = int(hit["_source"]["ciks"][0])
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{filename}"


def _text(html):
    from bs4 import BeautifulSoup
    t = BeautifulSoup(html, "html.parser").get_text(" ")
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"\s+([’'),.;:])", r"\1", t)


def _table_like(s):
    """Text lifted out of a table: mostly digits, dollar signs and underscores rather than words."""
    letters = sum(ch.isalpha() for ch in s)
    return letters < 0.55 * len(s) or s.count("$") > 4 or "___" in s


def mentions(text, term, limit=4):
    """Sentences that name the company, those with a dollar figure or percentage first. A mention
    inside a table becomes a short clip around the name, labelled as a table entry."""
    out = []
    for s in re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", text):
        i = s.lower().find(term.lower())
        if i < 0 or not (40 < len(s) < 1500):
            continue
        if _table_like(s):
            clip = re.sub(r"\s+", " ", s[max(0, i - 60): i + len(term) + 90]).strip()
            out.append("[table entry] …" + clip + "…")
        elif len(s) < 900:
            out.append(s.strip())
    out.sort(key=lambda s: (s.startswith("[table"), 0 if re.search(r"\$\s?[\d,.]+\s*(billion|million)|\d+(\.\d+)?%", s) else 1, -len(s)))
    return list(dict.fromkeys(out))[:limit]


RELATION = re.compile(r"agreement|contract|lease|invest|customer|supplier|purchase|commit|settlement|notes?\b|"
                      r"preferred stock|revenue from|pay(?:s|ment)|backstop|warrant|loan|credit", re.I)
MONEY = re.compile(r"\$\s?[\d,.]+\s*(billion|million)", re.I)


def relation_score(quotes):
    """A business relationship (money next to a contract word) outranks a name in a list of competitors."""
    return sum(2 if (MONEY.search(q) and RELATION.search(q)) else 1 if RELATION.search(q) else 0 for q in quotes)


def companies(term, own_cik, start, end, max_read=20, keep=10):
    by = {}
    for form in COMPANY_FORMS:
        for h in search(term, form, start, end):
            s = h["_source"]
            cik = int(s["ciks"][0])
            if cik == own_cik:
                continue
            name = re.sub(r"\s+\(CIK \d+\)", "", s["display_names"][0]).strip()
            by.setdefault(cik, {"name": name, "cik": cik, "filings": []})["filings"].append(
                {"form": s["form"], "date": s["file_date"], "url": doc_url(h)})
    pool = sorted(by.values(), key=lambda c: (-len(c["filings"]), c["name"]))[:max_read]
    for c in pool:
        c["filings"].sort(key=lambda f: f["date"], reverse=True)
        # read the newest report (10-Q/10-K/S-1 say more than an 8-K cover)
        best = next((f for f in c["filings"] if f["form"] in ("10-Q", "10-K", "S-1", "S-1/A", "424B4", "20-F")),
                    c["filings"][0])
        try:
            c["quotes"] = mentions(_text(get(best["url"]).decode("utf-8", "ignore")), term)
            c["read"] = best
        except Exception as e:  # one unreadable filing never stops the rest
            c["quotes"], c["read"] = [], {"error": str(e), **best}
        c["count"] = len(c["filings"])
        c["score"] = relation_score(c["quotes"])
        c["relationship"] = c["score"] >= 2
        c["filings"] = c["filings"][:5]
    pool.sort(key=lambda c: (-c["score"], -c["count"]))
    return pool[:keep]


def fund_marks(term, start, end, max_funds=8):
    """Funds report every holding each quarter (Form N-PORT), with the value they put on it.
    Before an IPO, that is the only outside price on record."""
    hits = [h for h in search(term, "NPORT-P", start, end) if h["_id"].endswith(".xml")]
    hits.sort(key=lambda h: h["_source"]["file_date"], reverse=True)
    marks, seen = [], set()
    for h in hits:
        fund = re.sub(r"\s+\(CIK \d+\)", "", h["_source"]["display_names"][0]).strip()
        if fund in seen:
            continue
        seen.add(fund)
        try:
            root = ET.fromstring(get(doc_url(h)))
        except Exception:
            continue
        ns = {"n": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {"n": ""}
        period = root.findtext(".//n:repPdDate", default="", namespaces=ns) if ns["n"] else ""
        for sec in root.iter():
            if not sec.tag.endswith("invstOrSec"):
                continue
            name = next((x.text for x in sec if x.tag.endswith("title") and x.text), None) or \
                next((x.text for x in sec if x.tag.endswith("name") and x.text), "")
            if term.lower() not in name.lower():
                continue
            val = lambda tag: next((x.text for x in sec if x.tag.endswith(tag)), None)
            bal, usd, units = val("balance"), val("valUSD"), val("units")
            try:
                bal, usd = float(bal), float(usd)
            except (TypeError, ValueError):
                continue
            marks.append({"fund": fund, "filed": h["_source"]["file_date"], "period": period, "holding": name.strip(),
                          "units": units, "balance": bal, "value_usd": usd,
                          "per_unit": round(usd / bal, 2) if bal and units == "NS" else None,
                          "url": doc_url(h)})
        if len(seen) >= max_funds:
            break
    return {"funds_found": len({h["_source"]["display_names"][0] for h in hits}), "marks": marks}


def run(index_path, start="2025-01-01", end=None):
    from datetime import date
    index = json.loads(Path(index_path).read_text())
    end = end or date.today().isoformat()
    term = re.sub(r",?\s+(PBC|Inc\.?|Corp\.?|Corporation|LLC|Ltd\.?|Holdings?)\b.*$", "",
                  re.sub(r"\s*\(.*?\)\s*", " ", index["name"])).strip()
    if term.isupper():
        term = term.title()
    return {"term": term, "companies": companies(term, index["cik"], start, end),
            "funds": fund_marks(term, start, end)}


def main(index_path):
    result = run(index_path)
    out = Path(index_path).with_name("others.json")
    out.write_text(json.dumps(result, indent=2))
    print(f"term: {result['term']}")
    for c in result["companies"]:
        print(f"  {c['count']:>3}  score {c['score']}  {c['name']}")
        for q in c["quotes"][:2]:
            print("       “" + q[:220] + "”")
    print(f"funds: {result['funds']['funds_found']} filers; marks read: {len(result['funds']['marks'])}")
    for m in result["funds"]["marks"][:10]:
        print(f"  {m['fund'][:40]:<40} {m['period']}  {m['holding'][:40]:<40} ${m['value_usd']:,.0f}  per unit {m['per_unit']}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
