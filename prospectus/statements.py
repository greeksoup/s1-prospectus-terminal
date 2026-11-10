"""The three primary financial statements, every printed row, in the filing's own order and words.

run(path) -> {"income": ..., "balance": ..., "cashflow": ..., "units": "$ millions"}

Each statement: {"title", "pages", "columns" (oldest left), "rows": [{"label", "values", "kind", "indent"}]}
or {"status": "not read", "note": why}. Dollar rows are in $ millions (tables.py rescales thousands);
per-share rows carry "unit": "per share", share counts "unit": "shares" plus the "scale" they are printed in.
A blank cell is None: nothing is filled in. The auditor's report and the notes are never read.
"""
import json
import re
import sys

from .questions import STATEMENTS, Filing, head_lines, label, periods
from .tables import _continues

KINDS = {"income": "income", "balance": "balance", "cashflow": "cash"}
# the printed title line itself, e.g. "Condensed Consolidated Statements of Operations (continued)"
TITLE = r"^(?:unaudited\s+)?(?:interim\s+)?(?:condensed\s+)?(?:consolidated\s+)?(?:interim\s+)?(?:combined\s+)?(?:{})\b[^.]{{0,60}}$"
NOISE = re.compile(r"^(?:\(?[a-z0-9*]\)?|[_\W]*)$|accompanying notes|^see notes", re.I)
PER_SHARE = re.compile(r"per share|per unit", re.I)
SHARES = re.compile(r"^weighted[- ]average|^(?:number of )?shares\b", re.I)
CHILD = re.compile(r"^(?:basic|diluted)\b", re.I)
TOTAL = re.compile(r"^total (?:assets|liabilities\b.*(?:equity|deficit))|^net (?:income|loss|\(loss\)|earnings)"
                   r"(?: \(loss\)| \(income\))?$|^net cash (?:flows? )?(?:provided|used|from)|^comprehensive "
                   r"(?:income|loss)|end of (?:the )?(?:period|year)$", re.I)
SUBTOTAL = re.compile(r"^total\b|^net (?:income|loss|\(loss\)|earnings|cash|increase|decrease|change|revenue|sales)"
                      r"|^(?:increase|decrease|change) in cash|^gross (?:profit|margin)|^(?:income|loss|\(loss\)|operating)[\w ()]* from operations"
                      r"|^operating (?:income|loss)|before (?:provision for |benefit from )?(?:\(?benefit\)? ?)?"
                      r"(?:provision for )?income tax|^other comprehensive (?:income|loss)[\w ()]*$", re.I)


def _title(f, page, pattern):
    """The statement title printed at the top of this page, or None."""
    rx = re.compile(TITLE.format(pattern), re.I)
    for line in head_lines(f.page_text.get(page, ""), 8):
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 120 and rx.search(line):
            return line
    return None


def _same(a, b):
    norm = lambda t: re.sub(r"\(continued\)|\(unaudited\)|[^a-z ]", "", t.lower()).split()
    return norm(a) == norm(b)


def _groups(f, kind):
    """Statement page runs that open on the statement's own printed title. A run that only names the
    statement in prose (the auditor's report, a note) is dropped; a continuation page with a different
    statement's title (comprehensive loss, stockholders' equity) ends the run."""
    pat = STATEMENTS[kind].pattern
    any_title = "|".join(p.pattern for p in STATEMENTS.values()) + r"|stockholders|shareholders|members|equity|deficit"
    out = []
    for g in f.statement_groups(kind):
        start = next((i for i, p in enumerate(g) if _title(f, p, pat)), None)
        if start is None:
            continue
        title = _title(f, g[start], pat)
        pages = [g[start]]
        for p in g[start + 1:]:
            t = _title(f, p, any_title)
            if t and not _same(t, title):
                break
            pages.append(p)
        out.append((re.sub(r"\s*\((?:continued|unaudited)\)", "", title).strip(), pages))
    return out


def _page_scale_word(f, page):
    """What a share count on this page is printed in: thousands, millions, or plain units."""
    text = re.sub(r"\s+", " ", f.page_text.get(page, "")[:1500])
    if re.search(r"share (?:amounts|data|counts)[^)]{0,30}in thousands", text, re.I):
        return "thousands"
    if re.search(r"except (?:per share and )?shares?\b(?! data)|except share and per share", text, re.I):
        return "units"
    m = re.search(r"in (thousands|millions)", text, re.I)
    return m.group(1).lower() if m else "units"


