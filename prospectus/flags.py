"""Flags: the patterns our two IPO editions caught by hand, written down as rules.

From the November 2025 dashboard: people leaving close to the filing, a loss flipping to a profit
just before listing, one customer carrying the business ("if promoter behaviour and the financial
trend diverge, look deeper").
From the June 2026 SpaceX edition: a default cured by waiver, a debt wall, a ratio moved by
shrinking equity, a number stated in the body and withheld from the audited notes, contracts
either side can cancel on short notice, and the filing's silences.

A flag is a pointer to a page, never a verdict. Each one quotes the sentence it found.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from .questions import Filing, answer

MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}


def sentences(filing, pages=None):
    """(page, sentence) for every sentence, lines joined back into prose."""
    for p in filing.pages:
        if pages and not pages(p["page"]):
            continue
        text = re.sub(r"\s*\n\s*", " ", p["text"])
        text = re.sub(r"\s+([’'),.;:])", r"\1", text)
        for s in re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", text):
            if 30 < len(s) < 1500:
                yield p["page"], s.strip()


def windows(filing, before=2, after=2):
    """(page, sentence, the few sentences around it): a name and its number often sit one sentence apart."""
    sents = list(sentences(filing))
    for i, (page, sent) in enumerate(sents):
        ctx = " ".join(x[1] for x in sents[max(0, i - before): i + after + 1] if x[0] == page or True)
        yield page, sent, ctx


def group(flags):
    """One flag per finding: the same sentence repeated in the summary, MD&A and notes becomes one flag
    listing every page it appears on."""
    out = {}
    for x in flags:
        quote = re.sub(r"\W+|\d{4}|march 31|december 31|agreements?", "", x["quote"].lower())[:120]
        key = (x["kind"], quote) if x["kind"] == "contracts" else (x["kind"], x["title"], quote)
        if key in out:
            for pg in x["page"].split(", "):
                if pg not in out[key]["page"].split(", "):
                    out[key]["page"] += ", " + pg
            if len(x["title"]) > len(out[key]["title"]):
                out[key]["title"] = x["title"]  # keep the version that names the counterparty
        else:
            out[key] = dict(x)
    return list(out.values())


def filing_date(filing):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", filing.path.name)
    return date(*map(int, m.groups())) if m else None


def dates_in(s):
    for m in re.finditer(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                         r"\s+(\d{1,2}),\s+((?:19|20)\d\d)", s):
        try:
            yield date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            pass


def money(v):
    """$ millions -> '$4.6B' / '−$907M', the way the dashboard writes it."""
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    if a >= 1:
        return f"{sign}${a:,.0f}M" if a >= 10 else f"{sign}${a:.1f}M"
    return f"{sign}${a * 1000:,.0f}K"


def flag(kind, title, page, quote="", detail=""):
    return {"kind": kind, "title": title, "page": page, "quote": quote[:600], "detail": detail}


# ---------- rules on text ----------

HYPOTHETICAL = re.compile(r"\b(could|may|might|would|if we|in the event|there can be no|we cannot assure|failure to)\b", re.I)


def people_leaving(f, filed):
    """Founders, chiefs and directors who left within a year of the filing (the boAt find: 29 days)."""
    out = []
    rx = re.compile(r"\b(resigned|stepped down|step down|departed|departure|ceased to (?:serve|be)|terminated as|"
                    r"retired as|will retire|transitioned from)\b", re.I)
    role = re.compile(r"\b(founder|co-founder|chief|president|director|chair(?:man|person)?|officer)\b", re.I)
    for page, s in sentences(f):
        if rx.search(s) and role.search(s) and not HYPOTHETICAL.search(s):
            ds = [d for d in dates_in(s) if filed and 0 <= (filed - d).days <= 365]
            if ds:
                days = (filed - max(ds)).days
                out.append(flag("people", f"Senior person left {days} days before this filing", page, s,
                                "The November 2025 rule: if people and the numbers move in different directions, "
                                "look deeper."))
    return out


def defaults_and_waivers(f):
    """A default that actually happened, or a lender's waiver that cured one (SpaceX, F-30)."""
    out = []
    rx = re.compile(r"(technical default|event of default (?:occurred|was triggered|resulted)|resulted in an? "
                    r"(?:technical )?default|(?:obtained|received|entered into|executed) an? (?:\w+ )?(?:waiver|forbearance)"
                    r"|covenant waiver|was not in compliance|were not in compliance|waived the)", re.I)
    for page, s in sentences(f):
        if rx.search(s) and not re.search(r"\b(could|may|might|would)\b(?!.*\b(occurred|obtained|received)\b)", s, re.I):
            out.append(flag("debt", "A default or lender waiver actually happened", page, s))
    return out


