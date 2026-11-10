"""The qualitative read of a prospectus: what the company does, the offer, who owns and runs it,
the risks it lists, related-party dealings, lawsuits and headcount.

Every item carries the printed page it was read from and the filing's own words, so a reader can
open the page and check. When a rule is not sure, the item says "not found" or "not disclosed"
rather than guess. Nothing here is paraphrased into a fact the filing does not state.
"""
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from .flags import HYPOTHETICAL, filing_date, people_leaving
from .pages import PAGE_NUMBER, read_html
from .versions import table_of_contents

NOT_FOUND = {"status": "not found"}
NOT_DISCLOSED = {"status": "not disclosed"}


# ---------- the filing, its pages and its sections ----------

class Doc:
    """Just the printed pages (no table reading): enough for every text rule here."""

    def __init__(self, path):
        self.path = Path(path)
        pages_file = self.path.with_suffix(".pages.json")
        if not pages_file.exists():
            from .pages import main as split_pages
            split_pages(str(path))
        self.pages = json.loads(pages_file.read_text())
        self.toc_seq, toc = _toc(self)
        self.sections = _sections(self, toc)
        for p in self.pages:  # unnumbered pages ahead of the contents page are the cover
            if p["page"] == "unnumbered" and self.toc_seq and p["seq"] < self.toc_seq:
                p["page"] = "cover"

    def section(self, key):
        rng = self.sections.get(key)
        return [p for p in self.pages if rng and rng[0] <= p["seq"] < rng[1]]

    def cover(self):
        end = self.toc_seq or 6
        return [p for p in self.pages if p["seq"] < end][:12]

    def body(self):
        return [p for p in self.pages if not p["page"].startswith("F-")]


class _Sub:
    def __init__(self, pages):
        self.pages = pages


ABBREV_END = re.compile(r"\b(?:Co|Inc|Mr|Ms|Mrs|Dr|No|U\.S|L\.P|Corp|Ltd|p\.m|a\.m|Jr|Sr|St|Messrs)\.$")
SPLIT_AT = re.compile(r"[.;][”\"]?(?=\s+[A-Z(“\"•])")


def sents(pages):
    """(page, sentence) over a run of pages read as one stream (a sentence broken by a page break stays
    whole and keeps the page it starts on). Lines are joined back into prose; a split never falls after
    an abbreviation ("Goldman Sachs & Co. LLC", "Mr. Musk") and no piece is dropped, so a quote is always
    the filing's full sentence."""
    full, marks = "", []
    for p in pages:
        lines = [l for l in p["text"].split("\n")
                 if l.strip() and l.strip() != "Table of Contents" and not PAGE_NUMBER.match(l.strip())]
        text = re.sub(r"\s+", " ", " ".join(lines)).strip()
        text = re.sub(r"\s+([’'),.;:])", r"\1", text)
        if text:
            marks.append((len(full), p["page"]))
            full += text + " "
    out, start = [], 0

    def page_at(off):
        return [pg for o, pg in marks if o <= off][-1]
    for m in SPLIT_AT.finditer(full):
        piece = full[start:m.end()]
        if ABBREV_END.search(piece):
            continue
        if piece.strip():
            out.append((page_at(start + len(piece) - len(piece.lstrip())), piece.strip()))
        start = m.end()
    if full[start:].strip():
        out.append((page_at(start), full[start:].strip()))
    return [(pg, x) for pg, x in out if len(x) > 1]


TOC_PAIR = re.compile(r"([A-Z][A-Za-z’'&,\-/(). ]{2,110}?)\s+(\d{1,3}|F-1|[ivx]{1,5})(?=\s|$)")


def _toc(doc):
    """(seq of the contents page, [(section, printed page)]). Uses the versions module's reader first;
    falls back to a looser one for two-column contents pages and one-cell-per-line HTML."""
    toc = table_of_contents(doc)
    for p in doc.pages[:40]:
        if not re.search(r"table\s+of\s+contents", p["text"], re.I):  # "TABLE" / "OF CONTENTS" on two lines (LIS)
            continue
        joined = re.sub(r"\s+", " ", p["text"])
        pairs = [(n.strip(), pg) for n, pg in TOC_PAIR.findall(joined)]
        names = " ".join(n for n, _ in pairs)
        # a best-efforts or placement-agent offering lists "Plan of Distribution" instead of "Underwriting"
        if len(pairs) >= 8 and re.search(r"Risk\s+Factors", names, re.I) and re.search(r"Underwrit|Plan\s+of\s+Distribution|The\s+Conversion", names, re.I):
            if not toc:
                toc = [(re.sub(r"^(?:Page\s+)+", "", n), pg) for n, pg in pairs if not re.fullmatch(r"[ivx]+", pg)]
            return p["seq"], toc
    return None, toc


SECTION_NAMES = {
    # the first name in a contents list can carry the heading in front ("TABLE OF CONTENTS Page SUMMARY"),
    # and banks, small companies and best-efforts offerings name their sections their own way (Nov 2026)
    "summary": r"(?:^|\bpage\s+)(?:prospectus\s+)?summary$|^summary$",
    "risk": r"^risk factors$|\brisk factors$",
    "proceeds": r"^use of (?:the )?proceeds|use the proceeds",
    "dividend": r"^dividend policy|^our dividend policy|policy regarding dividends",
    "business": r"^business$|^business of |^(?:detailed )?description of (?:our )?business|^our business$",
    "management": r"^management$|^directors,? (?:and )?executive officers|^executive officers(?:,| and) directors",
    "related": r"certain relationships|related (?:party|person) transactions",
    "principal": r"principal (?:and selling )?(?:stock|share)holders|security ownership|beneficial ownership of|^stock ownership",
    "capital": r"^description of (?:capital stock|share capital|securities)",
    "eligible": r"^shares eligible",
    "underwriting": r"^underwrit|^plan of distribution",
}


def _sections(doc, toc):
    """{key: (first seq, seq after the last)} from the printed page numbers in the contents."""
    after = doc.toc_seq or 0
    first_seq = {}
    for p in doc.pages:
        if p["seq"] > after and p["page"].isdigit() and p["page"] not in first_seq:
            first_seq[p["page"]] = p["seq"]
    f1 = next((p["seq"] for p in doc.pages if p["page"].startswith("F-")), len(doc.pages) + 1)

    def seq_of(page):
        n = int(page)
        for k in range(n, n + 4):  # a section opening on an unreadable page: take the next readable one
            if str(k) in first_seq:
                return first_seq[str(k)] - (k - n)
        return None
    starts = sorted({(int(pg), name) for name, pg in toc if pg.isdigit()})
    out = {}
    for i, (pg, name) in enumerate(starts):
        s = seq_of(str(pg))
        if s is None:
            continue
        nxt = next((seq_of(str(q)) for q, _ in starts[i + 1:] if q > pg and seq_of(str(q))), f1)
        for key, rx in SECTION_NAMES.items():
            if key not in out and re.search(rx, name.strip(), re.I):
                out[key] = (s, max(nxt, s + 1))
    return out


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(?:T\s?able\s?o\s?f\s?Contents\s*)+", "", s)
    s = re.sub(r"\s+([’'),.;:”])", r"\1", s)
    return re.sub(r"(?<=[.”])\s+\d{1,3}$", "", s)  # a page number caught at the end of a section


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def found(value=None, page=None, text=None, **more):
    out = {}
    if value is not None:
        out["value"] = value
    out.update(more)
    if text is not None:
        out["text"] = clean(text)
    out["page"] = page
    return out


# ---------- summary ----------

DESCRIBES = re.compile(r"\b(?:we are|we build|we provide|we design|we make|we offer|we develop|we deliver|we sell|we operate|"
                       r"is an?|was founded|our mission is|is building|are building)\b", re.I)


def summary(doc):
    """The opening sentences under "Overview" that say what the company is and does."""
    pages = doc.section("summary")
    for i, p in enumerate(pages):
        lines = p["text"].split("\n")
        for j, line in enumerate(lines):
            if line.strip() in ("Overview", "Our Company", "Our Business", "Company Overview", "Business Overview"):
                nxt = pages[i + 1]["text"].split("\n") if i + 1 < len(pages) else []
                text = " ".join(l for l in lines[j + 1:] + nxt
                                if l.strip() != "Table of Contents" and not PAGE_NUMBER.match(l.strip()))
                ss = [s for _, s in sents([{"page": p["page"], "text": text}])]
                start = next((k for k, s in enumerate(ss[:8]) if DESCRIBES.search(s)), None)
                if start is None:
                    return NOT_FOUND
                picked, size = [], 0
                for s in ss[start:]:
                    if picked and (size + len(s) > 700 or len(picked) >= 4):
                        break
                    picked.append(s)
                    size += len(s)
                    if len(picked) >= 2 and size > 350:
                        break
                return found(page=p["page"], text=" ".join(picked))
    return NOT_FOUND


