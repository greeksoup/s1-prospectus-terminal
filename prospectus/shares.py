"""Share counts and the offer terms, read from the prospectus's own words and tables.

Everything carries the printed page it came from. A field the filing leaves blank (an S-1/A before
pricing) is None with a "status" saying so; a field the code could not find says "not read".
Nothing is estimated. Share counts are plain integers; money is $ millions except per-share figures.

run(path) -> {
  "as_of", "offering", "outstanding_after", "excluded", "fully_diluted",
  "underwriting", "lockup_schedule", "capitalization", "dilution"}
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from .tables import read as read_tables, positioned_lines, _page_number
from .pages import page_boxes

N = r"(\d{1,3}(?:,\d{3})+|\d+)"
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DATE = MONTH + r"\s+\d{1,2},\s+\d{4}"
CLASS = r"(?:(?:our\s+)?(Class\s+[A-Z])\s+)?common\s+stock"
NOT_PRINTED = "blank in this filing (not printed yet)"
NOT_READ = "not read"


def _int(s):
    return int(s.replace(",", "")) if s else None


def _norm(text):
    text = re.sub(r"\s+", " ", text.replace("\xa0", " "))
    return re.sub(r"\s+([’'),.;:])", r"\1", text).strip()


class Stream:
    """Several printed pages read as one text, remembering where each page starts."""

    def __init__(self, pages):
        self.text, self.marks = "", []
        for p in pages:
            lines = [l for l in p["text"].split("\n")
                     if l.strip() not in ("Table of Contents", "Table o f Contents", p["page"])]
            self.marks.append((len(self.text), p["page"]))
            self.text += _norm(" ".join(lines)) + " "

    def page_at(self, pos):
        page = self.marks[0][1] if self.marks else None
        for start, pg in self.marks:
            if start <= pos:
                page = pg
        return page


def _load(path):
    path = Path(path)
    pages_file = path.with_suffix(".pages.json")
    if not pages_file.exists():
        from .pages import main as split_pages
        split_pages(str(path))
    return json.loads(pages_file.read_text())


# ---------- the offering box ----------

def _offering_pages(pages):
    """The 'The Offering' summary box: its first page and the next three (the excludes list follows it)."""
    for i, p in enumerate(pages[:80]):
        lines = [l.strip() for l in p["text"].split("\n")[:4]]
        if any(re.fullmatch(r"(?i)the offering", l) for l in lines):
            return pages[i:i + 4]
    return []


def _offering(s):
    t = s.text
    out = {"class": None, "page": None}
    m = re.search(r"(?:(Class [A-Z]) )?[Cc]ommon stock offered by us\s+" + N + r"?\s*shares?"
                  r"(?:\s*\((?:or\s+)?" + N + r" shares if the underwriters)?", t)
    if m:
        out["class"] = m.group(1) or "Common"
        out["primary"] = _int(m.group(2))
        out["page"] = s.page_at(m.start())
        with_option = _int(m.group(3))
    else:
        out["primary"], with_option = None, None
    m = re.search(r"offered by the selling (?:stockholders|shareholders)\s+" + N + r"?\s*shares", t)
    out["secondary"] = _int(m.group(1)) if m else (0 if out["primary"] is not None else None)
    if m and m.group(1) is None:
        out["secondary_status"] = NOT_PRINTED
    # the underwriters' option: printed as its own line, or as "additional N shares", or only as an "(or N shares ...)"
    m = (re.search(r"[Oo]ver-allotment option to purchase additional shares of (?:Class [A-Z] )?common stock from (?:us|the selling \w+)\s+" + N + r"\s+shares", t)
         or re.search(r"option to purchase (?:up to )?an additional " + N + r" shares", t))
    if m:
        out["overallotment"] = _int(m.group(1))
        out["overallotment_from"] = "selling stockholders" if re.search(r"selling", t[m.start():m.end() + 120]) else "us"
    elif with_option and out["primary"] is not None:
        out["overallotment"] = with_option - out["primary"]
        out["overallotment_from"] = "us"
        out["overallotment_note"] = "printed total with the option less the base offer"
    else:
        out["overallotment"] = None
        if re.search(r"option to purchase additional\s+shares", t):
            out["overallotment_status"] = NOT_PRINTED
    if out["primary"] is not None:
        out["shares_offered_total"] = out["primary"] + (out["secondary"] or 0)
    else:
        out["shares_offered_total"] = None
        out["status"] = NOT_PRINTED if re.search(r"offered by us\s+shares", t) else NOT_READ
    return out


def _outstanding_after(s):
    t = s.text
    by_class, page, blank = {}, None, []
    pat = re.compile(r"(?:(Class [A-Z]) )?[Cc]ommon stock (?:to be )?outstanding (?:immediately )?after(?: this offering)?\s+"
                     r"(?:(" + N[1:-1] + r"|one|no) shares?|(None)\b|shares)")
    for m in pat.finditer(t):
        before = t[max(0, m.start() - 160):m.start()]
        if before.strip().endswith(",") or re.search(r"Total [^.]*$|Class [A-Z], [^.]*$", before):
            continue  # "Total Class A, Class B and Class N common stock ..." is the total line
        cls = m.group(1) or "Common"
        if cls in by_class or cls in blank:
            continue
        raw = m.group(2) or m.group(3)
        if raw is None:
            blank.append(cls)
            continue
        by_class[cls] = 0 if raw.lower() in ("none", "no") else 1 if raw.lower() == "one" else _int(raw)
        page = page or s.page_at(m.start())
    total = None
    m = re.search(r"Total [^.]{0,120}?outstanding after\s+" + N + r" shares", t)
    if m:
        total = _int(m.group(1))
    elif by_class and not blank:
        total = sum(by_class.values())
    out = {"by_class": by_class, "total": total, "page": page}
    if m:
        out["total_note"] = "printed total"
    elif total is not None and len(by_class) > 1:
        out["total_note"] = "sum of the classes printed"
    if blank:
        out["blank_classes"] = blank
        out["status"] = NOT_PRINTED
    if not by_class and not blank:
        out["status"] = NOT_READ
    return out


def _as_of(s):
    m = re.search(r"(?:is based on|based on the number of shares)[^.]{0,500}?outstanding as of (" + DATE + ")", s.text)
    return (m.group(1), s.page_at(m.start())) if m else (None, None)


KINDS = [
    ("other", r"\b(?:were issued|issued (?:after|in settlement|in connection)|repurchased|forfeited|withheld in connection|resulting from the conversion)"),
    ("prsus", r"PRSU|market-based vesting"),
    ("warrants", r"\bwarrants?\b"),
    ("options", r"exercise of (?:outstanding )?(?:stock )?options|options to purchase|upon exercise of stock options"),
    ("rsus", r"\bRSUs\b|restricted stock units"),
    ("reserved", r"reserved for (?:future )?issuance"),
]


def _kind(text):
    for kind, pat in KINDS:
        if re.search(pat, text):
            return kind
    return "other"


def _excluded(s):
    t = s.text
    m = re.search(r"(?:\bexcludes?\b|\bexcluding\b|does not reflect any of the following)\s*(?:the following)?\s*:", t)
    if not m:
        return [], NOT_READ
    end = re.search(r"(?:Unless otherwise (?:noted|indicated),|The \d{4} Plan and the ESPP also|Our \d{4} Plan and ESPP each|"
                    r"Unless otherwise indicated, all information)", t[m.end():])
    body = t[m.end(): m.end() + (end.start() if end else 6000)]
    out = []
    pos = m.end()
    for bullet in re.split(r"\s*[•◦]\s*", body):
        if not bullet.strip():
            pos += len(bullet)
            continue
        start = t.find(bullet, pos)
        pos = start + len(bullet)
        page = s.page_at(start)
        head = re.split(r",? of which|\(which|\(none of which|, including", bullet)[0]
        kind = _kind(head)
        pairs = re.findall(r"(?:" + N + r"\s+)shares? of " + CLASS, head)
        strikes = [float(x) for x in re.findall(r"exercise price of \$([\d,.]+)\s*(?:per share)?", bullet)]
        strikes += [float(x) for x in re.findall(r"and \$([\d.]+) per share of Class", bullet)]
        if not pairs:
            if re.match(r"^shares of " + CLASS, head) or re.search(r"consisting of:?$", head):
                out.append({"what": kind, "class": None, "shares": None, "strike": None,
                            "status": NOT_PRINTED, "text": bullet.strip()[:400], "page": page})
            continue
        for i, (num, cls) in enumerate(pairs):
            strike = strikes[i] if i < len(strikes) else (strikes[0] if len(strikes) == 1 else None)
            out.append({"what": kind, "class": cls or "Common", "shares": _int(num),
                        "strike": strike if kind in ("options", "warrants") else None,
                        "text": bullet.strip()[:400], "page": page})
        blank = re.match(r"^shares of " + CLASS, head)
        if blank:
            out.append({"what": kind, "class": blank.group(1) or "Common", "shares": None, "strike": None,
                        "status": NOT_PRINTED, "text": bullet.strip()[:400], "page": page})
    return out, None


def _fully_diluted(after, excluded):
    adds = [e for e in excluded if e["what"] in ("options", "rsus", "prsus", "warrants")]
    note = ("shares outstanding after the offering plus every option, RSU, PRSU and warrant in the "
            "'excludes' list (all classes, at one share each, no treasury method); reserved plan pools and "
            "shares issued, withheld or repurchased after the share-count date are not added")
    if after.get("total") is None:
        return {"value": None, "status": NOT_PRINTED if after.get("status") == NOT_PRINTED else NOT_READ, "note": note}
    blank = [e for e in adds if e["shares"] is None]
    total = after["total"] + sum(e["shares"] for e in adds if e["shares"] is not None)
    out = {"value": total, "note": note, "added": {k: sum(e["shares"] or 0 for e in adds if e["what"] == k)
                                                   for k in ("options", "rsus", "prsus", "warrants")}}
    if blank:
        out["value"], out["status"] = None, f"{len(blank)} dilutive items blank in this filing"
    return out


# ---------- underwriting ----------

def _money(s):
    return float(s.replace(",", ""))


def _underwriting(pages, offering_stream):
    out = {"discount_per_share": None, "discount_total": None, "discount_pct": None, "price": None,
           "net_proceeds": None, "net_proceeds_assumption": None, "page": None}
    for p in pages[:6]:
        t = _norm(p["text"])
        m = re.search(r"Initial public offering price \$ ?([\d,.]+) \$ ?([\d,]+)", t)
        d = re.search(r"Underwriting discounts? and commissions(?: \(\d\))? \$ ?([\d,.]+) \$ ?([\d,]+)", t)
        if m and d:
            out.update(price=_money(m.group(1)), gross=round(_money(m.group(2)) / 1e6, 3),
                       discount_per_share=_money(d.group(1)), discount_total=round(_money(d.group(2)) / 1e6, 3),
                       page=p["page"] if p["page"] != "unnumbered" else "cover")
            break
        # "Price to Public / Underwriting Discounts and Commissions / Proceeds" laid out as columns
        ps = re.search(r"Per Share \$ ?([\d,.]+) \$ ?([\d,.]+) \$ ?([\d,.]+)", t)
        tot = re.search(r"Total \$ ?([\d,]+) \$ ?([\d,]+) \$ ?([\d,]+)", t)
        if ps and re.search(r"Underwriting", t):
            out.update(price=_money(ps.group(1)), discount_per_share=_money(ps.group(2)),
                       page=p["page"] if p["page"] != "unnumbered" else "cover")
            if tot:
                out.update(gross=round(_money(tot.group(1)) / 1e6, 3), discount_total=round(_money(tot.group(2)) / 1e6, 3))
            break
        if re.search(r"Underwriting discounts?(?: and commissions)?(?: \(\d\))? \$ \$", t):
            out["status"] = NOT_PRINTED
            out["page"] = p["page"] if p["page"] != "unnumbered" else "cover"
    if out["discount_per_share"] is not None and out["price"]:
        out["discount_pct"] = round(100 * out["discount_per_share"] / out["price"], 3)
    # net proceeds to the company, after discounts and offering expenses, from the offering box
    t = offering_stream.text
    m = (re.search(r"net proceeds[^.]{0,120}?approximately \$ ?([\d,.]+)\s*(million|billion)", t)
         or re.search(r"approximately \$ ?([\d,.]+)\s*(million|billion) of net proceeds", t))
    if m:
        v = _money(m.group(1)) * (1000 if m.group(2) == "billion" else 1)
        out["net_proceeds"] = round(v, 3)
        out["net_proceeds_page"] = offering_stream.page_at(m.start())
        a = re.search(r"(?:assumed initial public offering price|initial public offering price) of \$ ?([\d.]+) per share(, which is the midpoint[^.]*?range)?",
                      t[m.start(): m.start() + 600])
        if a:
            out["net_proceeds_assumption"] = (f"midpoint ${a.group(1)}" if a.group(2) else f"offer price ${a.group(1)}")
        else:
            out["net_proceeds_assumption"] = "offer price on the cover"
    elif re.search(r"net proceeds[^.]{0,200}?approximately \$ \(", t):
        out["net_proceeds_status"] = NOT_PRINTED
    return out


# ---------- lock-up release schedule ----------

ROW_START = re.compile(r"^(?:Up to|An aggregate|All remaining|If the)")
SUFFIX = re.compile(r"^(?:st|nd|rd|th)$")


def _shares_from(text):
    m = re.search(r"([\d.]+)\s*(million|billion)", text)
    if m:
        return int(round(float(m.group(1)) * (1e9 if m.group(2) == "billion" else 1e6)))
    m = re.search(r"Up to (?:approximately )?" + N + r" shares", text)
    return _int(m.group(1)) if m else None


def _who(text):
    m = re.search(r"(?<!Excludes shares )held by ((?:Mr\.|Ms\.|Dr\.|[^.])+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"\((other than [^)]+)\)", text)
    if m:
        return "all holders " + m.group(1)
    m = re.search(r"representing all shares held by ([^(.,]+)", text)
    return m.group(1).strip() if m else None


def _row(when, right, page):
    when = re.sub(r"(\d+) (st|nd|rd|th)\b", r"\1\2", _norm(when))
    right = _norm(right)
    shares = _shares_from(right)
    out = {"when": when, "shares": shares, "who": _who(right), "text": right, "page": page}
    if shares is None:
        out["status"] = (NOT_PRINTED if re.search(r"Up to\s+shares", right)
                         else "no count printed: all remaining shares" if re.match(r"All remaining", right) else NOT_READ)
    return out


def _lockup_positioned(path):
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="ignore"), "lxml")
    boxes = page_boxes(soup)
    rows, started = [], False
    for b in boxes:
        lines = positioned_lines(b)
        texts = [" ".join(t for _, t in w) for _, w in lines]
        header = next((i for i, t in enumerate(texts) if t.startswith("Earliest Date Available for Sale")), None)
        if not started and header is None:
            continue
        if not started:
            started = True
            xr = lines[header][1][-1][0] - 45  # the cells sit a little left of their heading
            start = header + 1
        else:
            start = 0 if header is None else header + 1
        page = _page_number(lines)
        suffix = None
        for y, words in lines[start:]:
            line = " ".join(t for _, t in words)
            if line in ("Table of Contents", "Table o f Contents", page):
                continue
            if len(words) == 1 and SUFFIX.match(words[0][1].strip()):
                suffix = words[0]
                continue
            left = [(x, t) for x, t in words if x < xr]
            right = " ".join(t for x, t in words if x >= xr)
            if left and suffix:
                # a superscript "th" printed on its own line belongs after the number to its left
                k = max((i for i, (x, _) in enumerate(left) if x < suffix[0]), default=0)
                left[k] = (left[k][0], left[k][1].rstrip() + suffix[1].strip())
                suffix = None
            left_text = " ".join(t for _, t in left)
            if not right and (len(left_text) > 75 or re.match(r"^(?:Lock-Up|As used herein|Lock-up)", left_text)):
                return rows  # the prose after the table
            if right and ROW_START.match(right) and (left_text or not rows):
                rows.append({"when": left_text, "right": right, "page": page})
            elif rows:
                rows[-1]["when"] += " " + left_text
                rows[-1]["right"] += " " + right
    return rows


def _lockup_text(pages):
    """Plain HTML filings: the date lines come first, then the 'Up to ...' line, row after row."""
    i = next((k for k, p in enumerate(pages) if "Earliest Date Available for Sale" in p["text"]), None)
    if i is None:
        return []
    rows, when, cur = [], [], None
    for p in pages[i:i + 3]:
        lines = p["text"].split("\n")
        if p is pages[i]:
            lines = lines[next(k for k, l in enumerate(lines) if "Earliest Date Available for Sale" in l):]
        for raw in lines:
            l = raw.strip()
            if l in ("Table of Contents", p["page"]) or re.match(r"^(Earliest Date Available for Sale in the Public|Market|Number of (Additional )?Shares of)", l):
                continue
            if re.match(r"^\(\d\)$", l) and cur and cur.get("closed"):
                return [_row(r["when"], r["right"], r["page"]) for r in rows]
            if ROW_START.match(l):
                if not when and rows:
                    return [_row(r["when"], r["right"], r["page"]) for r in rows]  # the footnotes under the table
                cur = {"when": " ".join(when), "right": l, "page": p["page"]}
                rows.append(cur)
                when = []
                continue
            if cur and not cur.get("closed") and not re.match(r"^\s*,\s*20\d\d|^(Earliest Potential|Price-Based|Time-Based|U$|p Expiration)", l):
                cur["right"] += " " + l
                if l.endswith("agreements") or l.endswith(")"):
                    pass
                continue
            if cur:
                cur["closed"] = True
            when.append(l)
    return [_row(r["when"], r["right"], r["page"]) for r in rows]


def _lockup(path, layout, pages):
    if layout == "positioned":
        raw = _lockup_positioned(path)
        rows = [_row(r["when"], r["right"], r["page"]) for r in raw]
    else:
        rows = _lockup_text(pages)
    for r in rows:
        r["when"] = re.sub(r"\s*(?:Earliest Potential )?(?:Price|Time)-Based Lock- ?U ?p Expiration Dates\s*", " ", r["when"]).strip()
        r["when"] = re.sub(r"\(\s*(\d+)\s+(st|nd|rd|th)\s+day", r"(\1\2 day", r["when"])
        if r["when"].startswith(","):
            r["date_status"] = "date " + NOT_PRINTED
    return rows


# ---------- capitalization and dilution ----------

MARKERS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009)


def _footnote_only(r):
    """A row holding only footnote markers: "(6)" reads as -6 (or -0.006 on a page in thousands)."""
    v = [x for x in r["values"] if x is not None]
    return bool(v) and all(x < 0 and abs(x) in MARKERS for x in v)


def clean_rows(rows):
    """Merge a row name split by a footnote marker ('Purchase' (3) / 'commitments' ...), drop markers and rules."""
    out = []
    for r in rows:
        label = r["label"].strip()
        if out and _footnote_only(out[-1]) and (label[:1].islower() or not out[-1]["label"]):
            prev = out.pop()
            r = {"label": (prev["label"] + " " + label).strip(), "values": r["values"]}
            label = r["label"]
        out.append({"label": label, "values": r["values"]})
    return [r for r in out if r["label"] and not _footnote_only(r) and not set(r["label"]) <= set("_ ")]


CAP_COLUMNS = ["Actual", "Pro forma", "Pro forma as adjusted"]


def _capitalization(tables, pages):
    idx = next((i for i, t in enumerate(tables) if any(re.match(r"Total capitalization", r["label"]) for r in t["rows"])), None)
    if idx is None:
        return {"status": NOT_READ}
    group = [tables[idx]]
    # the table may begin on the page before
    if idx > 0 and tables[idx - 1]["page"] != tables[idx]["page"] and re.match(r"\d+$", tables[idx - 1]["page"] or "") \
            and any(re.search(r"^Cash", r["label"]) for r in tables[idx - 1]["rows"]) \
            and not any(re.search(r"^Cash", r["label"]) for r in tables[idx]["rows"]):
        group.insert(0, tables[idx - 1])
    rows, width = [], max(len(r["values"]) for t in group for r in t["rows"])
    for t in group:
        for r in clean_rows(t["rows"]):
            vals = r["values"]
            if not any(v is not None for v in vals) or r["label"][:1].islower():
                continue
            if any(v is not None and abs(v) > 5e6 for v in vals) or re.search(r"\b(Dollars|in millions|in thousands)\b", r["label"]):
                continue  # a share count left in the row name, or the unit line
            if re.search(r"par value", r["label"]) and (all(v in (0, 0.0, None) or abs(v) < 0.01 for v in vals)
                                                         or (width >= 3 and all(v is None for v in vals[1:]))):
                continue  # common stock at par: zero dollars
            vals = list(vals) + [None] * (3 - len(vals))
            rows.append({"label": r["label"], "values": dict(zip(CAP_COLUMNS, vals[:3]))})
    out = {"columns": CAP_COLUMNS, "rows": rows, "page": group[0]["page"], "pages": sorted({t["page"] for t in group})}
    if width < 3:
        out["status"] = "pro forma columns blank in this filing (not printed yet)"
    return out


def _dilution(tables, pages):
    rows = None
    for t in tables:
        if any(re.search(r"^Dilution.*per share", r["label"]) for r in t["rows"]):
            rows, page = t["rows"], t["page"]
            break
    out = {"ntbv_per_share_before": None, "ntbv_per_share_after": None, "dilution_per_share": None,
           "price_per_share": None, "page": None}
    if rows is None:
        for p in pages:
            m = re.search(r"historical net tangible book value[^.]{0,80}?was \$ ?\(?([\d.,]+)\)? ?(billion|million)?[^$]{0,30}?or \$ ?(\()?([\d.]+)\)? per share",
                          _norm(p["text"]))
            if m and re.match(r"\d+$", p["page"]):
                out["ntbv_per_share_historical"] = -float(m.group(4)) if m.group(3) else float(m.group(4))
                out["page"] = p["page"]
                out["status"] = "pro forma and dilution figures blank in this filing (not printed yet)"
                return out
        out["status"] = NOT_READ
        return out
    out["page"] = page
    for r in rows:
        v = next((x for x in r["values"] if x is not None), None)
        lab = r["label"]
        if re.search(r"offering price per share", lab, re.I):
            out["price_per_share"] = v
        elif re.match(r"Historical net tangible book value", lab):
            out["ntbv_per_share_historical"] = v
        elif re.match(r"Pro forma net tangible book value", lab):
            out["ntbv_per_share_before"] = v
        elif re.search(r"(?:as adjusted|after).*net tangible book value|net tangible book value.*after giving effect", lab, re.I) \
                and not re.match(r"Increase", lab):
            out["ntbv_per_share_after"] = v
        elif re.match(r"Dilution", lab):
            out["dilution_per_share"] = v
    if out["ntbv_per_share_before"] is None and "ntbv_per_share_historical" in out:
        out["ntbv_per_share_before"] = out["ntbv_per_share_historical"]
    return out


# ---------- run ----------

def run(path):
    pages = _load(path)
    layout, tables = read_tables(path)
    box = Stream(_offering_pages(pages))
    as_of, as_of_page = _as_of(box)
    offering = _offering(box) if box.text else {"status": NOT_READ}
    after = _outstanding_after(box) if box.text else {"status": NOT_READ}
    excluded, ex_status = _excluded(box) if box.text else ([], NOT_READ)
    out = {
        "as_of": as_of,
        "as_of_page": as_of_page,
        "offering": offering,
        "outstanding_after": after,
        "excluded": excluded,
        "fully_diluted": _fully_diluted(after, excluded),
        "underwriting": _underwriting(pages, box),
        "lockup_schedule": _lockup(path, layout, pages),
        "capitalization": _capitalization(tables, pages),
        "dilution": _dilution(tables, pages),
    }
    if ex_status:
        out["excluded_status"] = ex_status
    if not out["lockup_schedule"]:
        out["lockup_status"] = NOT_READ
    return out


def main(path):
    out = run(path)
    dest = Path(path).with_suffix(".shares.json")
    dest.write_text(json.dumps(out, indent=1))
    print(f"shares -> {dest.name}")
    return dest


if __name__ == "__main__":
    main(sys.argv[1])
