"""Operating detail from the prospectus: quarterly results, stock-based compensation, commitments
by year, and key business metrics where the company prints them as a table.

Every figure carries its printed page. A section the filing does not print is a "status" saying so;
nothing is estimated. Money is $ millions; KPI values stay in the unit the company prints.

run(path) -> {"quarterly", "sbc", "commitments", "key_metrics"}
"""
import json
import re
import sys
from pathlib import Path

from .questions import Filing
from .shares import clean_rows

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
MONTH_DAY = re.compile(r"(" + "|".join(MONTHS) + r")\s+\d{1,2}")
YEAR = re.compile(r"(?:19|20)\d\d")
NOT_PRINTED = "not printed in this filing"
NOT_READ = "not read"


def _front(page):
    return bool(re.match(r"^\d+$", page or ""))


def _norm(text):
    text = re.sub(r"\s+", " ", (text or "").replace("\xa0", " "))
    return re.sub(r"\s+([’'),.;:])", r"\1", text).strip()


# ---------- quarterly results ----------

def _quarter_labels(table):
    titles = [_norm(t) for t in table.get("columns") or []]
    width = max((len(r["values"]) for r in table["rows"]), default=0)
    if width < 4 or len(titles) < width:
        return None
    joined = " ".join(titles + [table.get("caption") or ""] + (table.get("lead") or []))
    months = MONTH_DAY.findall(" ".join(titles))
    years = []
    for t in titles[:width]:
        y = YEAR.findall(t)
        years.append(int(y[-1]) if y else None)
    if len(months) != width or None in years or not re.search(r"Three Months Ended|Quarterly", joined, re.I):
        return None
    dates = [(y, MONTHS.index(m) + 1) for m, y in zip(months, years)]
    return dates


def _is_percent_table(rows):
    rev = next((r for r in rows if re.match(r"^(Total )?revenues?$", r["label"], re.I)), None)
    vals = [v for v in (rev or {"values": []})["values"] if v is not None]
    return bool(vals) and len(set(vals)) == 1 and vals[0] in (100.0, 0.1)


def _quarterly(filing):
    tables = filing.tables
    for i, t in enumerate(tables):
        if not _front(t["page"]):
            continue
        dates = _quarter_labels(t)
        if not dates:
            continue
        rows = clean_rows(t["rows"])
        if _is_percent_table(rows) or not any(re.search(r"revenue", r["label"], re.I) and any(v is not None for v in r["values"])
                                                for r in rows):
            continue
        pages = [t["page"]]
        has_bottom = any(re.match(r"^Net (income|loss)", r["label"], re.I) for r in rows)
        nxt = tables[i + 1] if i + 1 < len(tables) else None
        if not has_bottom and nxt and nxt["page"] != t["page"] and _front(nxt["page"]) \
                and int(nxt["page"]) == int(t["page"]) + 1 and _quarter_labels(nxt) == dates:
            more = clean_rows(nxt["rows"])
            if not _is_percent_table(more):
                rows += more
                pages.append(nxt["page"])
        width = len(dates)
        order = sorted(range(width), key=lambda k: dates[k])  # oldest left
        labels = [f"{MONTHS[dates[k][1] - 1][:3]} {dates[k][0]}" for k in order]
        out_rows, revenue, section = [], None, ""
        for r in rows:
            vals = (list(r["values"]) + [None] * width)[:width]
            if not any(v is not None for v in vals):
                section = r["label"].rstrip(":")
                continue
            if re.match(r"^(Includes|Note:|\(in |Three Months)", r["label"]) or MONTH_DAY.search(r["label"]):
                continue
            if re.search(r"%|margin$", r["label"]) and not any(v for v in vals):
                continue
            values = {labels[j]: vals[k] for j, k in enumerate(order)}
            row = {"label": r["label"], "section": section, "values": values, "unit": "$M"}
            out_rows.append(row)
            if revenue is None and re.match(r"^(Total )?revenues?$", r["label"], re.I):
                revenue = values
        if revenue:
            for row in out_rows:
                row["pct_of_revenue"] = {c: (round(100 * v / revenue[c], 1) if v is not None and revenue.get(c) else None)
                                         for c, v in row["values"].items()}
        return {"columns": labels, "rows": out_rows, "pages": pages,
                "note": "three months ended on each date; % of revenue worked out here from the printed rows"}
    return {"status": NOT_PRINTED + " (no quarterly results table found)"}