def _lead_lines(f, page, first_label):
    """Headings printed above the first figure on a positioned page ("Assets", "Stockholders' deficit:").
    The table reader keeps only lines between figures, so these are read back from the page text: the
    lines straight above the first row, up to the column titles (anything with a digit stops the walk)."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in f.page_text.get(page, "").split("\n")]
    probe = first_label[:18]
    at = next((i for i, l in enumerate(lines) if probe and l.startswith(probe)), None)
    out = []
    i = (at or 0) - 1
    while at and i >= 0:
        l = lines[i]
        if not l or re.search(r"\d|ended|unaudited|in (?:millions|thousands)|^as of|table of contents|statements? of|"
                              r"balance sheets?", l, re.I) or len(l) > 100:
            break
        out.insert(0, l)
        i -= 1
    return out[-3:]


def _raw_rows(f, pages):
    """Every row on these pages with its period keys, headings kept; rows that cannot be lined up
    with the columns are counted, never guessed."""
    out, skipped, per, seen = [], 0, None, set()
    for t in f.tables:
        if t["page"] not in pages:
            continue
        p = periods(t, f.fy_month)
        per = p or per
        if per is None:
            continue
        keys = [label(k) for k in per]
        lead = t.get("lead")
        if lead is None and t["rows"] and t["page"] not in seen:
            lead = _lead_lines(f, t["page"], t["rows"][0]["label"])
        seen.add(t["page"])
        for lead in lead or []:
            out.append({"label": lead, "page": t["page"], "values": None})
        for r in t["rows"]:
            vals = r["values"]
            if not vals or all(v is None for v in vals):
                out.append({"label": r["label"], "page": t["page"], "values": None})
            elif len(vals) == len(keys):
                out.append({"label": r["label"], "page": t["page"], "values": dict(zip(keys, vals))})
            else:
                skipped += 1
    return out, skipped


def _clean(rows):
    """Drop footnote marks and rules, and join a row name that the reader left in pieces."""
    out = []
    for r in rows:
        lab = re.sub(r"\s+", " ", r["label"]).strip().rstrip(":").strip()
        if NOISE.search(lab) or (not lab):
            continue
        r = dict(r, label=lab)
        prev = out[-1] if out else None
        if prev and prev["page"] == r["page"]:
            # "and shares issued ... and" / "respectively": the rest of the row above
            if lab[:1].islower():
                prev["label"] += " " + lab
                if r["values"] and any(v is not None for v in r["values"].values()):
                    prev["values"] = r["values"]
                continue
            # two heading lines that are one heading: "Other comprehensive income" + "(loss)"
            if prev["values"] is None and r["values"] is None and _continues(prev["label"], lab):
                prev["label"] += " " + lab
                continue
        out.append(r)
    return out


def _shape(f, rows):
    """kind, indent and unit for each row."""
    out, heading, indented = [], "", False
    for r in rows:
        lab, vals = r["label"], r["values"]
        row = {"label": lab, "values": vals}
        if vals is None:
            row["kind"], row["indent"] = "header", 0
            # "Commitments and contingencies (Note 13)" is a pointer to a note, not a section heading
            heading, indented = lab, not re.match(r"commitments", lab, re.I)
            out.append(row)
            continue
        unit = None
        if SHARES.search(lab) or (CHILD.match(lab) and SHARES.search(heading)):
            unit = "shares"
        elif (PER_SHARE.search(lab) and not re.search(r"par value", lab, re.I)) or (CHILD.match(lab) and PER_SHARE.search(heading)):
            unit = "per share"
        if unit:
            row["unit"] = unit
            if unit == "shares":
                row["scale"] = _page_scale_word(f, r["page"])
            kind = "line"
        elif TOTAL.search(lab):
            kind = "total"
        elif SUBTOTAL.search(lab):
            kind = "subtotal"
        else:
            kind = "line"
        row["kind"] = kind
        row["indent"] = 1 if (kind == "line" and indented) else 0
        if kind != "line":
            indented = False
        out.append(row)
    return out


STOP = {"income", "loss", "losses", "expense", "expenses", "benefit", "credits", "gain", "gains", "net", "from",
        "for", "of", "the", "and", "provision", "total", "period", "year", "fiscal", "provided", "used", "by", "in"}


def _key(text):
    """A row's name with the words that flip between periods taken out: "Net income (loss)" and
    "Net loss" are one row; so are "Other income (expense), net" and "Other expense, net"."""
    t = text.lower()
    if re.search(r"\d", t):  # "net of allowance of $47 and $39 at March 31, 2026": the figures change, the row does not
        t = re.split(r"[,;(]", t)[0]
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\bbasic and diluted\b", "basic", t)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z]+", t) if w not in STOP]
    return " ".join(words) or "_net_"


def _merge(a, b):
    """Lay the interim statement's rows into the annual one by name, in printed order. A row printed
    in only one of them keeps blanks for the other's periods."""
    out = [dict(r, values=dict(r["values"]) if r["values"] else None) for r in a]
    pos = -1
    for r in b:
        hit = next((i for i in range(pos + 1, min(pos + 9, len(out)))
                    if _key(out[i]["label"]) == _key(r["label"]) and (out[i]["values"] is None) == (r["values"] is None)),
                   None)
        if hit is None:
            out.insert(pos + 1, dict(r))
            pos += 1
            continue
        pos = hit
        if re.search(r"\d", r["label"]):  # the later filing's wording carries the later dates
            out[hit]["label"] = r["label"]
        for k, v in (r["values"] or {}).items():
            out[hit]["values"].setdefault(k, v)
    return out