def cancellable(f):
    """Contracts either side can end on short notice (Anthropic and Google: 90 days)."""
    out = []
    rx = re.compile(r"(?:terminated|cancell?ed|terminable)\s+(?:by|at the option of)\s+either party\s+(?:upon|on|with)"
                    r"\s+(\d+)\s+days[’']?\s+(?:advance\s+)?(?:written\s+)?notice", re.I)
    for page, sent, ctx in windows(f, before=3, after=0):
        m = rx.search(sent)
        if m:
            who = None
            for w in re.finditer(r"(?:agreements?|arrangements?|contracts?)\s+with\s+([A-Z][\w.&\-]+(?:\s+[A-Z][\w.&\-]+){0,3})", ctx):
                who = re.sub(r"\s+(PBC|Inc\.?|LLC|Corp\.?|Ltd\.?)$", "", w.group(1).strip())
            if who and "." in who:  # "SpaceX.AI" where the filing mostly writes "SpaceXAI": use its usual spelling
                alt = who.replace(".", "")
                body = " ".join(p.get("text", "") for p in getattr(f, "pages", []) if isinstance(p, dict))
                if body.count(alt) > body.count(who):
                    who = alt
            out.append(flag("contracts", f"Either side can cancel on {m.group(1)} days' notice"
                            + (f": {who}" if who else ""), page, sent))
    return out


def concentration(f):
    """One customer or a few carrying the revenue (Cerebras: G42 85% in 2024, MBZUAI 62% in 2025)."""
    out, seen = [], set()
    rx = re.compile(r"(?:accounted for|represented|comprised)\s+(?:approximately\s+)?(\d{1,3}(?:\.\d)?)%"
                    r"(?:\s*(?:,|and)\s*(?:approximately\s+)?(\d{1,3}(?:\.\d)?)%)*\s+of\s+"
                    r"(?:our\s+)?(?:total\s+)?(?:net\s+)?revenues?", re.I)
    not_customer = re.compile(r"segment|product|hardware|software|services|subscription|membership|region|"
                              r"united states|international|domestic|no single customer|recurring|expense|cost|margin|compute|personnel|"
                              r"marketing|administrative|research and development|loss|income|total|percentage", re.I)
    for page, s in sentences(f):
        for m in rx.finditer(s):
            pcts = [float(x) for x in re.findall(r"(\d{1,3}(?:\.\d)?)%", m.group(0))]
            pct = max(pcts)
            subject = s[:m.start()][-160:]
            if pct < 10 or not_customer.search(subject) or HYPOTHETICAL.search(subject[-60:]):
                continue
            who = re.findall(r"“([A-Z][\w&.\- ]{1,40})”|\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,4})", subject)
            skip = set("For In The During As Total Revenue January February March April May June July August September "
                       "October November December".split())
            name = next((a or b for a, b in reversed(who) if (a or b).split()[0] not in skip), "")
            if not name and re.search(r"these customers|customers with", subject, re.I):
                name = "Largest customers"
            key = (name, tuple(pcts))
            if key in seen:
                continue
            seen.add(key)
            shown = " and ".join(f"{x:g}%" for x in pcts)
            out.append(flag("customers", f"{name or 'One customer'}: {shown} of revenue", page, s))
    return out


def control(f):
    """Who holds the vote after the IPO (SpaceX: Musk's ten-vote shares; Anthropic: a Founder LLC with 50.1%)."""
    out = []
    pct = re.compile(r"(\d{1,3}(?:\.\d+)?)%\s+of\s+(?:the\s+)?(?:total|aggregate|combined|outstanding)\s+"
                     r"(?:voting power|votes)", re.I)
    for page, sent, ctx in windows(f, before=1, after=1):
        m = pct.search(sent)
        if m and float(m.group(1)) >= 25 and not HYPOTHETICAL.search(sent[:m.start()][-60:]) \
                and re.search(r"class|LLC|founder|trust|beneficially own|Mr\.|Ms\.", sent, re.I) \
                and not re.search(r"change (?:in|of) (?:the )?(?:effective )?control", sent, re.I):
            no_econ = " It carries no economic rights." if re.search(r"no(?:t have any)? economic rights", ctx, re.I) else ""
            out.append(flag("control", f"One holder or class carries {m.group(1)}% of the vote", page, sent,
                            "You buy a share of the economics, not of the decisions." + no_econ))
        if re.search(r"we (?:are|will be) (?:considered )?a “?controlled company”?", sent, re.I) \
                and not re.search(r"\b(?:not|if|may|might|could)\b", sent, re.I):
            out.append(flag("control", "A controlled company under exchange rules", page, sent,
                            "Controlled companies may skip some board-independence rules."))
    # one flag per kind of control finding, every page listed; keep the sentence that explains why
    merged = {}
    for x in out:
        k = "controlled" if x["title"].startswith("A controlled") else "vote"
        if k not in merged:
            merged[k] = dict(x)
            continue
        pages = merged[k]["page"].split(", ")
        merged[k]["page"] = ", ".join(pages + [p for p in x["page"].split(", ") if p not in pages])
        if "because" in x["quote"] and "because" not in merged[k]["quote"]:
            merged[k]["quote"] = x["quote"]
    return list(merged.values())