# ---------- the offer ----------

def _cover_text(doc):
    return [(p["page"], clean(p["text"])) for p in doc.cover()]


def _first(doc_pages, rx, flags=0):
    for page, text in doc_pages:
        m = re.search(rx, text, flags)
        if m:
            return page, m, text
    return None, None, None


def _quote(text, m, before=0, after=0):
    """The sentence holding a match, as printed."""
    a = max(text.rfind(". ", 0, m.start()) + 2, 0) if before == 0 else max(0, m.start() - before)
    b = text.find(". ", m.end())
    b = len(text) if b == -1 else b + 1
    return text[a:b][:600]


def offer(doc):
    cover = _cover_text(doc)
    out = {}

    page, m, text = _first(cover, r"([\d,]{5,}) Sh ?ares\b")
    if m:
        item = found(value=int(m.group(1).replace(",", "")), page=page, text=m.group(0).replace("Sh ares", "Shares"))
        pg2, m2, t2 = _first(cover, r"(?:We are|is) offering ([\d,]{5,}) shares")
        if m2:
            item["by_company"] = int(m2.group(1).replace(",", ""))
        pg3, m3, t3 = _first(cover, r"selling (?:stock|share)holders?[^.]{0,80}? (?:are|is) offering ([\d,]{5,}) shares")
        if m3:
            item["by_selling_stockholders"] = int(m3.group(1).replace(",", ""))
        out["shares_offered"] = item
    else:
        out["shares_offered"] = NOT_DISCLOSED

    page, m, text = _first(cover, r"public offering price(?: per share)?(?: of (?:our|the) [\w ]+?stock)? (?:is|of) \$\s?(\d+(?:\.\d+)?)")
    if m:
        out["price_range"] = found(value=f"${m.group(1)} per share", page=page, text=_quote(text, m), low=float(m.group(1)),
                                   high=float(m.group(1)), fixed=True)
    else:
        page, m, text = _first(cover, r"between \$\s?(\d+(?:\.\d+)?) and \$\s?(\d+(?:\.\d+)?)")
        if m:
            out["price_range"] = found(value=f"${m.group(1)} to ${m.group(2)} per share", page=page, text=_quote(text, m),
                                       low=float(m.group(1)), high=float(m.group(2)), fixed=False)
        else:
            page, m, text = _first(cover, r"between \$\s*and \$")
            out["price_range"] = dict(NOT_DISCLOSED, page=page, text=clean(_quote(text, m))) if m else NOT_DISCLOSED

    page, m, text = _first(cover, r"list (?:our|its|the|these)[^.]{0,80}? on (?:the )?(The Nasdaq[^.,“(]{0,40}|Nasdaq[^.,“(]{0,40}|"
                                  r"New York Stock Exchange|NYSE[^.,“(]{0,20})")
    if m:
        venue = re.sub(r"\s+under the.*$", "", m.group(1)).strip()
        out["exchange"] = found(value="Nasdaq" if "Nasdaq" in venue else "NYSE", page=page, text=_quote(text, m), listing=venue)
    else:
        out["exchange"] = NOT_FOUND
    page, m, text = _first(cover, r"under the (?:ticker )?symbol\s*[“\"]\s*([A-Z][A-Z.]{0,5})\s*[,.]?\s*[”\"]")
    out["ticker"] = found(value=m.group(1).rstrip("."), page=page, text=_quote(text, m)) if m else NOT_FOUND

    out["underwriters"] = underwriters(doc)
    out["use_of_proceeds"] = use_of_proceeds(doc)
    out["lockup"] = lockup(doc)

    page, m, text = _first(cover, r"selling (?:stock|share)holders?[^.]{0,60}?(?:are|is) (?:offering|selling)|offered by the selling (?:stock|share)holders")
    if m:
        out["selling_stockholders"] = found(value=True, page=page, text=_quote(text, m))
    else:
        page, m, text = _first(cover, r"(?:We are|is) offering [\d,]* ?shares")
        mentions = any(re.search(r"selling (?:stock|share)holder", t, re.I) for _, t in cover)
        out["selling_stockholders"] = (found(value=False, page=page, text=_quote(text, m))
                                       if m and not mentions else NOT_FOUND)
    out["dividend_policy"] = first_sentences(doc.section("dividend"), 2)
    return out


def first_sentences(pages, n, skip=r"^(?:Table of Contents|[A-Z][A-Za-z ]{0,40})$"):
    if not pages:
        return NOT_FOUND
    ss = [(pg, s) for pg, s in sents(pages) if not re.match(r"^(?:Table of Contents )?[A-Z][A-Z ’']+$", s)]
    if not ss:
        return NOT_FOUND
    first = ss[0][1]
    first = re.sub(r"^(?:Table of Contents\s+)?(?:[A-Z][A-Za-z’' ]{2,30}?\s+)?(?=(?:We|Our|The|Each|In|Since|Holders|No)\b)", "", first, count=1)
    picked = [first] + [s for _, s in ss[1:n]]
    return found(page=ss[0][0], text=" ".join(picked))


FIRM = re.compile(r"LLC|Inc\.?|Incorporated|& Co\.?|Securities|Capital|Ltd\.?|plc|L\.P\.|Markets|Company")


SENTENCE_START = re.compile(r"(?<!\bCo)(?<!\bInc)(?<!\bCorp)(?<!\bL\.P)(?<!\bU\.S)\.\s+(?=[A-Z])")


def underwriters(doc):
    pages = doc.section("underwriting") or doc.body()
    for p in pages:
        text = clean(p["text"])
        m = re.search(r"(?:are|is) (?:acting as )?(?:the )?(?:joint )?(?:book-running managers and )?representatives?\b", text)
        if not m:
            continue
        lead = text[max(0, m.start() - 400):m.start()]
        if "for whom " in lead:
            lead = lead.rsplit("for whom ", 1)[1]
        else:
            cuts = [x.end() for x in SENTENCE_START.finditer(lead)]
            lead = lead[cuts[-1]:] if cuts else lead
        names = [x.strip() for x in re.split(r",(?!\s*(?:Inc\b|LLC\b|L\.P\.|Ltd\b|PLC\b))\s*(?:and\s+)?|\s+and\s+(?=[A-Z])", lead.strip())
                 if x.strip()]
        names = [x for x in names if FIRM.search(x) and len(x) < 60]
        if names:
            return {"names": names, "role": "representatives of the underwriters",
                    "text": clean(lead + " " + m.group(0)), "page": p["page"]}
    return NOT_FOUND


def use_of_proceeds(doc):
    pages = doc.section("proceeds")
    if not pages:
        return NOT_FOUND
    ss = sents(pages)
    picked = []
    for rx in (r"net proceeds", r"intend to use|will use|expect to use"):
        hit = next(((pg, s) for pg, s in ss if re.search(rx, s, re.I) and (pg, s) not in picked and len(s) < 700), None)
        if hit:
            picked.append(hit)
    for pg, s in ss:
        if len(picked) >= 3:
            break
        if re.search(r"intend to use|will use|remaining", s, re.I) and (pg, s) not in picked and len(s) < 700:
            picked.append((pg, s))
    if not picked:
        return NOT_FOUND
    picked.sort(key=lambda x: ss.index(x))
    return found(page=picked[0][0], text=" ".join(re.sub(r"^(?:Table of Contents\s+)?Use of Proceeds\s+", "", s, flags=re.I)
                                                  for _, s in picked))


def lockup(doc):
    for pages in (doc.section("underwriting"), doc.section("eligible")):
        got = _lockup(pages)
        if got:
            return got
    return NOT_FOUND