def _order(cols):
    def key(c):
        y = int(re.search(r"\d{4}", c).group())
        return (0 if c.isdigit() else 1, y, c)
    return sorted(cols, key=key)


def statement(f, kind):
    groups = _groups(f, kind)
    if not groups:
        return {"status": "not read", "note": "no page carrying this statement's printed title was found"}
    read = []
    for title, pages in groups:
        rows, skipped = _raw_rows(f, pages)
        rows = _clean(rows)
        if sum(1 for r in rows if r["values"]) >= 5:
            cols = {k for r in rows if r["values"] for k in r["values"]}
            read.append({"title": title, "pages": list(dict.fromkeys(r["page"] for r in rows)),
                         "rows": rows, "cols": cols, "skipped": skipped})
    if not read:
        return {"status": "not read", "note": "the statement pages were found but their columns could not be read"}
    main = read[0]
    # the interim set: the next statement run that brings periods the first one does not have
    extra = next((r for r in read[1:] if r["cols"] - main["cols"]), None)
    rows, pages, skipped = main["rows"], main["pages"], main["skipped"]
    if extra:
        rows = _merge(rows, extra["rows"])
        pages = pages + [p for p in extra["pages"] if p not in pages]
        skipped += extra["skipped"]
    columns = _order({k for r in rows if r["values"] for k in r["values"]})
    shaped = _shape(f, rows)
    for r in shaped:
        if r["values"] is not None:
            r["values"] = {c: r["values"].get(c) for c in columns}
        else:
            r["values"] = {c: None for c in columns}
    out = {"title": main["title"], "pages": pages, "columns": columns, "rows": shaped}
    if skipped:
        out["rows_not_aligned"] = skipped
    return out


def run(path):
    f = Filing(path)
    out = {name: statement(f, kind) for name, kind in KINDS.items()}
    text = " ".join(p["text"] for p in f.pages)
    if all(v.get("status") for v in out.values()) and re.search(r"incorporat\w+ (?:herein )?by reference", text, re.I) \
            and re.search(r"Annual Report on Form 10-K|Form 20-F", text):
        # a short S-1 from a company already listed (Exozymes, Nov 2026) points to its annual report instead
        for name in KINDS:
            out[name] = {"status": "incorporated by reference",
                         "note": "this filing does not print its financial statements; it incorporates them by reference "
                                 "from the company's annual and quarterly reports"}
    pages = {pg for v in out.values() if isinstance(v, dict) for pg in v.get("pages") or []}
    cur = next((t["currency"] for t in f.tables if t["page"] in pages and t.get("currency")), None)
    out["units"] = f"{cur} millions" if cur else "$ millions"
    if cur:
        out["currency"] = cur
    return out


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), indent=1)[:20000])