def body_vs_notes(f):
    """A counterparty with a dollar figure in the prospectus body, and the same deal in the audited
    notes with the figure left out (SpaceX: $1.25B a month on p. 13, 'a monthly fee' on F-62)."""
    out = []
    deal = re.compile(r"agreements?\s+with\s+([A-Z][\w.&\-]+(?:\s+[A-Z][\w.&\-]+){0,3})", re.I)
    money = re.compile(r"\$\s?[\d.,]+\s*(?:billion|million)", re.I)
    body, notes = {}, {}
    for page, sent, ctx in windows(f, before=0, after=2):
        for m in deal.finditer(sent):
            name = re.sub(r"\s+(PBC|Inc\.?|LLC|Corp\.?|Ltd\.?)$", "", m.group(1).strip())
            if len(name) < 3 or name.lower() in ("the", "our", "certain", "such", "third", "us"):
                continue
            (notes if page.startswith("F-") else body).setdefault(name, []).append((page, ctx, bool(money.search(ctx))))
    for name in body:
        priced = [x for x in body[name] if x[2]]
        unpriced_notes = [x for x in notes.get(name, []) if not x[2]]
        priced_notes = [x for x in notes.get(name, []) if x[2]]
        if priced and unpriced_notes and not priced_notes:
            b, n = priced[0], unpriced_notes[0]
            amount = money.search(b[1]).group(0)
            out.append(flag("disclosure", f"{name}: {amount} in the body, no figure in the audited notes",
                            f"{b[0]} vs {n[0]}", b[1],
                            f"Notes, page {n[0]}: {n[1][:300]}"))
    return out


# ---------- rules on the numbers ----------

def from_numbers(q):
    out = []
    ni = q["q2_funds_itself"]["net_income"].get("values", {})
    fy = [k for k in sorted(ni) if k.isdigit()]
    for a, b in zip(fy, fy[1:]):
        if ni[a] is not None and ni[b] is not None and ni[a] < 0 < ni[b]:
            out.append(flag("numbers", f"Loss in {a} turned into a profit in {b}",
                            q["q2_funds_itself"]["net_income"]["page"], "",
                            f"{a}: {money(ni[a])}; {b}: {money(ni[b])}. Check what drove the turn "
                            "(the November 2025 find: a loss flipping to profit the year before listing)."))
    gap = q["q4_profit_real"].get("gap", {}).get("values", {})
    for y, g in gap.items():
        n = ni.get(y)
        if n is not None and n > 0 and g < -0.2 * abs(n):
            out.append(flag("numbers", f"Profit not turning into cash in {y}", q["q4_profit_real"]["gap"]["page"], "",
                            f"Operating cash flow was {money(abs(g))} below reported profit: the pattern "
                            "behind most accounting frauds."))
        elif n is not None and n < 0 and g > 0.5 * abs(n):
            out.append(flag("numbers", f"Most of the {y} loss is not cash", q["q4_profit_real"]["gap"]["page"], "",
                            f"Reported loss {money(n)}; operating cash flow {money(n + g)}. "
                            "Read the non-cash items before reading the loss."))
    de = q["q3_debt"].get("debt_to_equity", {})
    if de.get("warning"):
        out.append(flag("debt", "Debt to equity moved by shrinking equity", q["q3_debt"]["equity"].get("page", ""),
                        "", de["warning"]))
    if q["q3_debt"].get("equity_negative"):
        out.append(flag("debt", "Equity below zero", q["q3_debt"]["equity"].get("page", ""), "",
                        q["q3_debt"]["equity_negative"]["note"]))
    m = q["q3_debt"].get("maturities", {})
    if m.get("largest_share_pct") and m["largest_share_pct"] >= 40:
        out.append(flag("debt", f"{m['largest_share_pct']}% of debt falls due in {m['largest_year']}", m["page"], "",
                        "Principal due by year: " + ", ".join(
                            f"{y} ${v / 1000:.1f}B" if v >= 1000 else f"{y} ${v:,.0f}M" for y, v in m["schedule"].items() if v)))
    if q["q5_price"].get("price", {}).get("status") == "not disclosed":
        out.append(flag("silence", "No price in this filing", "cover", "",
                        "The price fields are blank. Every valuation multiple waits for the amendment that sets them."))
    return out