def _lockup(pages):
    rx = re.compile(r"(?:period (?:ending|of)\s+)?(\d{2,3})\s+days after the date of (?:this|the final) prospectus|(\d{2,3})-day "
                    r"(?:lock-up|restricted) period", re.I)
    # the sentence that defines the lock-up ("during the period ending 180 days after the date of this
    # prospectus", "180 days after ... (the “Lock-up Period”)") wins over release schedules and exceptions
    defining = re.compile(r"period (?:ending|of)\s+(\d{2,3})\s+days after the date of (?:this|the final) prospectus|"
                          r"(\d{2,3})\s+days after the date of (?:this|the final) prospectus\s*\(the\s*[“\"](?:lock-\s?up|restricted) period",
                          re.I)
    hits, main = [], None
    for page, s in sents(pages):
        d = defining.search(s)
        if d and main is None and not re.search(r"\d%|percent", s[:d.start()]):
            main = (int(d.group(1) or d.group(2)), page, s)
        if re.search(r"lock-up|restricted period|agreed[^.]{0,200}not to", s, re.I) or d:
            for m in rx.finditer(s):
                hits.append((int(m.group(1) or m.group(2)), page, s))
    if not hits:
        return None
    if main:
        days, page, s = main
    else:
        days = Counter(h[0] for h in hits).most_common(1)[0][0]
        page, s = next((h[1], h[2]) for h in hits if h[0] == days)
    other = sorted({h[0] for h in hits} - {days})
    s = re.split(r"Lock-[Uu]p (?:and Market Standoff )?Agreements\s+", clean(s))[-1]
    out = {"days": days, "text": s[:700], "page": page}
    if other:
        out["other_periods_days"] = other
    return out


# ---------- owners ----------

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "twenty": 20, "fifty": 50, "one hundred": 100}


def _votes(word):
    return int(word) if word.isdigit() else WORDS.get(word.lower())


def classes(doc):
    pages = doc.cover() + doc.section("capital") + doc.section("summary")
    found_ = {}
    pats = [
        (r"[Ee]ach share of (?:our )?(Class [A-Z]) common stock (?:is|will be) entitled to (\w+) votes?", "n"),
        (r"[Ee]ach share of (?:our )?(Class [A-Z]) common stock will entitle its holder to (\w+) votes?", "n"),
        (r"[Hh]olders? of (?:our )?(Class [A-Z]) common stock (?:are|is|will be) entitled to (\w+) votes? (?:for|per)", "n"),
        (r"[Ee]ach share of (?:our )?(Class [A-Z]) common stock (?:is|will be) non-voting", "zero"),
        (r"[Hh]olders? of (?:our )?(Class [A-Z]) common stock (?:are|is|will be) not entitled to vote", "zero"),
        (r"(?:holders?|holder) of (?:our )?(Class [A-Z]) common stock (?:has|have|will have) no voting rights", "zero"),
        (r"(Class [A-Z]) common stock (?:is|will be) entitled to an aggregate number of votes that equals (\d+(?:\.\d+)?%)", "pct"),
        (r"[Hh]olders of (?:our )?(common stock) (?:are|will be) entitled to (one) vote (?:for|per) each share", "n"),
    ]
    for page, s in sents(pages):
        for rx, kind in pats:
            for m in re.finditer(rx, s):
                name = m.group(1)
                name = "Common stock" if name == "common stock" else name
                if name in found_:
                    continue
                item = {"name": name, "page": page, "text": re.sub(r"\s+[•◦].*$", "", clean(s))[:500]}
                if kind == "n":
                    item["votes_per_share"] = _votes(m.group(2))
                elif kind == "pct":
                    item["votes_per_share"] = None
                    item["voting_power"] = m.group(2)
                else:
                    tail = s[m.end():]
                    if re.search(r"except", tail) and re.search(r"elect|director", tail, re.I):
                        item["votes_per_share"] = None
                        item["note"] = "No general vote; the quoted exception gives it a vote on specific matters."
                    else:
                        item["votes_per_share"] = 0
                if kind == "n" and item["votes_per_share"] is None:
                    continue
                found_[name] = item
    return sorted(found_.values(), key=lambda x: x["name"]) or NOT_FOUND


# ---------- principal stockholders: the ownership table, column by column ----------
#
# The table is read from the HTML, not the page text: the text loses blank cells (Anthropic's S-1/A
# prints a share count with every % left blank), so a value can only be placed in its column by where
# it sits. Workiva pages put each table cell in its own positioned box (left + width); Donnelley-style
# HTML puts it in a <td> whose grid position follows from the colspans. Either way a header cell that
# holds no smaller header cell is one column, and every header cell above it names it.

CELL_NUMBER = re.compile(r"^(?:[\d,]+(?:\.\d+)?%?|—|–|-|\*)$")
FOOTNOTE = re.compile(r"^(?:\(\d+\)\s*)+(?:†+|\*+)?$|^†+$|^\(\d+$|^\)$")
LEADER = re.compile(r"^[.\s]+$")


def _doc_soup(doc):
    if getattr(doc, "_soup", None) is None:
        from bs4 import BeautifulSoup
        doc._html = read_html(doc.path)
        doc._soup = BeautifulSoup(doc._html, "lxml")
    return doc._soup


def _style_pt(style, key):
    m = re.search(r"(?<![-\w])" + key + r":\s*(-?[\d.]+)pt", style or "")
    return float(m.group(1)) if m else None


def _box_cells(box):
    """[(y, (left, right) of the cell box, text)] for every piece of text on a Workiva page."""
    out = []
    for s in box.find_all(string=True):
        t = s.strip()
        if not t or LEADER.match(t):
            continue
        chain, e = [], s.parent
        while e is not None and e is not box:
            chain.append(e)
            e = e.parent
        y = sum(_style_pt(c.get("style"), "top") or 0.0 for c in chain)
        cell = None
        for i, c in enumerate(chain):
            st = c.get("style") or ""
            w = _style_pt(st, "width")
            if c.name == "div" and w is not None and _style_pt(st, "left") is not None:
                left = sum(_style_pt(a.get("style"), "left") or 0.0 for a in chain[i:])
                cell = (round(left, 1), round(left + w, 1))
                break
        if cell is None:
            x = sum(_style_pt(c.get("style"), "left") or 0.0 for c in chain)
            cell = (round(x, 1), round(x + 600, 1))  # loose text: treat as a label
        out.append((round(y, 1), cell, t))
    return out


def _lines_of(items):
    rows = {}
    for y, cell, t in items:
        key = next((k for k in rows if abs(k - y) < 1.5), y)
        rows.setdefault(key, []).append((cell, t))
    return [(y, sorted(rows[y])) for y in sorted(rows)]


def _grid_lines(table):
    """The same shape for an HTML <table>: a line per <tr>, each cell's (first, last+1) grid column, with
    colspan and rowspan honoured. The first column holds the names, so it is given the full width."""
    out, taken = [], {}  # taken: row -> set of grid columns filled by a rowspan from above

    def num(v):
        return int(v) if str(v or "").isdigit() else 1
    for i, tr in enumerate(table.find_all("tr")):
        col, cells = 0, []
        for td in tr.find_all(["td", "th"]):
            while col in taken.get(i, ()):
                col += 1
            span, down = num(td.get("colspan")), num(td.get("rowspan"))
            for r in range(i + 1, i + down):
                taken.setdefault(r, set()).update(range(col, col + span))
            t = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
            if t:
                cells.append(((col, col + span) if col > 0 else (0, 1000), t))
            col += span
        out.append((i, cells))
    return out


def _is_value_cell(cell, text, wide):
    return (cell[1] - cell[0]) < wide and bool(CELL_NUMBER.match(text.replace(" ", "")))


def _read_holder_lines(lines, wide):
    """Split one page's lines into (header cells, data lines). A data line has a value in a narrow cell."""
    header, data, started = [], [], False
    for y, cells in lines:
        vals = [(c, t) for c, t in cells if _is_value_cell(c, t, wide) or (t == "%" and (c[1] - c[0]) < wide)]
        label_parts = [t for c, t in cells if (c, t) not in vals]
        if not started:
            if any(re.search(r"Beneficially Owned|Beneficial Owner\b|^Number$|^#$|^Percent$", t)
                   or (t.isupper() and re.search(r"BENEFICIALLY OWNED|BENEFICIAL OWNER\b", t)) for _, t in cells):
                started = True
                header.extend(cells)
            continue
        if re.match(r"^(?:_{3,}|\*\s*(?:Represents|Less|Indicates))", " ".join(t for _, t in cells)):
            break
        vals = [(c, t) for c, t in vals if t != "%"]  # a column's header says it is a percentage
        if not vals:
            narrow = [t for c, t in cells if (c[1] - c[0]) < wide and not FOOTNOTE.match(t)]
            if not data and narrow:
                header.extend(cells)  # still the header: it has text over the columns
                continue
            if all(FOOTNOTE.match(t) for t in label_parts):
                continue  # a footnote mark printed on a line of its own
            data.append((y, " ".join(label_parts), []))
            continue
        data.append((y, " ".join(label_parts), vals))
    return header, data


