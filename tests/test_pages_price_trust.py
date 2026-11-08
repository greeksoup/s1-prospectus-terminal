"""Round 3 fixes, checked against the page text on 8 Nov 2026:
- every printed page comes out once, in order (Anthropic's landscape ownership pages 293 to 295 were lost);
- the Cerebras 424B4 price ("PRICE $185.00 A SHARE") reaches question 5;
- trust flags fire on statements of fact only.
Run: python3 -m tests.test_pages_price_trust
"""
import glob
import json
from pathlib import Path

from prospectus.flags import Filing, trust
from prospectus.pages import fill_between
from prospectus.questions import answer


def latest(cik, form):
    return sorted(glob.glob(f"data/{cik}/filings/*_{form}_*.htm"))[-1]


ANT, SPX, CBR, OURA = latest("2130357", "S-1-A"), latest("1181412", "424B4"), latest("2021728", "424B4"), latest("2133022", "S-1-A")


def pages(path):
    return json.loads(Path(path).with_suffix(".pages.json").read_text())


def numbered_gaps(path):
    ints = [int(p["page"]) for p in pages(path) if p["page"].isdigit()]
    return sorted(set(range(1, max(ints) + 1)) - set(ints)), len(ints) != len(set(ints))


def page_text(path, number):
    return next((p["text"] for p in pages(path) if p["page"] == number), "")


def titles(path):
    return [(x["title"], x["page"]) for x in trust(Filing(path))]


A_T, S_T, C_T, O_T = titles(ANT), titles(SPX), titles(CBR), titles(OURA)

CHECKS = [
    ("Anthropic: 427 printed pages, no number missing or repeated", (len(pages(ANT)), numbered_gaps(ANT)), (427, ([], False))),
    ("Anthropic: p. 293 is the ownership table (landscape page)", "Dario Amodei 240,637,980" in page_text(ANT, "293"), True),
    ("Anthropic: pp. 294 and 295 are its footnotes", ("Founder LLC Agreement" in page_text(ANT, "294"),
                                                     "239,446,940" in page_text(ANT, "295")), (True, True)),
    ("Anthropic: II-1 to II-8 numbered", [p["page"] for p in pages(ANT)][-8:], [f"II-{i}" for i in range(1, 9)]),
    ("Anthropic: the 20 case-study pictures are pp. 212 to 231, marked inferred",
     [p["page"] for p in pages(ANT) if p.get("inferred")][4:24], [str(i) for i in range(212, 232)]),
    ("SpaceX 424B4: 406 pages, none missing", (len(pages(SPX)), numbered_gaps(SPX)), (406, ([], False))),
    ("Cerebras 424B4: 271 pages, none missing", (len(pages(CBR)), numbered_gaps(CBR)), (271, ([], False))),
    ("Oura S-1/A: 347 pages, none missing, EDGAR header not page 1", (len(pages(OURA)), numbered_gaps(OURA)), (347, ([], False))),
    ("fill_between numbers a gap only when it fits exactly", fill_between(["3", None, "5", None, None, "9", "F-1", None, "F-3"])[0],
     ["3", "4", "5", None, None, "9", "F-1", "F-2", "F-3"]),

    ("Cerebras: q5 price $185 from the 424B4 cover", answer(CBR)["q5_price"].get("price", {}).get("value"), 185.0),
    ("SpaceX 424B4: q5 price $135", answer(SPX)["q5_price"].get("price", {}).get("value"), 135.0),
    ("Oura: q5 range $40 to $44", answer(OURA)["q5_price"].get("price_range"), {"low": 40.0, "high": 44.0}),

    ("Anthropic: not an emerging growth company (cover box empty), no EGC flag", any(t == "Emerging growth company" for t, _ in A_T), False),
    ("Anthropic: auditor change Grant Thornton to Ernst & Young (p. 339)",
     ("Auditor changed from Grant Thornton LLP to Ernst & Young LLP", "339") in A_T, True),
    ("Cerebras: emerging growth company (p. 12)", ("Emerging growth company", "12") in C_T, True),
    ("Cerebras: material weakness stated as a finding (pp. 64, 65)", any(t.startswith("Material weakness") for t, _ in C_T), True),
    ("Cerebras: auditor change BDO to KPMG (p. 214)", ("Auditor changed from BDO USA, P.C. to KPMG LLP", "214") in C_T, True),
    ("Oura: emerging growth company (cover box ticked)", ("Emerging growth company", "cover") in O_T, True),
    ("SpaceX: risk-factor 'may reveal material weaknesses' does not fire", any(t.startswith("Material weakness") for t, _ in S_T), False),
    ("No going-concern flag in any of the four", any(t.startswith("Going") for t, _ in A_T + S_T + C_T + O_T), False),
]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