# ---------- stock-based compensation ----------

def _period_labels(table, fy_month):
    from .questions import periods, label
    p = periods(table, fy_month)
    return [label(x) for x in p] if p else None


def _row(tables, pattern):
    for t in tables:
        for r in t["rows"]:
            if re.match(pattern, r["label"], re.I) and any(v is not None for v in r["values"]):
                return t, r
    return None, None


AMOUNT = r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion)?"
AWARD = r"(stock options|options|RSUs|restricted stock units|RSAs|restricted stock awards|PSUs|PRSUs|other outstanding equity awards|other equity awards)"


def _unrecognized(filing):
    items = []
    for p in filing.pages:
        text = _norm(p["text"])
        pos = 0
        for s in re.split(r"(?<=[a-z0-9)%])\.\s+(?=[A-Z(])", text):
            start = text.find(s, pos)
            pos = start + len(s)
            key = re.search(r"unrecognized|total remaining (?:share|stock)-based", s, re.I)
            if not key or "$" not in s \
                    or not re.search(r"compensation", s, re.I) or re.search(r"would have|tax benefit", s, re.I):
                continue
            dates = list(re.finditer(r"(?:As of|At) (" + "|".join(MONTHS) + r") (\d{1,2}), (\d{4})", s))
            date = ([d for d in dates if d.start() < key.start()] or dates or [None])[-1]
            if not date:
                continue
            years = re.findall(r"period of (?:approximately )?([\d.]+) years", s)
            # the figures belong to the sentence's own clause: "$X of unrecognized ..." or "unrecognized ... was $X"
            amounts = [a for a in re.finditer(AMOUNT, s) if a.start() >= key.start() - 25]
            for k, a in enumerate(amounts):
                after = s[a.end(): a.end() + 160]
                before = s[max(0, a.start() - 200): a.start()]
                kind = re.search(r"related to (?:our )?(?:unvested )?" + AWARD, after) or re.search(AWARD, before + " " + after)
                context = False
                if not kind:
                    # "the Company had $2.0 million of unrecognized ..." in a paragraph about one award type
                    found = list(re.finditer(AWARD, text[max(0, start - 1500):start]))
                    kind, context = (found[-1], True) if found else (None, False)
                if re.search(r"\band \$", s[a.start() - 6: a.start() + 1]) and "respectively" in s and k > 0 and not re.search(r"related to", after[:40]):
                    continue  # "$X and $Y, respectively": the second figure is the earlier date
                v = float(a.group(1).replace(",", "")) * (1000 if a.group(2) == "billion" else 1)
                items.append({"amount": v, "award": kind.group(1) if kind else "all awards", "award_from_context": context,
                              "as_of": f"{date.group(1)} {date.group(2)}, {date.group(3)}",
                              "date": (int(date.group(3)), MONTHS.index(date.group(1))),
                              "years": float(years[min(k, len(years) - 1)]) if years and (len(years) > k or len(years) == 1) else None,
                              "page": p["page"], "text": s[:400]})
    if not items:
        return {"unrecognized": None, "recognition_years": None, "status": NOT_PRINTED}
    latest = max(i["date"] for i in items)
    at = [i for i in items if i["date"] == latest]
    # the first page that states it carries the full split; other pages only add award types it did not cover
    first = at[0]["page"]
    chosen = [i for i in at if i["page"] == first]
    covers_all = any(re.search(r"other|all awards", i["award"]) for i in chosen)
    seen = {_award(i["award"]) for i in chosen}
    if not covers_all:
        for i in at:
            if _award(i["award"]) not in seen and not re.search(r"other|all awards", i["award"]):
                chosen.append(i)
                seen.add(_award(i["award"]))
    total = round(sum(i["amount"] for i in chosen), 3)
    yrs = None
    if all(i["years"] is not None for i in chosen):
        yrs = round(sum(i["amount"] * i["years"] for i in chosen) / total, 2) if total else None
    for i in items:
        i.pop("date")
    out = {"unrecognized": total, "recognition_years": yrs, "unrecognized_as_of": chosen[0]["as_of"],
           "unrecognized_page": chosen[0]["page"], "unrecognized_pages": sorted({i["page"] for i in chosen}),
           "built_from": [{k: i[k] for k in ("award", "amount", "years", "page")} for i in chosen],
           "items": items}
    if len(chosen) > 1:
        out["unrecognized_note"] = ("sum of the award types printed separately at the latest date"
                       + ("; years weighted by amount" if yrs is not None else "; not every type prints its years"))
    return out