def _columns_from_values(lines, wide):
    """Fallback when the header cells are too wide to be columns (Rezera, Nov 2026: each title spans four
    grid cells over spacer cells). The columns are where the numbers sit; each is named by every header
    cell printed above it."""
    first = next((i for i, (_, cells) in enumerate(lines) if any(_is_value_cell(c, t, wide) for c, t in cells)), None)
    if first is None:
        return [], []
    header = [ct for _, cells in lines[:first] for ct in cells]
    _, data = _read_holder_lines([(-1, [((0, 1), "Beneficially Owned")])] + lines[first:], wide)
    spans = sorted({c for _, _, vals in data for c, t in vals})
    cols = []
    for sp in spans:
        mid = (sp[0] + sp[1]) / 2
        above = " ".join(t for c, t in header if c[0] <= mid <= c[1] and not FOOTNOTE.match(t))
        if above:
            cols.append({"span": sp, "head": above, "own": above})
    # one share-count column beside %-before and %-after columns: the count is the holding before the offering
    if any(re.search(r"\bAfter\b", c["head"], re.I) for c in cols):
        for c in cols:
            if re.search(r"Number|Shares", c["head"], re.I) and not re.search(r"Percent|%|\bBefore\b|\bAfter\b|\bPrior\b", c["head"], re.I):
                c["head"] = c["own"] = c["head"] + " before the offering"
    return cols, data


def _leaves(header, wide):
    """Columns: header cells that hold no smaller header cell, narrower than the name column."""
    spans = sorted({c for c, t in header if (c[1] - c[0]) < wide and not FOOTNOTE.match(t)})
    leaves = []
    for s in spans:
        inner = [o for o in spans if o != s and o[0] >= s[0] - 0.5 and o[1] <= s[1] + 0.5]
        if not inner:
            leaves.append(s)
    out = []
    for s in leaves:
        mid = (s[0] + s[1]) / 2
        above = [t for c, t in header if c[0] - 0.5 <= mid <= c[1] + 0.5 and (c[1] - c[0]) < wide * 3
                 and not FOOTNOTE.match(t)]
        own = " ".join(t for c, t in header if c == s)
        out.append({"span": s, "head": " ".join(above), "own": own})
    return out


def _describe(leaf):
    head, own = re.sub(r"\s+", " ", leaf["head"]), re.sub(r"\s+", " ", leaf["own"])
    if re.search(r"Offered|to Be Sold|Being Offered|Sold in", head, re.I):
        stage = "offered_option" if re.search(r"Additional|Full Exercise", head, re.I) else "offered"
        kind = "shares"
    else:
        if re.search(r"\bAfter\b", head, re.I):
            stage = "after_option" if re.search(r"With Full|Full Exercise", head, re.I) and not re.search(r"Without", head, re.I) \
                else "after"
        elif re.search(r"\bBefore\b|\bPrior\b", head, re.I):
            stage = "before"
        else:
            stage = None
        if re.search(r"Voting|Power|†", head, re.I):
            kind = "votes"
        elif re.search(r"Outstanding", head, re.I):
            kind = "outstanding"
        elif re.search(r"%|Percent", own, re.I):
            kind = "pct"
        elif re.search(r"Number|#|Shares", own, re.I):
            kind = "shares"
        else:
            kind = None
    cls = re.search(r"Class [A-Z]\b", head)
    return {"stage": stage, "kind": kind, "class": cls.group(0) if cls else None, "header": clean(head)}


def _value(text):
    t = text.replace(" ", "").replace(",", "").rstrip("%")
    if t in ("—", "–", "-"):
        return 0
    if t == "*":
        return "<1"
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return None


def _parse_rows(data, cols, page, locate):
    """[(name, section, {column index: value})] from the data lines of one page."""
    rows, pending, section = [], "", ""
    for _, label, vals in data:
        label = re.sub(r"\(\s*\d+\s*\)\s*(?:†+)?|†+|\.{3,}", " ", label)
        label = re.sub(r"\s+", " ", label).strip(" .")
        if not vals:
            if label.endswith(":"):
                section, pending = label.rstrip(":"), ""
            elif label:
                pending = (pending + " " + label).strip()
            continue
        name = label
        if pending:
            name = (pending + " " + label).strip()
            pending = ""
        cells = {}
        for cell, t in vals:
            i = locate(cell)
            if i is not None and i not in cells:
                cells[i] = t
        values = {i: _value(t) for i, t in cells.items()}
        rows.append({"name": name, "section": section, "values": values, "page": page, "cols": cols})
    return rows


def _holder_tables(doc):
    """Read the ownership table on every page of the section: (columns, rows) or None."""
    pages = doc.section("principal")
    if not pages:
        return None, []
    soup = _doc_soup(doc)
    from .pages import page_boxes, html_chunks
    boxes = page_boxes(soup)
    cols, rows = None, []
    if boxes:
        if len(boxes) == len(doc.pages):
            box_of = {p["seq"]: boxes[p["seq"] - 1] for p in pages}
        else:  # a pages.json written by an older splitter: find each page's box by its printed number
            from .tables import positioned_lines, _page_number
            want = {p["page"]: p["seq"] for p in pages}
            box_of = {}
            for b in boxes:
                n = _page_number(positioned_lines(b))
                if n in want and want[n] not in box_of:
                    box_of[want[n]] = b
        for p in pages:
            if p["seq"] not in box_of:
                continue
            items = _box_cells(box_of[p["seq"]])
            header, data = _read_holder_lines(_lines_of(items), wide=150)
            leaves = _leaves(header, wide=150) if header else []
            if len(leaves) >= 2:
                cols = leaves
            if not cols or not data:
                continue

            def locate(cell, cols=cols):
                mid = (cell[0] + cell[1]) / 2
                return next((i for i, c in enumerate(cols) if c["span"][0] - 1 <= mid <= c["span"][1] + 1), None)
            rows += _parse_rows(data, cols, p["page"], locate)
    else:
        from bs4 import BeautifulSoup
        chunks = html_chunks(doc._html)
        if len(chunks) != len(doc.pages):
            return None, []
        for p in pages:
            part = BeautifulSoup(chunks[p["seq"] - 1], "lxml")
            for table in part.find_all("table"):
                if not re.search(r"Beneficially|Beneficial Owner", table.get_text(" "), re.I):
                    continue
                grid = _grid_lines(table)
                header, data = _read_holder_lines(grid, wide=4)
                leaves = _leaves(header, wide=4) if header else []
                if len(leaves) < 2:
                    leaves, data = _columns_from_values(grid, wide=4)
                if len(leaves) >= 2:
                    cols = leaves
                if not cols or not data:
                    continue

                def locate(cell, cols=cols):
                    return next((i for i, c in enumerate(cols) if c["span"][0] <= cell[0] < c["span"][1]), None)
                rows += _parse_rows(data, cols, p["page"], locate)
    return cols, rows


def _pct(v):
    return float(v) if isinstance(v, (int, float)) else None


