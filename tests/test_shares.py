"""prospectus/shares.py against figures read by eye from each filing's page text on 8 Nov 2026.
SpaceX 424B4 (cover, pp. 17-19, 71, 258-259), Cerebras 424B4 (cover, pp. 13, 15, 84, 87, 189),
Oura S-1/A (pp. 14-16, 87, 226), Anthropic S-1/A (pp. 18, 20, 128, 130).
Run: python3 -m tests.test_shares
"""
import glob

from prospectus.shares import run

SPX = run(glob.glob("data/1181412/filings/2026-06-12_424B4_*.htm")[0])
CBR = run(glob.glob("data/2021728/filings/*424B4*.htm")[-1])
OURA = run(glob.glob("data/2133022/filings/2026-09-21_S-1-A_*.htm")[0])
ANT = run(glob.glob("data/2130357/filings/2026-11-02_S-1-A_*.htm")[0])


def excl(d, what, cls=None):
    return [(e["shares"], e["strike"]) for e in d["excluded"] if e["what"] == what and (cls is None or e["class"] == cls)]


def lock(d, i):
    return d["lockup_schedule"][i]["shares"] if len(d["lockup_schedule"]) > i else None


def cap(d, label, col):
    return next((r["values"][col] for r in d["capitalization"].get("rows", []) if r["label"].startswith(label)), None)


CHECKS = [
    # SpaceX
    ("SPX p17 Class A offered", SPX["offering"]["primary"], 555555555),
    ("SPX cover over-allotment", SPX["offering"]["overallotment"], 83333333),
    ("SPX p17 Class A after offering", SPX["outstanding_after"]["by_class"].get("Class A"), 7380196910),
    ("SPX p17 Class B after offering", SPX["outstanding_after"]["by_class"].get("Class B"), 5695668265),
    ("SPX p18 share base date", SPX["as_of"], "March 31, 2026"),
    ("SPX p19 Class A options and strike", excl(SPX, "options", "Class A")[0], (133793640, 27.65)),
    ("SPX p19 Class B options and strike", excl(SPX, "options", "Class B")[0], (358169015, 8.22)),
    ("SPX cover discount per share", SPX["underwriting"]["discount_per_share"], 0.90),
    ("SPX cover discount total $M", SPX["underwriting"]["discount_total"], 500.0),
    ("SPX p17 net proceeds $M", SPX["underwriting"]["net_proceeds"], 74400.0),
    ("SPX p71 dilution per share", SPX["dilution"]["dilution_per_share"], 127.15),
    ("SPX p71 NTBV per share after", SPX["dilution"]["ntbv_per_share_after"], 7.85),
    ("SPX p69 cash pro forma as adjusted", cap(SPX, "Cash and cash equivalents", "Pro forma as adjusted"), 90300.0),
    ("SPX p258 first lock-up release", lock(SPX, 0), 911500000),
    ("SPX p258 price-triggered release", lock(SPX, 1), 455800000),
    # Cerebras
    ("CBR p13 Class A offered", CBR["offering"]["primary"], 30000000),
    ("CBR p13 over-allotment", CBR["offering"]["overallotment"], 4500000),
    ("CBR p13 total after offering", CBR["outstanding_after"]["total"], 215110345),
    ("CBR p13 Class B after offering", CBR["outstanding_after"]["by_class"].get("Class B"), 185110345),
    ("CBR p15 options and strike", excl(CBR, "options")[0], (28361707, 4.97)),
    ("CBR p15 PRSUs", excl(CBR, "prsus")[0][0], 9000000),
    ("CBR p15 OpenAI warrant", excl(CBR, "warrants")[0][0], 33445026),
    ("CBR cover discount per share", CBR["underwriting"]["discount_per_share"], 4.3475),
    ("CBR cover discount total $M", CBR["underwriting"]["discount_total"], 130.425),
    ("CBR p13 net proceeds $M", CBR["underwriting"]["net_proceeds"], 5408.5),
    ("CBR p84 total capitalization as adjusted", cap(CBR, "Total capitalization", "Pro forma as adjusted"), 6347.115),
    ("CBR p87 dilution per share", CBR["dilution"]["dilution_per_share"], 155.49),
    ("CBR p189 day-one employee release", lock(CBR, 0), 2500000),
    # Oura
    ("OURA p16 share base date", OURA["as_of"], "June 30, 2026"),
    ("OURA p14 shares after offering", OURA["outstanding_after"]["total"], 320945459),
    ("OURA p14 primary / secondary / option", (OURA["offering"]["primary"], OURA["offering"]["secondary"],
                                               OURA["offering"]["overallotment"]), (13500000, 36500000, 7500000)),
    ("OURA p16 plan options at $0.46", excl(OURA, "options")[0], (21746410, 0.46)),
    ("OURA p16 plan RSUs", excl(OURA, "rsus")[0][0], 10842504),
    ("OURA fully diluted (p14 + p16 options and RSUs)", OURA["fully_diluted"]["value"], 355849309),
    ("OURA p15 net proceeds at $42 midpoint", (OURA["underwriting"]["net_proceeds"], OURA["underwriting"]["net_proceeds_assumption"]),
     (532.6, "midpoint $42.00")),
    ("OURA cover discount blank", OURA["underwriting"]["discount_per_share"], None),
    ("OURA p87 dilution per share", OURA["dilution"]["dilution_per_share"], 42.69),
    ("OURA p226 Stage 1 price-based release", lock(OURA, 0), 17000000),
    # Anthropic (S-1/A before the price: most counts blank)
    ("ANT p18 Class A after offering blank", "Class A" in ANT["outstanding_after"].get("blank_classes", []), True),
    ("ANT p20 options and strike", excl(ANT, "options")[0], (1774342693, 2.91)),
    ("ANT fully diluted waits on the price", ANT["fully_diluted"]["value"], None),
    ("ANT p130 historical NTBV per share", ANT["dilution"].get("ntbv_per_share_historical"), -68.47),
    ("ANT p128 cash actual", cap(ANT, "Cash, cash equivalents", "Actual"), 131845.0),
    ("ANT p311 lock-up counts blank", lock(ANT, 0), None),
]

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