def _award(name):
    n = name.lower()
    return "options" if "option" in n else "rsus" if ("rsu" in n or "restricted stock unit" in n) else \
        "rsas" if ("rsa" in n or "restricted stock award" in n) else "psus" if "psu" in n else n


def _sbc(filing):
    out = {"by_year": {}, "page": None, "pages": []}
    revenue = {}
    for group in filing.statement_groups("cash"):
        ts = [t for t in filing.tables if t["page"] in group]
        t, r = _row(ts, r"^(?:Stock|Share|Equity)-based compensation")
        if not r:
            continue
        labels = _period_labels(t, filing.fy_month)
        if not labels or len(labels) != len(r["values"]):
            continue
        for lab, v in zip(labels, r["values"]):
            if v is not None and lab not in out["by_year"]:
                out["by_year"][lab] = v
        out["pages"].append(t["page"])
        out["page"] = out["page"] or t["page"]
    for group in filing.statement_groups("income"):
        ts = [t for t in filing.tables if t["page"] in group]
        t, r = _row(ts, r"^(?:Total )?(?:net )?revenues?$")
        if not r:
            continue
        labels = _period_labels(t, filing.fy_month)
        if labels and len(labels) == len(r["values"]):
            for lab, v in zip(labels, r["values"]):
                revenue.setdefault(lab, v)
    if out["by_year"]:
        out["pct_of_revenue"] = {k: round(100 * v / revenue[k], 1) for k, v in out["by_year"].items() if revenue.get(k)}
        out["note"] = "from the cash flow statement; % of revenue worked out here"
    else:
        out["status"] = NOT_READ
    out.update(_unrecognized(filing))
    return out


# ---------- commitments ----------

COMMIT = re.compile(r"(?:purchase|unconditional|contractual|non-?cancel+able|capacity)[^.]{0,40}(?:obligations|commitments)", re.I)