def principal_holders(doc):
    """The ownership table as numbers: shares and % of each class before and after the offering, % of
    the vote, % of all shares outstanding where printed, shares sold. "<1" in `under_1pct` marks a "*"."""
    pages = doc.section("principal")
    if not pages:
        return NOT_FOUND, None
    cols, rows = _holder_tables(doc)
    if not cols or not rows:
        return {"status": "not read", "page": pages[0]["page"],
                "note": "The ownership table's columns could not be read from this filing's layout."}, None
    metas = {}

    def meta_of(cs):
        return metas.setdefault(id(cs), [_describe(c) for c in cs])
    meta = meta_of(rows[0]["cols"])
    every = [m for r in rows for m in meta_of(r["cols"])]
    classes_ = sorted({m["class"] for m in every if m["kind"] in ("shares", "pct") and m["stage"] in ("before", "after")
                       and m["class"]}) or ["Common stock"]
    single = len(classes_) == 1
    out, seen, sub_of = [], set(), ""
    for r in rows:
        name = r["name"]
        if re.match(r"^(?:Total|Shares subject to)", name):
            name = f"{sub_of}: {name[0].lower() + name[1:]}" if sub_of else name
        else:
            sub_of = name
        if name in seen or not name:
            continue
        seen.add(name)
        item = {"name": name, "section": r["section"], "classes": {}, "votes_pct_before": None, "votes_pct_after": None,
                "page": r["page"]}
        under = []
        for i, m in enumerate(meta_of(r["cols"])):
            v = r["values"].get(i)
            if v is None or m["kind"] is None:
                continue
            key = m["stage"] or ""
            if m["kind"] in ("shares", "pct") and m["stage"] in ("before", "after", "after_option"):
                c = item["classes"].setdefault(m["class"] or classes_[0], {"shares": None, "shares_after": None, "pct_before": None, "pct_after": None})
                field = {("shares", "before"): "shares", ("shares", "after"): "shares_after",
                         ("shares", "after_option"): "shares_after_option", ("pct", "before"): "pct_before",
                         ("pct", "after"): "pct_after", ("pct", "after_option"): "pct_after_option"}[(m["kind"], m["stage"])]
                c[field] = _pct(v) if m["kind"] == "pct" else (v if isinstance(v, int) else None)
                if v == "<1":
                    under.append(f"{m['class'] or classes_[0]} {field}")
            elif m["kind"] == "votes" and key in ("before", "after"):
                item[f"votes_pct_{key}"] = _pct(v)
                if v == "<1":
                    under.append(f"votes_pct_{key}")
            elif m["kind"] == "outstanding" and key in ("before", "after"):
                item[f"outstanding_pct_{key}"] = _pct(v)
                if v == "<1":
                    under.append(f"outstanding_pct_{key}")
            elif m["kind"] == "shares" and key.startswith("offered"):
                item["shares_offered" if key == "offered" else "shares_offered_option"] = v if isinstance(v, int) else None
        if under:
            item["under_1pct"] = under
        if re.search(r"as a group", name, re.I):
            item["is_group"] = True
        # the fields the dashboard already shows (strings, as before)
        if single:
            c = item["classes"].get(classes_[0], {})
            item["pct_before"] = _pct_text(c.get("pct_before"), f"{classes_[0]} pct_before" in under)
            item["pct_after"] = _pct_text(c.get("pct_after"), f"{classes_[0]} pct_after" in under)
            item["votes_pct"] = None
        else:
            item["pct_before"] = item["pct_after"] = None
            item["votes_pct"] = _pct_text(item["votes_pct_after"], "votes_pct_after" in under)
        out.append(item)
    columns = {"classes": classes_, "columns": meta, "page": rows[0]["page"]}
    columns["has"] = sorted({f"{m['kind']} {m['stage']}" for m in meta if m["kind"]})
    blank = [o["name"] for o in out if not any(
        v is not None for c in o["classes"].values() for k, v in c.items() if k.startswith("pct"))
        and o["votes_pct_after"] is None and not o.get("under_1pct")]
    if blank:
        columns["note"] = (f"{len(blank)} of {len(out)} rows print no percentages in this version "
                           "(the filing leaves them blank).")
    return out, columns


def _pct_text(v, under=False):
    if under:
        return "<1%"
    if v is None:
        return None
    return "none" if v == 0 else f"{v:g}%"


SHARES_OF = re.compile(r"(no|[\d,]{5,}|one) shares? of (?:our )?(?:(Class [A-Z]) )?common stock", re.I)


def _outstanding(doc):
    """Shares outstanding by class before and after the offering, as the ownership section states them."""
    before, after, added = {}, {}, {}
    for page, s in sents(doc.section("principal")):
        if not re.search(r"based|percentage ownership|calculation", s, re.I):
            continue
        is_after = re.search(r"after (?:this|the) offering", s, re.I) and not re.search(r"before (?:this|the) offering|prior to", s, re.I)
        is_before = re.search(r"before (?:this|the) offering|prior to (?:this|the) offering", s, re.I)
        cut = s.find("sale of")
        head, tail = (s[:cut], s[cut:]) if cut >= 0 else (s, "")
        if re.search(r"(?:\bon|\band|,)\s+shares of (?:our )?(?:Class [A-Z] )?common stock", head):
            continue  # a count left blank in this version: the totals cannot be used
        pairs = [(m.group(1), m.group(2) or "Common stock") for m in SHARES_OF.finditer(head)]
        nums = {c: (0 if n.lower() == "no" else 1 if n.lower() == "one" else int(n.replace(",", ""))) for n, c in pairs}
        if is_before and not before and nums:
            before = dict(nums, page=page)
            if re.search(r"after (?:this|the) offering", s, re.I):
                for m in SHARES_OF.finditer(tail):
                    if m.group(1)[0].isdigit():
                        added[m.group(2) or "Common stock"] = int(m.group(1).replace(",", ""))
        elif is_after and not after:
            if nums:
                after = dict(nums, page=page)
            else:
                for m in SHARES_OF.finditer(tail):
                    if m.group(1)[0].isdigit():
                        added[m.group(2) or "Common stock"] = int(m.group(1).replace(",", ""))
                if added:
                    after = {"page": page}
    if before and not any(k != "page" for k in after) and added:
        after = {c: v for c, v in before.items() if c != "page"}
        for c, v in added.items():
            after[c] = after.get(c, 0) + v
        after["page"] = before["page"]
        after["derived"] = "before plus the shares sold in this offering"
    return before, after


def wedge(doc, holders, columns):
    """The top voting holder: share of all shares outstanding versus share of the vote."""
    if not isinstance(holders, list) or not holders:
        return {"status": "not read"}
    if columns and len(columns["classes"]) == 1 and not any(m["kind"] == "votes" for m in columns["columns"]):
        return {"status": "single class", "note": "One class, one vote a share: shares held and votes held are the same."}
    people_ = [h for h in holders if not h.get("is_group") and ":" not in h["name"]]
    stage = "after" if any(h["votes_pct_after"] for h in people_) else "before"
    top = max(people_, key=lambda h: h[f"votes_pct_{stage}"] or 0)
    votes = top[f"votes_pct_{stage}"]
    if not votes:
        return {"status": "not read", "note": "The table prints no voting-power figures in this version."}
    out = {"holder": top["name"], "stage": stage, "votes_pct": votes, "votes_page": top["page"]}
    printed = top.get(f"outstanding_pct_{stage}")
    before, after = _outstanding(doc)
    totals = after if stage == "after" else before
    field = "shares_after" if stage == "after" else "shares"
    held = {c: (v.get(field) if v.get(field) is not None else v.get("shares")) for c, v in top["classes"].items()}
    total = sum(v for c, v in totals.items() if c not in ("page", "derived") and isinstance(v, int))
    if total and all(isinstance(v, int) for v in held.values()) and held:
        out.update(economic_pct=round(100 * sum(held.values()) / total, 1), economic_page=totals.get("page"),
                   economic_source="computed", shares_held=sum(held.values()), shares_outstanding=total,
                   note="Shares held over all shares outstanding; the holder's shares include any options it can "
                        "exercise within 60 days, which the outstanding count does not.")
        if printed is not None:
            out["economic_pct_printed"] = printed
    elif printed is not None:
        out.update(economic_pct=printed, economic_page=top["page"], economic_source="table")
    else:
        out.update(economic_pct=None, economic_page=None, economic_source=None,
                   shares_held=sum(v for v in held.values() if isinstance(v, int)) or None,
                   note="Total shares outstanding are not printed in this version, so the share of all shares "
                        "cannot be computed.")
    return out


# ---------- control: who decides, and for how long ----------

def _fact(s, m=None):
    """A statement of fact: no hypothetical word ahead of the match (or in the sentence)."""
    head = s[:m.end()][-100:] if m else s
    return not HYPOTHETICAL.search(head) and not re.search(r"\bif\b", head, re.I)


ELECTS = re.compile(r"\belect\w*\b[^.]{0,160}?(?:a majority of (?:the |our )?(?:authorized )?(?:members of )?(?:our )?(?:board|directors)"
                    r"|51% of the (?:total number of )?(?:authorized )?directors|all (?:of )?(?:the|our) directors)", re.I)