def converts_at_ipo(f, q):
    """Pre-IPO funding (convertible notes, convertible preferred) that turns into shares at the offering.
    Without this, a reader sees a deficit and draws the wrong conclusion."""
    pages = [p["page"] for p in f.pages
             if re.search(r"(Convertible Notes|Preferred Stock) Conversion|automatically convert\w* into[^.]{0,120}"
                          r"(?:this offering|initial public offering)", re.sub(r"\s+", " ", p["text"]), re.I)]
    if not pages:
        return []
    d = q["q3_debt"]
    parts = []
    for key, name in (("debt", "convertible notes"), ("redeemable_preferred", "convertible preferred")):
        vals = d.get(key, {}).get("values") or {}
        if vals and (key != "debt" or "onvertible" in d[key].get("note", "")):
            latest = sorted(vals, key=lambda k: (k[-4:], k[:1].isdigit()))[-1]
            parts.append(f"{name} {money(vals[latest])} ({latest})")
    eq = (d.get("equity", {}).get("values") or {})
    if eq:
        latest = sorted(eq, key=lambda k: (k[-4:], k[:1].isdigit()))[-1]
        parts.append(f"equity {money(eq[latest])} ({latest})")
    cap = next((p["page"] for p in f.pages if re.search(r"pro forma basis", p["text"], re.I)
                and re.search(r"Conversion", p["text"])), None)
    # Some notes convert only up to a holder's ownership cap; the rest stays debt after the IPO (Anthropic, Amazon Notes, p. 60).
    stays = next((p["page"] for p in f.pages
                  if re.search(r"ownership cap", p["text"], re.I)
                  and re.search(r"remain outstanding|cannot (?:be fully )?convert|repaid in cash", re.sub(r"\s+", " ", p["text"]), re.I)), None)
    out = flag("numbers", "Pre-IPO funding turns into shares at the offering", ", ".join(dict.fromkeys(pages[:6])), "",
               "Before the IPO: " + "; ".join(parts) + ". These convert into common stock at the offering, "
               "so the deficit is not the picture after listing. Read the pro forma column of the capitalization "
               f"table{(' (page ' + cap + ')') if cap else ''}."
               + (f" Notes above the holder's ownership cap stay outstanding after the offering and convert later "
                  f"or are repaid in cash at maturity (page {stays})." if stays else ""))
    if stays:
        out["stays"] = stays
    return [out]



# ---------- trust: how far the reader can lean on the numbers ----------

FIRM = r"([A-Z][A-Za-z&.,’' ]{1,45}?(?:LLP|L\.L\.P\.|P\.C\.|LLC))"


def _factual(s, m):
    """No hypothetical word before or inside the match: 'if we identify a material weakness' is not one."""
    head = s[:m.end()][-120:]
    return not HYPOTHETICAL.search(head) and not re.search(r"\bif\b|\bwhether\b|\bany\b", head, re.I)


