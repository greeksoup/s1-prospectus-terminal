"""The qualitative read (prospectus/qual.py) on the four filings on disk. Every expected value below was read
by eye in the page text on 8 Nov 2026 (cover pages, Management tables, Underwriting, Principal
Stockholders, Business). Run: python3 -m tests.test_qual
"""
import glob

from prospectus.qual import run


def latest(cik, form):
    return sorted(glob.glob(f"data/{cik}/filings/*_{form}_*.htm"))[-1]


anthropic = run(latest("2130357", "S-1-A"))
spacex = run(latest("1181412", "424B4"))
cerebras = run(latest("2021728", "424B4"))
oura = run(latest("2133022", "S-1-A"))


def names(people):
    return [p["name"] for p in people] if isinstance(people, list) else []


def holder(result, name):
    rows = result["owners"]["principal_holders"]
    return next((r for r in rows if r["name"] == name), {}) if isinstance(rows, list) else {}


def cls(result, name, cls_):
    return holder(result, name).get("classes", {}).get(cls_, {})


def ctl(result, key):
    return result["owners"]["control"].get(key, {})


def votes(result, cls):
    rows = result["owners"]["classes"]
    return next((c for c in rows if c["name"] == cls), {}) if isinstance(rows, list) else {}


A, S, C, O = anthropic, spacex, cerebras, oura
CHECKS = [
    # Anthropic S-1/A, 2 Nov 2026
    ("Anthropic: price range blank on the cover", A["offer"]["price_range"].get("status"), "not disclosed"),
    ("Anthropic: Nasdaq, ticker ANT (cover)", (A["offer"]["exchange"].get("value"), A["offer"]["ticker"].get("value")), ("Nasdaq", "ANT")),
    ("Anthropic: risk factor headings > 50", A["risks"]["count"] > 50, True),
    ("Anthropic: Class F carries 50.1% of the vote (p. 297)", (votes(A, "Class F").get("voting_power"), votes(A, "Class F").get("page")), ("50.1%", "297")),
    ("Anthropic: executives p. 258", names(A["people"]["executives"]), ["Dario Amodei", "Daniela Amodei", "Krishna Rao"]),
    ("Anthropic: Reed Hastings, director, 66", any(d["name"] == "Reed Hastings" and d["age"] == 66 for d in A["people"]["directors"]), True),
    ("Anthropic: representatives (p. 321)", A["offer"]["underwriters"].get("names"), ["Goldman Sachs & Co. LLC", "Morgan Stanley & Co. LLC"]),
    ("Anthropic: 180-day market standoff (p. 322)", (A["offer"]["lockup"].get("days"), A["offer"]["lockup"].get("page")), (180, "322")),
    ("Anthropic: selling stockholders on the cover", A["offer"]["selling_stockholders"].get("value"), True),
    # ownership table, landscape pages 293 to 295 (read from the page text on 8 Nov 2026 after the page fix)
    ("Anthropic: Dario Amodei 240,637,980 Class A before the offering (p. 293)",
     (cls(A, "Dario Amodei", "Class A").get("shares"), holder(A, "Dario Amodei").get("page")), (240637980, "293")),
    ("Anthropic: officers and directors as a group (7 persons) 496,360,810 Class A",
     cls(A, "All executive officers and directors as a group (7 persons)", "Class A").get("shares"), 496360810),
    ("Anthropic: Founder LLC 1 Class F share, 50.1% of the vote after", (cls(A, "Founder LLC", "Class F").get("shares_after"),
                                                                        holder(A, "Founder LLC").get("votes_pct_after")), (1, 50.1)),
    ("Anthropic: % columns left blank in this version", cls(A, "Tom Brown", "Class A").get("pct_before"), None),
    ("Anthropic: wedge holder Founder LLC, 1 share, total shares blank", (A["owners"]["wedge"].get("holder"),
                                                                         A["owners"]["wedge"].get("shares_held"),
                                                                         A["owners"]["wedge"].get("economic_pct")), ("Founder LLC", 1, None)),
    ("Anthropic: controlled company, Nasdaq (cover)", (ctl(A, "controlled_company").get("value"), ctl(A, "controlled_company").get("exchange")),
     (True, "Nasdaq")),
    ("Anthropic: public benefit corporation (cover)", ctl(A, "public_benefit_corporation").get("value"), True),
    ("Anthropic: LTBT elects the board majority", "LTBT" in ctl(A, "board_majority").get("text", ""), True),
    ("Anthropic: Class F sunset terms (p. 109)", [(x["class"], x["page"]) for x in ctl(A, "sunset").get("quotes", [])][:1], [("Class F", "109")]),
    ("Anthropic: auditor Ernst & Young LLP since 2025, Grant Thornton report too", (A["auditor"].get("name"), A["auditor"].get("since"),
     [x["name"] for x in A["auditor"].get("other_reports", [])]), ("Ernst & Young LLP", 2025, ["Grant Thornton LLP"])),
    ("Anthropic: about 5,300 employees", A["employees"].get("count"), 5300),

    # SpaceX 424B4, 12 Jun 2026
    ("SpaceX: Nasdaq, ticker SPCX (cover)", (S["offer"]["exchange"].get("value"), S["offer"]["ticker"].get("value")), ("Nasdaq", "SPCX")),
    ("SpaceX: offer price $135.00 (cover)", (S["offer"]["price_range"].get("low"), S["offer"]["price_range"].get("fixed")), (135.0, True)),
    ("SpaceX: 555,555,555 shares offered", S["offer"]["shares_offered"].get("value"), 555555555),
    ("SpaceX: Class B ten votes a share", votes(S, "Class B").get("votes_per_share"), 10),
    ("SpaceX: executives p. 226", names(S["people"]["executives"]), ["Elon Musk", "Gwynne Shotwell", "Bret Johnsen"]),
    ("SpaceX: Musk 84.4% combined voting power after the offering (p. 248)", holder(S, "Elon Musk").get("votes_pct"), "84.4%"),
    ("SpaceX: 180-day lock-up (p. 268)", (S["offer"]["lockup"].get("days"), S["offer"]["lockup"].get("page")), (180, "268")),
    ("SpaceX: Goldman Sachs first representative", (S["offer"]["underwriters"].get("names") or [""])[0], "Goldman Sachs & Co. LLC"),
    ("SpaceX: risk factor headings > 40", S["risks"]["count"] > 40, True),
    ("SpaceX: Musk 849,494,440 A and 5,569,053,075 B (p. 248)", (cls(S, "Elon Musk", "Class A").get("shares"),
                                                                 cls(S, "Elon Musk", "Class B").get("shares")), (849494440, 5569053075)),
    ("SpaceX: Musk 12.3% of A before, 11.3% after; 85.1% then 84.4% of the vote", (cls(S, "Elon Musk", "Class A").get("pct_before"),
     cls(S, "Elon Musk", "Class A").get("pct_after"), holder(S, "Elon Musk").get("votes_pct_before"),
     holder(S, "Elon Musk").get("votes_pct_after")), (12.3, 11.3, 85.1, 84.4)),
    ("SpaceX: wedge, Musk 49.0% of all shares after vs 84.4% of the vote (pp. 247, 248)",
     (S["owners"]["wedge"].get("holder"), S["owners"]["wedge"].get("economic_pct"), S["owners"]["wedge"].get("votes_pct")),
     ("Elon Musk", 49.0, 84.4)),
    ("SpaceX: controlled company, Nasdaq", (ctl(S, "controlled_company").get("value"), ctl(S, "controlled_company").get("exchange")),
     (True, "Nasdaq")),
    ("SpaceX: no time sunset, Class B converts on transfer (p. 251)", (ctl(S, "sunset").get("value"), ctl(S, "sunset").get("page")), (False, "251")),
    ("SpaceX: auditor PricewaterhouseCoopers LLP since 2012 (F-3)", (S["auditor"].get("name"), S["auditor"].get("since")),
     ("PricewaterhouseCoopers LLP", 2012)),

    # Cerebras 424B4, 14 May 2026
    ("Cerebras: Nasdaq, ticker CBRS, $185.00", (C["offer"]["exchange"].get("value"), C["offer"]["ticker"].get("value"),
                                                 C["offer"]["price_range"].get("low")), ("Nasdaq", "CBRS", 185.0)),
    ("Cerebras: Class B twenty votes, Class N none", (votes(C, "Class B").get("votes_per_share"), votes(C, "Class N").get("votes_per_share")), (20, 0)),
    ("Cerebras: CEO Andrew D. Feldman, 56", (C["people"]["executives"] or [{}])[0].get("name"), "Andrew D. Feldman"),
    ("Cerebras: Fidelity 10.9% of the vote after (p. 176)", (holder(C, "Entities affiliated with Fidelity").get("votes_pct"),
                                                             holder(C, "Entities affiliated with Fidelity").get("page")), ("10.9%", "176")),
    ("Cerebras: 180-day lock-up", C["offer"]["lockup"].get("days"), 180),
    ("Cerebras: Fidelity 20,443,122 Class B, 9.4% of all shares after (p. 176)", (cls(C, "Entities affiliated with Fidelity", "Class B").get("shares"),
     holder(C, "Entities affiliated with Fidelity").get("outstanding_pct_after")), (20443122, 9.4)),
    ("Cerebras: Feldman 10,158,635 B before, 10,144,876 B after", (cls(C, "Andrew D. Feldman", "Class B").get("shares"),
                                                                   cls(C, "Andrew D. Feldman", "Class B").get("shares_after")), (10158635, 10144876)),
    ("Cerebras: not a controlled company (p. 70 says it only may become one)", ctl(C, "controlled_company").get("value"), False),
    ("Cerebras: Class B founder sunset (p. 181)", (ctl(C, "sunset").get("value"), ctl(C, "sunset").get("page")), (True, "181")),
    ("Cerebras: auditor KPMG LLP, BDO report on the earlier year", (C["auditor"].get("name"),
     [x["name"] for x in C["auditor"].get("other_reports", [])]), ("KPMG LLP", ["BDO USA, P.C."])),
    ("Cerebras: 708 employees", C["employees"].get("count"), 708),
    ("Cerebras: no selling stockholders", C["offer"]["selling_stockholders"].get("value"), False),

    # Oura S-1/A, 21 Sep 2026
    ("Oura: price range $40.00 to $44.00 (cover)", (O["offer"]["price_range"].get("low"), O["offer"]["price_range"].get("high")), (40.0, 44.0)),
    ("Oura: Nasdaq, ticker OURA", (O["offer"]["exchange"].get("value"), O["offer"]["ticker"].get("value")), ("Nasdaq", "OURA")),
    ("Oura: 13.5M by Oura, 36.5M by sellers", (O["offer"]["shares_offered"].get("by_company"), O["offer"]["shares_offered"].get("by_selling_stockholders")),
     (13500000, 36500000)),
    ("Oura: executives p. 179", names(O["people"]["executives"]), ["Thomas Hale", "David Shuman", "Sean Brecker", "Michael A. Chapp"]),
    ("Oura: 180-day lock-up (p. 235)", (O["offer"]["lockup"].get("days"), O["offer"]["lockup"].get("page")), (180, "235")),
    ("Oura: FMR 10.9% before, 10.4% after (p. 206)", (holder(O, "Entities affiliated with FMR LLC").get("pct_before"),
                                                       holder(O, "Entities affiliated with FMR LLC").get("pct_after")), ("10.9%", "10.4%")),
    ("Oura: about 1,350 employees", O["employees"].get("count"), 1350),
    ("Oura: FMR 33,609,862 shares before and after (p. 206)", (cls(O, "Entities affiliated with FMR LLC", "Common stock").get("shares"),
     cls(O, "Entities affiliated with FMR LLC", "Common stock").get("shares_after")), (33609862, 33609862)),
    ("Oura: Lifeline sells 6,947,864, keeps 15,616,292 (4.9%)", (holder(O, "Entities affiliated with Lifeline Ventures").get("shares_offered"),
     cls(O, "Entities affiliated with Lifeline Ventures", "Common stock").get("shares_after"),
     cls(O, "Entities affiliated with Lifeline Ventures", "Common stock").get("pct_after")), (6947864, 15616292, 4.9)),
    ("Oura: group of 12 holds 75,475,938 before (p. 207)",
     cls(O, "All executive officers, directors, and director nominees as a group (12 individuals)", "Common stock").get("shares"), 75475938),
    ("Oura: one class, so no wedge", O["owners"]["wedge"].get("status"), "single class"),
    ("Oura: auditor Ernst & Young LLP since 2024 (F-2)", (O["auditor"].get("name"), O["auditor"].get("since")), ("Ernst & Young LLP", 2024)),
]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