SUNSET = re.compile(r"(?:(?:all|each)(?: of our| outstanding)* (?:share|shares) of (?:our )?(Class [A-Z]) common stock[^.]{0,140}?"
                    r"(?:will|shall) (?:convert automatically|automatically convert|be redeemed)"
                    r"|(Class [A-Z]) common stock will remain outstanding until)", re.I)
SUNSET_WHEN = re.compile(r"anniversary|years? (?:following|after)|death|incapacity|no longer|Transition Period|fewer than|"
                         r"falls? below|less than \d|months following", re.I)


def control(doc):
    body = sents(doc.body())
    out = {}
    # controlled company
    ctrl = next(((p, s) for p, s in body
                 for m in [re.search(r"\bwe (?:are|will be|are considered|will be considered|expect to be|qualify as) "
                                     r"(?:considered )?an? “?controlled company”?", s, re.I)] if m and _fact(s, m)), None)
    if ctrl:
        p, s = ctrl
        ex = re.search(r"Nasdaq|NYSE|New York Stock Exchange", s)
        rely = next(((pg, x) for pg, x in body if re.search(r"controlled company", x, re.I)
                     and re.search(r"\b(?:intend to|expect to|will|currently|do not expect to|elect to) (?:rely|take advantage|avail)", x, re.I)
                     and not re.search(r"\bif\b|\bmay\b|\bcould\b|\bmight\b", x, re.I)), None)
        item = found(value=True, page=p, text=s, exchange=ex.group(0) if ex else None)
        if rely:
            item["exemption"] = {"text": clean(rely[1])[:600], "page": rely[0]}
        out["controlled_company"] = item
    else:
        maybe = next(((p, s) for p, s in body if re.search(r"controlled company", s, re.I)), None)
        out["controlled_company"] = found(value=False, page=maybe[0] if maybe else None, text=maybe[1] if maybe else None,
                                          note="No sentence says it is a controlled company"
                                               + ("; the quoted one only says it could become one." if maybe else "."))
    # who elects the majority of the board
    hit = next(((p, s) for p, s in body for m in [ELECTS.search(s)] if m and _fact(s, m) and "•" not in s[:m.start()]), None)
    out["board_majority"] = found(page=hit[0], text=hit[1]) if hit else NOT_FOUND
    # dual-class sunset
    pages = doc.section("capital") + doc.section("summary") + doc.body()
    seen, quotes = set(), []
    for p, s in sents(pages):
        m = SUNSET.search(s)
        if m and SUNSET_WHEN.search(s[m.start():]) and "•" not in s and "Sunset Time Class" not in s and len(s) < 900 \
                and _fact(s, m) and norm(s)[:150] not in seen:
            seen.add(norm(s)[:150])
            quotes.append({"class": m.group(1) or m.group(2), "text": clean(s)[:700], "page": p})
        if len(quotes) >= 3:
            break
    if quotes:
        out["sunset"] = {"value": True, "quotes": quotes, "page": quotes[0]["page"]}
    else:
        transfer = next(((p, s) for p, s in sents(doc.section("capital"))
                         if re.search(r"convert automatically|automatically convert", s, re.I) and re.search(r"transfer|sale", s, re.I)), None)
        out["sunset"] = {"value": False, "status": "none found",
                         "note": "No time or event sunset found; the high-vote shares convert only when sold or transferred."
                         if transfer else "No conversion or sunset terms found.",
                         **({"text": clean(transfer[1])[:600], "page": transfer[0]} if transfer else {"page": None})}
    # public benefit corporation
    pbc = next(((p, s) for p, s in body for m in [re.search(r"\b(?:we are|incorporated as) an? (?:Delaware )?public benefit corporation", s, re.I)]
                if m and _fact(s, m)), None)
    out["public_benefit_corporation"] = found(value=True, page=pbc[0], text=pbc[1]) if pbc else found(value=False, page=None)
    return out


# ---------- the auditor ----------

AUDIT_FIRM = r"([A-Z][A-Za-z&.,’' ]{1,45}?(?:LLP|L\.L\.P\.|P\.C\.|LLC|Oy|AG|S\.A\.))"


def _firm(name):
    """'GRANT THORNTON LLP' -> 'Grant Thornton LLP'; short words (KPMG, BDO, USA, LLP) stay capitals."""
    name = re.sub(r"\s+", " ", name).strip()
    if name.isupper():
        name = " ".join(w if len(w.strip(".,")) <= 4 else w.capitalize() for w in name.split())
    return name


def auditor(doc):
    """The firm that signs the latest audit report (the page that says how long it has served), else the
    firm the Experts section names."""
    fpages = [p for p in doc.pages if p["page"].startswith("F-")][:12]
    for p in fpages:
        text = re.sub(r"\s+", " ", p["text"])
        since = re.search(r"served as the Company[’']s auditor since (\d{4})", text)
        sig = re.search(r"/s/\s*" + AUDIT_FIRM, text)
        if since and sig:
            name = _firm(sig.group(1))
            others = []
            for q in fpages:
                for m in re.finditer(r"/s/\s*" + AUDIT_FIRM, re.sub(r"\s+", " ", q["text"])):
                    o = _firm(m.group(1))
                    if norm(o) != norm(name) and o not in [x["name"] for x in others]:
                        others.append({"name": o, "page": q["page"]})
            out = {"name": name, "page": p["page"], "since": int(since.group(1))}
            if others:
                out["other_reports"] = others
            return out
    for p, s in sents(doc.body()):
        m = re.search(r"(?:audited by|report of) " + AUDIT_FIRM, s)
        if m and re.search(r"expert", s + p, re.I) or (m and re.search(r"independent registered public accounting firm", s)):
            return {"name": m.group(1).strip(), "page": p, "text": clean(s)[:500]}
    return NOT_FOUND


# ---------- people ----------

NAME = (r"[A-Z][^\W\d_.’'\-“”]*[\w.’'\-“”]*(?:\s+(?:[A-Z][\w.’'\-“”]*|de|van|von|der|da|del|la|le)){1,4}"
        r"(?:,\s*(?:[A-Z][A-Za-z.]{0,9}|Ph\.D\.|M\.D\.))*\**")  # degrees after a comma (", M.D., Ph.D.") and footnote stars
EXEC_WORDS = re.compile(r"Chief|President|Officer|Secretary|Counsel|Treasurer|Executive|Head|Vice|Controller|Founder", re.I)


def _name_age_pages(doc):
    """Body pages that print a 'Name / Age / Position' table header."""
    out = []
    for p in doc.body():
        lines = [l.strip() for l in p["text"].split("\n") if l.strip()]
        if any(re.match(r"^Name\b", l, re.I) and re.search(r"\bAge\b", " ".join(lines[k:k + 3]), re.I)
               for k, l in enumerate(lines)):
            out.append(p)
    return out


TITLE_WORDS = re.compile(r"Chief|President|Officer|Secretary|Counsel|Treasurer|Executive|Head|Vice|Controller|Founder|"
                         r"Director|Chair|Manager|Partner|Member|Trustee|Principal|Lead", re.I)
HEADER_BITS = re.compile(r"^(?:Name(?: and)?|Address|Age|Positions?(?:\(s\))?(?: Held.*)?|Title|Held Since|Position Held Since|"
                         r"Year Term|Term|Expires|Director Since|\(\d+\)|\*+|Mutual .*|.*Bank)$", re.I)