def _commitments(filing):
    page_text = filing.page_text
    candidates = []
    for t in filing.tables:
        text = page_text.get(t["page"], "")
        if not COMMIT.search(text):
            continue
        rows = clean_rows(t["rows"])
        # layout 1: one row per year ("2026  $ 2,720")
        yrows = [r for r in rows if re.match(r"^(?:20\d\d|Thereafter|Total)", r["label"]) and r["values"] and r["values"][0] is not None]
        if sum(1 for r in yrows if re.match(r"^20\d\d", r["label"])) >= 3 \
                and not any(re.search(r"lease|imputed interest", r["label"], re.I) for r in rows):
            by = {re.sub(r":$", "", r["label"]): r["values"][0] for r in yrows if not r["label"].startswith("Total")}
            total = next((r["values"][0] for r in yrows if r["label"].startswith("Total")), None)
            candidates.append({"by_year": by, "total": total, "kind": _kind(text), "page": t["page"], "lines": []})
            continue
        # layout 2: years across the top, one row per kind of obligation
        cols = [_norm(c) for c in t.get("columns") or []]
        heads = [(YEAR.findall(c) or (["Thereafter"] if "Thereafter" in c else ["Total"] if "Total" in c else [None]))[-1] for c in cols]
        if sum(1 for h in heads if h and YEAR.match(h)) >= 3:
            lines = []
            for r in rows:
                if len(r["values"]) == len(heads) and sum(v is not None for v in r["values"]) >= 3:
                    lines.append({"label": r["label"], "by_year": {h: v for h, v in zip(heads, r["values"]) if h}})
            tot = next((l for l in lines if re.match(r"^Total$", l["label"])), None)
            if tot:
                by = {h: v for h, v in tot["by_year"].items() if h != "Total"}
                candidates.append({"by_year": by, "total": tot["by_year"].get("Total"), "kind": "contractual obligations (all lines)",
                                   "page": t["page"], "lines": lines})
    # prose: "$4.1 million (2026), and $3.0 million (2027)"
    if not candidates:
        for p in filing.pages:
            text = _norm(p["text"])
            m = re.search(r"((?:purchase|non-?cancel+able) commitments[^.]{0,300}?)((?:\$[\d.,]+ (?:million|billion) \((?:20\d\d)\),?\s*(?:and\s*)?){2,})", text, re.I)
            if m:
                by = {}
                for v, unit, y in re.findall(r"\$([\d.,]+) (million|billion) \((20\d\d)\)", m.group(2)):
                    by[y] = float(v.replace(",", "")) * (1000 if unit == "billion" else 1)
                candidates.append({"by_year": by, "total": round(sum(by.values()), 3), "kind": "purchase commitments",
                                   "page": p["page"], "lines": [], "note": "total worked out here from the printed years"})
                break
    if not candidates:
        return {"status": NOT_PRINTED + " (no commitments schedule by year found)"}
    best = sorted(candidates, key=lambda c: (not _front(c["page"]), filing.pages.index(next(p for p in filing.pages if p["page"] == c["page"]))))[0]
    if not best["lines"]:
        best.pop("lines")
    return best


def _kind(text):
    m = COMMIT.search(text)
    return _norm(m.group(0)).lower() if m else "commitments"


# ---------- key business metrics ----------

KPI = re.compile(r"subscribers|\bARPU\b|customers|retention|\bNRR\b|\bARR\b|recurring revenue|run-rate|mass to orbit|"
                 r"launches|compute draw|rings sold|paid members|members\b|users\b|gigawatts", re.I)


def _kpi_columns(titles, width):
    """Name each column from the header: interim columns first, then full years, as most S-1 tables print."""
    joined = " ".join(titles)
    years = []
    for t in titles[:width]:
        y = YEAR.findall(t)
        years.append(y[-1] if y else None)
    if None in years:
        return None
    interim = re.search(r"(Three|Six|Nine) Months Ended", joined, re.I)
    tag = {"three": "3M", "six": "6M", "nine": "9M"}[interim.group(1).lower()] if interim else None
    months = MONTH_DAY.findall(joined)
    if tag and not re.search(r"Years? Ended", joined, re.I) and len(months) == width:
        return [f"{m[:3]} {y}" for m, y in zip(months, years)]
    out, restart = [], not tag
    for i, y in enumerate(years):
        if not restart and i > 0 and int(y) >= int(years[i - 1]):
            restart = True
        out.append(y if restart else f"{tag} {y}")
    return out


def _unit(label):
    m = re.search(r"\((?:in )?([^)]*)\)\s*$", label)
    return m.group(1) if m else "count"


