"""Seventeen filings added on 10 Nov 2026 to test "any company", after Rezera Inc. showed most screens
empty. Each check below is one layout the program could not read that day, with the value checked in the
printed page text the same day. Run (needs the filings in data/, fetched by adding each company):

    python3 -m tests.test_filers
"""
import glob

from prospectus import pages as pg
from prospectus import qual, shares
from prospectus.questions import Filing, q1_growth, q2_funds_itself, q3_debt
from prospectus.statements import run as statements


def latest(cik):
    files = sorted(glob.glob(f"data/{cik}/filings/*.htm"))
    return files[-1] if files else None


def cash(cik, year):
    return (q3_debt(Filing(latest(cik)))["cash"].get("values") or {}).get(year)


def after(cik):
    return shares.run(latest(cik))["outstanding_after"].get("total")


def kind(cik):
    return qual.filing_kind(qual.Doc(latest(cik)))["kind"]


def row(cik, stmt, label, col):
    for r in statements(latest(cik))[stmt].get("rows", []):
        if r["label"].lower().startswith(label.lower()):
            return r["values"].get(col)


def execs(cik):
    e = qual.people(qual.Doc(latest(cik)))["executives"]
    return [x["name"] for x in e] if isinstance(e, list) else []


CHECKS = [
    # IFRS titles ("Statement of Profit or Loss", "Financial Position"), a NOTES column, a from-to period
    ("Windward Bio: IFRS balance sheet, cash 2025 (F-4: 19,758)", lambda: cash("2145089", "2025"), 19.758),
    ("Windward Bio: income statement past the index page, R&D 2025 (F-3: 32,592)",
     lambda: row("2145089", "income", "Research and development", "2025"), -32.592),
    # whole Singapore dollars, a column of note numbers, a US$ copy of the last year
    ("Focus Media: currency kept as SGD", lambda: statements(latest("2123920")).get("currency"), "SGD"),
    ("Focus Media: cash 2026 in whole SGD (F-3: 1,136,237)", lambda: cash("2123920", "2026"), 1.136237),
    ("Focus Media: revenue 2026 (F-4: 4,634,587)", lambda: row("2123920", "income", "Revenue", "2026"), 4.634587),
    ("Focus Media: 'Mr.' on its own line joined to the name", lambda: "Mr. Liu Chun Hung Clement" in execs("2123920"), True),
    ("Focus Media: 'Ordinary Shares' outstanding after (p. 8: 20,000,000)", lambda: after("2123920"), 20000000),
    # a bank: financial pages numbered 1, 2, 3 after the text, a title broken mid-word, cash and due from banks
    ("Hometown Financial: bank statement pages found (printed 3, labelled F-3)", lambda: Filing(latest("2152644")).statement_groups("balance")[:1], [["F-3"]]),
    ("Hometown Financial: cash and due from banks 2026 (F-3: 370,279)", lambda: cash("2152644", "2026"), 370.279),
    ("Hometown Financial: labelled a mutual conversion", lambda: kind("2152644"), "mutual conversion"),
    ("MFB Bancorp: bold-only risk headings read", lambda: len(qual.risk_headings(qual.Doc(latest("2152813")))) >= 40, True),
    # an XML declaration line, "Cash" alone, management table on the page before the section
    ("SeeQC: cash labelled 'Cash' (F-3: 27,967)", lambda: cash("1779977", "2025"), 27.967),
    ("SeeQC: risk headings read despite the XML line", lambda: (qual.risks(qual.Doc(latest("1779977"))) or {}).get("count", 0) > 50, True),
    ("SeeQC: executives from the page before the section", lambda: execs("1779977")[:1], ["John Levy"]),
    # whole US dollars with no unit printed, "Common Stock" with a capital S
    ("Simwon America: cash 2026 in whole dollars (F-3: 39,430,946)", lambda: cash("1698506", "2026"), 39.430946),
    ("Simwon America: shares after (p. 7: 14,750,000)", lambda: after("1698506"), 14750000),
    # interim statements printed before the annual ones
    ("ConnectM: annual revenue found after the interim set (F-53: 33,072,261)",
     lambda: (q1_growth(Filing(latest("1895249")))["revenue"].get("values") or {}).get("2025"), 33.072261),
    ("ConnectM: shares after (p. 13: 9,638,074)", lambda: after("1895249"), 9638074),
    # page numbers carried by a page-break-after paragraph: each page keeps its own number
    ("Alopexx: page 58 ends with its own number", lambda: [p for p in pg.split(latest("1880995")) if p["page"] == "58"][0]["text"].split("\n")[-1].strip(), "58"),
    ("Alopexx: shares after, a (1) mark before the number (p. 8: 8,299,557)", lambda: after("1880995"), 8299557),
    ("LIS Technologies: names and titles spread over lines", lambda: execs("1973276")[:2], ["Jay Jiang Yu", "Christo J. Liebenberg"]),
    ("LIS Technologies: 'Completion of This Offering' (p. 13: 74,711,408)", lambda: after("1973276"), 74711408),
    ("Holvek: officer who is also the director", lambda: [d["name"] for d in qual.people(qual.Doc(latest("2161470")))["directors"]], ["Tomas Dragun"]),
    ("Holvek: 'outstanding after the offering: 6,500,000'", lambda: after("2161470"), 6500000),
    ("Blue Laser Fusion: labelled a resale", lambda: kind("1938570"), "resale"),
    ("Evaxion: labelled a short-form filing", lambda: kind("1828253"), "short form"),
    ("Rezera: still an IPO", lambda: kind("2141583"), "ipo"),
]

if __name__ == "__main__":
    ok = 0
    for name, fn, want in CHECKS:
        try:
            got = fn()
        except Exception as e:  # noqa: BLE001
            got = f"{type(e).__name__}: {e}"
        good = got == want
        ok += good
        print(("ok   " if good else "FAIL ") + f"{name}: {got!r}" + ("" if good else f" (want {want!r})"))
    print(f"\n{ok}/{len(CHECKS)} match")
    raise SystemExit(0 if ok == len(CHECKS) else 1)