def _people_by_age(lines, page):
    """A second reader for tables that spread one person over several lines (LIS, Blue Laser Fusion, MFB
    Bancorp, Holvek, Nov 2026): each two-digit age line is a person; the lines after it that read as a
    title are the title, the lines before it since the last title are the name."""
    people, name, title, group, cur = [], [], [], None, None
    def close():
        if cur is not None:
            cur["title"] = re.sub(r"\s+", " ", " ".join(title)).strip(" ,")
            people.append(cur)
    for line in lines:
        if len(line) > 140 or re.search(r"\b(?:has served|has been|serves as|joined (?:us|the)|is our)\b", line):
            break  # the biographies begin
        if re.fullmatch(r"(?:19|20)\d\d|\(\d+\)(?:\(\d+\))*", line) or HEADER_BITS.match(line):
            continue
        if cur is not None and title and title[-1].rstrip().endswith((",", " and", "&", " of")):
            title.append(line)  # "... Treasurer and" / "Director": the title runs on, it is no heading (Holvek)
            continue
        if re.match(r"^(?:Executive Officers?|Officers|Management|Significant Employees|Key Employees)(?: and Directors?)?:?$", line, re.I):
            group = "exec"
            continue
        if re.match(r"^(?:Non-Employee |Independent |Other )?Directors?(?: Nominees)?:?$", line, re.I):
            group = "dir"
            continue
        if re.fullmatch(r"\d{2}", line):
            close()
            nm = " ".join(name).strip()
            cur = {"name": nm.rstrip("*").strip(), "age": int(line), "page": page, "group": group} if nm else None
            name, title = [], []
            continue
        if cur is not None and not title and TITLE_WORDS.search(line):
            title.append(line)
            continue
        if cur is not None and title and (TITLE_WORDS.search(line) or line[:1].islower() or title[-1].rstrip().endswith((",", "and", "of", "&"))):
            title.append(line)
            continue
        if cur is not None and title:
            close()
            cur, title = None, []
        if re.search(r"\d", line):
            continue  # an address beside the name (Holvek)
        name.append(line)
    if cur is not None:
        close()
    ok = [p for p in people if p["title"] and re.fullmatch(r"(?:(?:Mr|Ms|Mrs|Dr|Mdm|Prof)\.\s+)?[A-Z][^\d]{1,70}", p["name"])
          and len(p["name"].split()) >= 2]
    execs, dirs = [], []
    for p in ok:
        rec = {"name": p["name"], "title": p["title"], "age": p["age"], "page": p["page"]}
        is_exec = p["group"] == "exec" or (p["group"] is None and EXEC_WORDS.search(p["title"]))
        if is_exec:
            execs.append(rec)
        if not is_exec or re.search(r"Director|Chair", p["title"]):
            dirs.append({"name": p["name"], "age": p["age"], "page": p["page"], "title": p["title"]})
    return execs, dirs


def people(doc):
    sec = doc.section("management")
    filed = filing_date(doc)
    departures = people_leaving(doc, filed)
    # the table often sits on the page before the section's first page (SeeQC, Simwon, Focus Media), and
    # some filings give no Management entry the reader can map (Hometown Financial): then any page with a
    # Name / Age / Position header is tried
    before = [p for p in doc.pages if sec and p["seq"] == sec[0]["seq"] - 1]
    pages = before + sec[:3]
    pages += [p for p in _name_age_pages(doc) if p not in pages]
    for i, p in enumerate(pages[:8]):
        lines = [l.strip() for l in p["text"].split("\n")]
        head = next((k for k, l in enumerate(lines)
                     if re.match(r"^Name\b", l, re.I) and re.search(r"\bAge\b", " ".join(lines[k:k + 3]), re.I)), None)
        if head is None:
            continue
        execs, dirs, group = [], [], None
        body = [l for l in lines[head + 1:] if l and not re.fullmatch(r"(?:\(\d+\))+", l)]
        joined = []  # "Mr." printed on its own line above the name (Focus Media, Nov 2026)
        for l in body:
            if joined and re.fullmatch(r"(?:Mr|Ms|Mrs|Mdm|Dr|Prof)\.?", joined[-1]):
                joined[-1] = joined[-1] + " " + l
            else:
                joined.append(l)
        body = joined
        k = 0
        while k < len(body):
            line = body[k]
            if re.match(r"^_{3,}|^\*|^\(\d\)\s+\w", line) or len(line) > 140:
                break
            if re.match(r"^(?:Position|Age|Following|Electing)", line, re.I):
                k += 1
                continue
            m = re.match(rf"^({NAME})\s*(?:\(\d+\))*\s+(\d{{2}})\s+(.+)$", line)
            if not m and re.fullmatch(NAME, line) and k + 2 < len(body) and re.fullmatch(r"\d{2}", body[k + 1]):
                m = re.match(rf"^({NAME})\s+(\d{{2}})\s+(.+)$", f"{line} {body[k + 1]} {body[k + 2]}")
                k += 2
            if m:
                name, age = m.group(1).strip().rstrip("*").strip(), int(m.group(2))
                title = re.sub(r"\s+Class(?:es)? [A-Z](?:,? (?:and )?[A-Z])*$", "", m.group(3)).strip()
                is_exec = group == "exec" or (group is None and EXEC_WORDS.search(title))
                rec = {"name": name, "title": title, "age": age, "page": p["page"]}
                if is_exec:
                    execs.append(rec)
                if not is_exec or re.search(r"Director|Chair", title):
                    dirs.append({"name": name, "age": age, "page": p["page"], "title": title})
            elif (execs or dirs) and (len(line) > 60 or re.search(r"Management Directors|Biographical", line)):
                break  # the biographies begin
            elif re.match(r"^(?:Significant|Key|Other) Employees", line, re.I):
                group = "exec"  # a sub-heading inside the same table, never the start of the biographies
            elif re.match(r"^(?:Executive Officers|Management|Executive|Officers)", line, re.I):
                if execs or dirs:
                    break  # a second "Executive Officers" heading opens the biographies
                group = "exec"
            elif re.match(r"^(?:Non-Employee|Directors?|Independent|Director Nominees)", line, re.I):
                group = "dir"
            elif execs or dirs:
                break
            k += 1
        e2, d2 = _people_by_age(body, p["page"])
        n2, n1 = len({x["name"] for x in e2 + d2}), len({x["name"] for x in execs + dirs})
        if n2 > n1 or (n2 == n1 and len(e2) + len(d2) > len(execs) + len(dirs)):
            execs, dirs = e2, d2  # the line-by-line reader found more of the table
        if execs or dirs:
            return {"executives": execs or NOT_FOUND, "directors": dirs or NOT_FOUND, "departures": departures}
    return {"executives": NOT_FOUND, "directors": NOT_FOUND, "departures": departures}


# ---------- risk factors ----------

def _emphasised_runs(html, mode="bi"):
    """Emphasised passages in document order: bold-and-italic ("bi", how the first four filers set a risk
    heading), bold only ("b") or italic only ("i"), for filers that set their headings another way."""
    import lxml.html
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
    root = lxml.html.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", html))  # an XML declaration line (SeeQC, Nov 2026)
    runs = []

    def state(el, b, i):
        tag = el.tag.lower() if isinstance(el.tag, str) else ""
        if tag in ("b", "strong"):
            b = True
        if tag in ("i", "em"):
            i = True
        style = (el.get("style") or "").lower() if tag else ""
        m = re.search(r"font-weight:\s*([a-z0-9]+)", style)
        if m:
            b = m.group(1) in ("bold", "bolder", "600", "700", "800", "900")
        m = re.search(r"font-style:\s*([a-z]+)", style)
        if m:
            i = m.group(1) in ("italic", "oblique")
        return b, i

    def walk(el, b, i):
        if not isinstance(el.tag, str):
            return
        b, i = state(el, b, i)
        pick = (b and i) if mode == "bi" else b if mode == "b" else i
        if el.text:
            runs.append((el.text, pick))
        for c in el:
            walk(c, b, i)
            if c.tail:
                runs.append((c.tail, (b and i) if mode == "bi" else b if mode == "b" else i))
    walk(root, False, False)

    out, cur = [], []
    for text, emph in runs:
        t = text.replace("\xa0", " ")
        if not t.strip():
            if cur:
                cur.append(" ")
            continue
        if emph:
            cur.append(t)
        elif t.strip() == "Table of Contents" or PAGE_NUMBER.match(t.strip()):
            continue  # a page break inside a heading
        else:
            if cur:
                out.append(clean("".join(cur)))
            cur = []
    if cur:
        out.append(clean("".join(cur)))
    return out


def risk_headings(doc):
    pages = doc.section("risk")
    if not pages:
        return None
    html = read_html(doc.path)
    texts = [(p["page"], norm(p["text"])) for p in pages]
    best = []
    for mode in ("bi", "b", "i"):
        found_ = _risk_headings_in(_emphasised_runs(html, mode), texts)
        if len(found_) > len(best):
            best = found_
        if len(best) >= 5:
            break
    return best


GROUP_TITLE = re.compile(r"^Risks? (?:Related|Relating) to .{3,90}?(?:(?<=[a-z])(?=[A-Z][a-z])|\s+(?=(?:Our|We|The|If|A|An|Any|"
                         r"Because|There|In|As|Changes|Future|Increases|Competition|Economic|Strong|Recent|Higher|Rising)\b))")