def trust(f):
    """Emerging growth company (and the accounting-standards choice), material weakness, change of
    auditor, going concern. Each fires only on a statement of fact."""
    out, sents_ = [], list(sentences(f))
    cover = " ".join(re.sub(r"\s+", " ", p["text"]) for p in f.pages[:4])
    # emerging growth company: the S-1 cover checkbox, else the company's own sentence
    box = re.search(r"Emerging growth company\s*([☒☐■□✓✔xX])", cover)
    egc = None
    if box and box.group(1) in "☒■✓✔xX":
        egc = ("cover", "Emerging growth company " + box.group(1))
    elif not box:
        said = [(pg, s) for pg, s in sents_ for m in [re.search(r"\bwe are an? “?emerging growth company", s, re.I)]
                if m and _factual(s, m)]
        egc = next(((pg, s) for pg, s in said if pg != "unnumbered"), said[0] if said else None)
    if egc:
        opt_out = next(((pg, s) for pg, s in sents_ for m in [re.search(
            r"(?:irrevocably )?elected not to (?:use|take advantage of) (?:the|this|such) extended transition period|"
            r"(?:have )?(?:irrevocably )?(?:elected to )?opt(?:ed)? out of (?:the|such) extended transition period", s, re.I)]
            if m and _factual(s, m) and not re.search(r"not to opt out", s, re.I)), None)
        uses = next(((pg, s) for pg, s in sents_ for m in [re.search(
            r"elected (?:to (?:use|take advantage of) the extended transition period|not to opt out)", s, re.I)]
            if m and _factual(s, m)), None)
        detail = "Lighter disclosure rules apply (fewer years of audited numbers, no auditor attestation on internal controls)."
        if uses:
            detail += (" It uses the extended transition period for new accounting standards, so its numbers may not "
                       f"line up with public companies that adopt them on time (page {uses[0]}).")
        elif opt_out:
            detail += f" It opted out of the extended transition period for new accounting standards (page {opt_out[0]})."
        out.append(flag("trust", "Emerging growth company", egc[0], egc[1], detail))
    # material weakness, stated as a finding
    mw = re.compile(r"\b(?:we|management|our (?:independent registered public accounting firm|auditors?))(?: and [\w ]{3,60}?)? "
                    r"(?:have |has |had )?(?:previously )?identified (?:certain |a |two |three |several )?material weakness", re.I)
    hits = [(pg, s) for pg, s in sents_ for m in [mw.search(s)] if m and _factual(s, m)]
    if hits:
        pages = ", ".join(dict.fromkeys(pg for pg, _ in hits))
        out.append(flag("trust", "Material weakness in internal control", pages, hits[0][1],
                        "The company says its own controls over the numbers had a material weakness. Read what it was "
                        "and whether it is fixed."))
    # change of auditor
    change = [(pg, s) for pg, s in sents_ for m in [re.search(r"\b(?:dismissed|replaced|engaged)\b[^.]{0,60}?" + FIRM + r"|"
                                                            + FIRM + r"[^.]{0,40}?\b(?:resigned|was dismissed|declined to stand)", s)]
              if m and _factual(s, m) and re.search(r"accountant|accounting firm|auditor|audit", s, re.I)
              and re.search(r"dismiss|resign|replac|declined to stand", s + " " + " ".join(x for p2, x in sents_ if p2 == pg)[:4000], re.I)]
    if change:
        text = " ".join(s for _, s in change)
        old_ = re.search(r"dismissed (?:\w+ ){0,2}?" + FIRM, text) or re.search(FIRM + r"[^.]{0,40}?\b(?:resigned|was dismissed|declined)", text)
        new_ = re.search(r"engaged (?:\w+ ){0,2}?" + FIRM, text)
        title = "Auditor changed"
        if old_ and new_:
            title += f" from {old_.group(1).strip()} to {new_.group(1).strip()}"
        pages = ", ".join(dict.fromkeys(pg for pg, _ in change))
        out.append(flag("trust", title, pages, change[0][1],
                        "A new audit firm signs some of the years. Check both reports and the reason given for the change."))
    # going concern
    gc = re.compile(r"substantial doubt (?:about|regarding|as to) (?:our|the Company[’']s|its) ability to continue as a going concern", re.I)
    hits = [(pg, s) for pg, s in sents_ for m in [gc.search(s)] if m and _factual(s, m)]
    if hits:
        out.append(flag("trust", "Going-concern doubt", hits[0][0], hits[0][1],
                        "The company or its auditor states doubt that it can keep operating without new money."))
    return out


def run(path):
    f = Filing(path)
    q = answer(path)
    filed = filing_date(f)
    flags = group(from_numbers(q) + converts_at_ipo(f, q) + defaults_and_waivers(f) + body_vs_notes(f) + cancellable(f)
                  + concentration(f) + control(f) + people_leaving(f, filed) + trust(f))
    return {"filing": f.path.name, "filed": str(filed), "flags": flags}


def main(path):
    result = run(path)
    out = Path(path).with_suffix(".flags.json")
    out.write_text(json.dumps(result, indent=2))
    for x in result["flags"]:
        print(f"[{x['kind']}] p.{x['page']}: {x['title']}")
        if x["quote"]:
            print("      “" + x["quote"][:260] + "”")
        if x["detail"]:
            print("      " + x["detail"][:260])
    print(f"\n{len(result['flags'])} flags")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