def _key_metrics_tables(filing):
    out, seen = [], set()
    for t in filing.tables:
        if not _front(t["page"]):
            continue
        rows = clean_rows(t["rows"])
        width = max((len(r["values"]) for r in rows), default=0)
        cols = None
        for r in rows:
            if not KPI.search(r["label"]) or re.search(r"\$|revenue|income|EBITDA|loss", r["label"], re.I):
                continue
            if sum(v is not None for v in r["values"]) < 2:
                continue
            cols = cols or _kpi_columns([_norm(c) for c in t.get("columns") or []], width)
            name = re.sub(r"\s*\([^)]*\)\s*$", "", r["label"]).strip()
            if not cols or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"label": name, "values": {c: v for c, v in zip(cols, r["values"]) if v is not None},
                        "unit": _unit(r["label"]), "page": t["page"]})
    return out


VALUE_LINE = re.compile(r"^\$?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|%)?$")


def _key_metrics_text(filing, have):
    """HTML filings print each KPI cell on its own line: 'Rings Sold', '3.1 million', '1.8 million', ..."""
    out = []
    for p in filing.pages:
        if not _front(p["page"]):
            continue
        lines = [l.strip() for l in p["text"].split("\n")]
        for i, l in enumerate(lines):
            if not re.match(r"^Operating Metrics$|^Key (?:Business|Operating) Metrics$", l):
                continue
            header = []
            for h in reversed(lines[max(0, i - 25):i]):
                if re.match(r"^(?:\(?(?:dollars|in) |Operating Metrics)", h):
                    continue
                if YEAR.fullmatch(h) or MONTH_DAY.match(h) or re.search(r"Months Ended|Years? Ended", h):
                    header.insert(0, h)
                elif header:
                    break
            j = i + 1
            while j < len(lines):
                label = lines[j]
                vals = []
                k = j + 1
                while k < len(lines) and VALUE_LINE.match(lines[k]):
                    vals.append(lines[k])
                    k += 1
                if len(vals) < 2:
                    if label == "Operating Metrics":
                        j += 1
                        continue
                    break
                years = [h for h in header if YEAR.fullmatch(h)]
                months = [h for h in header if MONTH_DAY.match(h)]
                if len(years) == len(vals) and len(months) == len(vals):
                    cols = [f"{m[:3]} {y}" for m, y in zip(months, years)]
                else:
                    cols = _kpi_columns([" ".join(header)] + years[1:], len(vals)) if len(years) == len(vals) else None
                    if cols and len(years) == len(vals):
                        cols = _kpi_columns([h for h in [" ".join(h for h in header if not YEAR.fullmatch(h)) + " " + years[0]] + years[1:]], len(vals))
                if cols and KPI.search(label):
                    parsed = [VALUE_LINE.match(v) for v in vals]
                    unit = parsed[0].group(2) or "count"
                    key = (label.lower(), tuple(cols))
                    if key not in have:
                        have.add(key)
                        values = {c: float(m.group(1).replace(",", "")) for c, m in zip(cols, parsed)}
                        if len(months) == len(vals):
                            values = dict(sorted(values.items(), key=lambda kv: (int(kv[0][-4:]), MONTHS.index(next(m for m in MONTHS if m.startswith(kv[0][:3]))))))
                        out.append({"label": label, "values": values, "unit": unit, "page": p["page"]})
                j = k
    return out


def _key_metrics(filing):
    rows = _key_metrics_tables(filing)
    have = {(r["label"].lower(), tuple(r["values"])) for r in rows}
    rows += _key_metrics_text(filing, have)
    return rows


# ---------- run ----------

def run(path):
    filing = Filing(path)
    km = _key_metrics(filing)
    out = {
        "quarterly": _quarterly(filing),
        "sbc": _sbc(filing),
        "commitments": _commitments(filing),
        "key_metrics": km,
    }
    if not km:
        out["key_metrics_status"] = "no key metrics table found (any metrics are in prose only; see Ask)"
    return out


def main(path):
    out = run(path)
    dest = Path(path).with_suffix(".metrics.json")
    dest.write_text(json.dumps(out, indent=1))
    print(f"metrics -> {dest.name}")
    return dest


if __name__ == "__main__":
    main(sys.argv[1])