def _risk_headings_in(runs, texts):
    out, at, seen = [], 0, set()
    for h in runs:
        h = GROUP_TITLE.sub("", h)  # a bold group title run into the first heading (bank filings, Nov 2026)
        if not (40 <= len(h) <= 1200 and re.search(r"[.?]”?$", h)):
            continue
        key = norm(h)[:60]
        if len(key) < 30 or key in seen:
            continue
        for j in range(at, len(texts)):
            if key in texts[j][1]:
                out.append({"heading": h, "page": texts[j][0]})
                seen.add(key)
                at = j
                break
    return out


def risks(doc, prev_path=None):
    heads = risk_headings(doc)
    if not heads or len(heads) < 5:
        return {"count": NOT_FOUND, "headings": NOT_FOUND, "new_since_last_version": NOT_FOUND}
    out = {"count": len(heads), "headings": heads[:25]}
    if prev_path:
        old = risk_headings(Doc(prev_path)) or []
        if len(old) >= 5:
            olds = [norm(o["heading"]) for o in old]
            new, reworded = [], []
            for h in heads:
                n = norm(h["heading"])
                if n in olds:
                    continue
                close = [(SequenceMatcher(None, n, o).ratio(), k) for k, o in enumerate(olds)
                         if abs(len(n) - len(o)) < 0.3 * len(n)]
                best = max(close, default=(0, None))
                if best[0] >= 0.85:  # the same risk with words edited
                    reworded.append(dict(h, before=old[best[1]]["heading"], before_page=old[best[1]]["page"]))
                else:
                    new.append(h)
            out["new_since_last_version"] = new
            out["reworded_since_last_version"] = reworded
            out["compared_with"] = Path(prev_path).name
        else:
            out["new_since_last_version"] = {"status": "not found", "note": "Headings of the previous version could not be read."}
    else:
        out["new_since_last_version"] = {"status": "first filing", "note": "No earlier version on file to compare."}
    return out


# ---------- related parties, legal, employees ----------

def related_party(doc):
    pages = doc.section("related")
    if not pages:
        return {"items": NOT_FOUND}
    items, seen = [], set()
    for page, s in sents(pages):
        s = clean(s)
        letters = sum(ch.isalpha() or ch == " " for ch in s)
        if 60 <= len(s) <= 360 and "___" not in s and letters > 0.8 * len(s) and re.search(r"\$\s?[\d.,]+\s*(?:million|billion)?", s) \
                and not re.search(r"\b(?:may|might|could)\b|amount involved|\$120,000", s):
            k = norm(s)[:80]
            if k not in seen:
                seen.add(k)
                items.append({"text": s, "page": page})
        if len(items) >= 6:
            break
    return {"items": items or NOT_FOUND}


def legal(doc):
    pages = doc.section("business") or doc.body()
    for p in pages:
        lines = p["text"].split("\n")
        for j, line in enumerate(lines):
            if line.strip() == "Legal Proceedings":
                text = " ".join(lines[j + 1:])
                ss = [s for _, s in sents([{"page": p["page"], "text": text}])][:2]
                if ss:
                    return found(page=p["page"], text=" ".join(ss))
    return NOT_FOUND


def employees(doc):
    rx = re.compile(r"[Aa]s of ([A-Z][a-z]+ \d{1,2}\s?, \d{4})\s?, we (?:had|employed) (?:approximately |a total of |over )?"
                    r"([\d,]+) (?:full-time )?(?:employees|team members|people)")
    for pages in (doc.section("business"), doc.body()):
        for page, s in sents(pages):
            m = rx.search(clean(s))
            if m:
                return {"count": int(m.group(2).replace(",", "")), "as_of": m.group(1).replace(" ,", ","),
                        "text": clean(s)[m.start():][:400], "page": page}
    return NOT_FOUND


# ---------- all of it ----------

def previous_version(path):
    index = Path(path).parent.parent / "filings.json"
    if not index.exists():
        return None
    from .fetch import filing_path
    files = [filing_path(f["path"]) for f in json.loads(index.read_text())["filings"]]
    names = [Path(f).name for f in files]
    me = Path(path).name
    if me in names and names.index(me) > 0:
        prev = Path(path).parent / names[names.index(me) - 1]
        return str(prev) if prev.exists() else None
    return None


def owners(doc):
    holders, columns = principal_holders(doc)
    return {"classes": classes(doc), "principal_holders": holders, "holders_columns": columns,
            "wedge": wedge(doc, holders, columns), "control": control(doc)}


def vote_rules(doc):
    """How a founders' vehicle or a trust casts its votes, and voting proxies: the filing's own sentences."""
    keys = ("will vote as determined by", "vote as directed by", "voting proxy agreement", "irrevocable proxy")
    out, seen = [], set()
    for p in doc.pages:
        t = re.sub(r"\s+", " ", p.get("text", ""))
        low = t.lower()
        for k in keys:
            at = low.find(k)
            while at != -1 and len(out) < 6:
                a = max(t.rfind(". ", 0, at) + 2, at - 400, 0)
                b = t.find(". ", at)
                b = len(t) if b == -1 or b - at > 500 else b + 1
                sent = t[a:b].strip()
                key = sent[:120].lower()
                if len(sent) >= 40 and key not in seen:
                    seen.add(key)
                    out.append({"text": sent, "page": p.get("page")})
                at = low.find(k, at + len(k))
        if len(out) >= 6:
            break
    return out


def filing_kind(doc):
    """What kind of registration this is, so an empty screen can say why. A resale (shares that existing
    holders may sell, often from a company already listed) and a mutual bank's conversion print far less than
    an IPO prospectus does (Blue Laser Fusion, VCI Global, Hometown Financial, Nov 2026)."""
    front = re.sub(r"\s+", " ", " ".join(p["text"] for p in doc.pages[:5]))
    if re.search(r"mutual holding company", front, re.I) and re.search(r"\bconversion\b", front, re.I):
        return {"kind": "mutual conversion",
                "note": "A mutual bank converting to stock form: there were no shareholders before, and the shares "
                        "on offer are a range set by an independent appraisal, so the holder table and a single "
                        "share count after the offering do not exist yet."}
    whole = " ".join(p["text"] for p in doc.pages)
    if len(doc.pages) < 100 and len(re.findall(r"incorporat\w+ (?:herein )?by reference", whole, re.I)) >= 10 \
            and re.search(r"Form 20-F|Form 10-K", whole):
        return {"kind": "short form",
                "note": "A short-form registration from a company that already files annual reports: the financial "
                        "statements, management and owners are not printed here but incorporated by reference from "
                        "its annual and quarterly reports, so those screens stay empty."}
    resale = re.search(r"\bresale\b|offered by the selling (?:stock|share)holders identified|by the selling (?:stock|share)holders identified", front, re.I)
    ipo = re.search(r"initial public offering|this is our initial", front, re.I)
    if resale and not ipo:
        return {"kind": "resale",
                "note": "A resale registration: it lets existing holders sell shares they already own, and the "
                        "company raises little or nothing from it. It prints far less than an IPO prospectus, so "
                        "several screens stay empty."}
    return {"kind": "ipo"}


def _safe(fn, *args):
    """One section failing on an unusual filing must never empty every other section (SeeQC, Nov 2026:
    a crash in the risk headings blanked management, holders, the offer and the risks)."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - recorded on the dashboard as "not read", with the reason
        return {"status": "not read", "note": f"this section could not be read from this filing ({type(e).__name__})"}


def run(path):
    doc = Doc(path)
    result = {
        "filing": doc.path.name,
        "summary": _safe(summary, doc),
        "offer": _safe(offer, doc),
        "owners": _safe(owners, doc),
        "people": _safe(people, doc),
        "risks": _safe(risks, doc, previous_version(path)),
        "related_party": _safe(related_party, doc),
        "legal": _safe(legal, doc),
        "employees": _safe(employees, doc),
        "auditor": _safe(auditor, doc),
        "kind": _safe(filing_kind, doc),
    }
    if isinstance(result["owners"], dict) and "status" not in result["owners"]:
        result["owners"]["vote_rules"] = _safe(vote_rules, doc)
    return result


def main(path):
    result = run(path)
    out = Path(path).with_suffix(".qual.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=1, ensure_ascii=False)[:6000])
    return out


if __name__ == "__main__":
    main(sys.argv[1])
