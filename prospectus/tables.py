"""Read the printed tables of a prospectus into rows of numbers, each with its page.

Two layouts exist:
- positioned pages (Workiva print layout, e.g. SpaceX): no <table> tags; every word sits at
  an x/y position, so rows are rebuilt from y and columns from x.
- ordinary HTML tables (e.g. Anthropic): <tr>/<td>, with "$" and ")" in cells of their own.

A table the code cannot read is reported as "not read", never as empty.
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

NUMBER = re.compile(r"^\(?-?\$?\s?[\d,]+(?:\.\d+)?\)?%?$|^—$|^-$")
YEAR = re.compile(r"^(?:19|20)\d\d$")
DIGIT_WIDTH = 5.0
# rows whose numbers are not dollars, so a "(in thousands)" page never rescales them
PER_SHARE = r"(?:income|loss|earnings|dividends?)\)? per share|^weighted[- ]average|^shares\b|^number of shares|%|\bratios?\b"
# "Basic" / "Diluted" lines printed under a per-share or share-count heading
SHARE_CHILD = r"^(?:basic|diluted)\b"


def _unscaled(label, heading):
    """Is this row a per-share figure or a share count, by its own name or the heading above it?"""
    return bool(re.search(PER_SHARE, label, re.I)
                or (heading and re.search(PER_SHARE, heading, re.I) and re.match(SHARE_CHILD, label, re.I)))


STATEMENT_TITLE = re.compile(r"balance sheets?|statements? of (?:operations|income|comprehensive|cash flows?|"
                             r"financial (?:position|condition)|profit (?:or|and) loss|loss|earnings)", re.I)


def thousands_scale(text):
    """0.001 when the page reports in thousands, so every figure ends up in $ millions.
    "(In millions, except share amounts which are in thousands)" is millions: the dollars decide.
    A financial statement page that names no unit at all and prints seven-digit figures is in whole
    dollars (Simwon America, Focus Media, Nov 2026), so it is scaled by a million."""
    if re.search(r"in\s+thousands", text, re.I) and not re.search(r"in\s+millions", text, re.I):
        return 0.001
    if re.search(r"in\s+millions", text, re.I):
        return 1.0
    head = [l.strip() for l in text.split("\n") if l.strip()][:8]
    if any(STATEMENT_TITLE.search(l) and len(l) < 120 for l in head) and re.search(r"\b\d{1,3}(?:,\d{3})+\b", text):
        return 0.000001
    return 1.0


def parse_number(token):
    t = token.replace("$", "").replace(",", "").replace(" ", "").strip()
    if t in ("—", "-", ""):
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").rstrip("%")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _offset(style, key):
    m = re.search(r"(?<![-\w])" + key + r":\s*(-?[\d.]+)pt", style or "")
    return float(m.group(1)) if m else 0.0


def _page_number(lines):
    from .pages import PAGE_NUMBER
    for _, words in reversed(lines):
        if len(words) == 1 and PAGE_NUMBER.match(words[0][1]):
            return words[0][1]
    return "unnumbered"


def positioned_lines(box):
    """Every piece of text on a page with its absolute (y, x)."""
    items = []
    for s in box.find_all(string=True):
        text = s.strip()
        if not text or set(text) <= set(". "):
            continue
        x = y = 0.0
        e = s.parent
        while e is not None and e is not box:
            st = e.get("style")
            x += _offset(st, "left")
            y += _offset(st, "top")
            e = e.parent
        items.append((round(y, 1), x, text))
    rows = {}
    for y, x, t in items:
        # words a fraction of a point apart vertically belong to the same printed line
        key = next((k for k in rows if abs(k - y) < 1.5), y)
        rows.setdefault(key, []).append((x, t))
    return [(y, sorted(rows[y])) for y in sorted(rows)]


CONNECTOR = re.compile(r"(?:[,;]|\b(?:of|and|or|the|as|for|to|in|at|on|by|with|from|net|less|including))$", re.I)


def _continues(prev, nxt):
    """Does the printed line `prev` run on into `nxt` (one row name wrapped), rather than being a heading?"""
    if not nxt:
        return True
    return nxt[:1].islower() or nxt[:1] in "($" or nxt[:1].isdigit() or bool(CONNECTOR.search(prev.strip()))


def _blocks_from_lines(lines):
    """Group consecutive lines that carry a label plus numbers into one table."""
    blocks, current, gap = [], [], 0
    from .pages import PAGE_NUMBER
    for y, words in lines:
        if len(words) == 1 and PAGE_NUMBER.match(words[0][1]):
            continue  # the printed page number
        words = [(x, t) for x, t in words if t != "$"]
        # a year at the far left is the row's name (a maturity schedule), not a value
        if words and YEAR.match(words[0][1]) and words[0][0] < 200:
            words = [(words[0][0], words[0][1] + ":")] + words[1:]
        text_words = [(x, t) for x, t in words if not NUMBER.match(t)]
        label_end = max((x for x, _ in text_words), default=-1)
        # numbers inside a sentence are prose; table cells sit to the right of every word
        numbers = [(x, t) for x, t in words if NUMBER.match(t) and x > label_end]
        if numbers and all(YEAR.match(t) for _, t in numbers):
            numbers = []  # a row of years is a column heading, not data
        label = " ".join(t for x, t in text_words).rstrip(":")
        label = re.sub(r"\s+([’'),.;:])", r"\1", label)  # "shareholders ’ equity" -> "shareholders’ equity"
        if numbers:
            # a row name that wrapped over several printed lines: walk back while each line runs on into the next
            follow, last_y = label, y
            while current and not current[-1]["cells"] and current[-1]["label"] and last_y - current[-1]["y"] < 14 \
                    and _continues(current[-1]["label"], follow):
                prev = current.pop()
                follow, last_y = prev["label"], prev["y"]
                label = (prev["label"] + " " + label).strip()
        if numbers:
            current.append({"y": y, "label": label, "cells": numbers})
            gap = 0
        elif not current and label and len(label) < 140:
            pending = {"y": y, "label": label, "cells": []}
            current = [pending]
            gap = 1
        elif current and not any(r["cells"] for r in current):
            # still before the first number: keep a few lines, a long row name may be wrapping
            current = (current + [{"y": y, "label": label, "cells": []}])[-12:] if label and len(label) < 140 else []
        elif current:
            runs_on = bool(current[-1]["label"]) and not current[-1]["cells"] and _continues(current[-1]["label"], label)
            if label and (gap < 4 or runs_on) and len(label) < 95 and any(r["cells"] for r in current):
                current.append({"y": y, "label": label, "cells": []})  # a sub-heading, or one line of a wrapped name
                gap += 0 if runs_on else 1
            else:
                blocks.append(current)
                # a long line here may be the first half of a wrapped row name; keep it until the next line decides
                current = [{"y": y, "label": label, "cells": []}] if label and len(label) < 140 else []
                gap = 1
    if current:
        blocks.append(current)
    out = []
    for b in blocks:
        while b and not b[0]["cells"]:
            b = b[1:]  # leading lines that were not merged belong to the header
        if sum(1 for r in b if r["cells"]) >= 2:
            out.append(b)
    return out


def _columns(block):
    """Right edges of the columns, taken from the rows that fill every column."""
    width = max(len(r["cells"]) for r in block)
    full = [r for r in block if len(r["cells"]) == width]
    edges = []
    for i in range(width):
        rights = sorted(x + DIGIT_WIDTH * len(t) for r in full for (x, t) in [r["cells"][i]])
        edges.append(rights[len(rights) // 2])
    return edges


def _header(lines, top_y, edges):
    """Up to five lines above the table: the column titles, matched to columns by position."""
    above = [(y, w) for y, w in lines if top_y - 75 < y < top_y][-5:]
    above = [(y, w) for y, w in above if not any(len(t) > 60 for _, t in w)]  # body prose is not a heading
    titles = [[] for _ in edges]
    caption = []
    for _, words in above:
        for x, t in words:
            if x < edges[0] - 120:
                caption.append(t)
                continue
            centre = x + DIGIT_WIDTH * len(t) / 2
            i = min(range(len(edges)), key=lambda k: abs(edges[k] - DIGIT_WIDTH * 4 - centre))
            titles[i].append(t)
    return " ".join(caption), [" ".join(t) for t in titles]


def positioned_tables(box, seq):
    lines = positioned_lines(box)
    page = _page_number(lines)
    text = " ".join(t for _, w in lines for _, t in w)
    scale = thousands_scale(text)  # everything in $ millions
    tables = []
    for block in _blocks_from_lines(lines):
        edges = _columns(block)
        caption, titles = _header(lines, block[0]["y"], edges)
        rows, heading, prev_heading = [], "", False
        for r in block:
            values = [None] * len(edges)
            if not r["cells"]:  # a heading may wrap over two printed lines
                heading = (heading + " " + r["label"]) if prev_heading else r["label"]
            prev_heading = not r["cells"]
            per_share = _unscaled(r["label"], heading)
            for x, t in r["cells"]:
                right = x + DIGIT_WIDTH * len(t)
                i = min(range(len(edges)), key=lambda k: abs(edges[k] - right))
                v = parse_number(t)
                values[i] = round(v * scale, 6 if scale < 0.001 else 3) if (v is not None and not per_share) else v
            rows.append({"label": r["label"], "values": values})
        tables.append({"seq": seq, "page": page, "caption": caption, "columns": titles, "rows": rows})
    return tables


def html_tables(soup, page, scale=1.0):
    """Ordinary <table> markup on one printed page. `scale` turns thousands into millions."""
    out = []
    for table in soup.find_all("table"):
        rows, heading, notes_col = [], "", False
        for tr in table.find_all("tr"):
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c not in ("", "$", "%")]
            merged = []  # "(1,531" and ")" printed in separate cells
            for c in cells:
                if c in (")", ")%") and merged:
                    merged[-1] += ")"
                else:
                    merged.append(c)
            cells = [c[1:].strip() if c.startswith("$") else c for c in merged]
            cells = [c + ")" if re.match(r"^\([\d,.]+$", c) else c for c in cells]
            if not cells:
                continue
            label = cells[0] if not NUMBER.match(cells[0].replace(" ", "")) else ""
            nums = cells[1:] if label else cells
            values = [parse_number(c) for c in nums if NUMBER.match(c.replace(" ", ""))]
            if values and (not label or re.fullmatch(r"notes?", label, re.I) or (len(nums) >= 2 and not re.search(r"[a-z]", label)))\
                    and all(YEAR.match(c.replace(" ", "")) for c in nums):
                # a year row may carry the statement's title or "Notes" in its first cell (Windward Bio, Nov 2026)
                notes_col = notes_col or bool(label)  # "Notes 2025 2026": a column of note numbers sits left of the years
                rows.append({"label": "", "values": [], "raw": nums})  # a row of years is the heading
                continue
            if not values:
                heading = label
            if not _unscaled(label, heading):
                values = [round(v * scale, 6 if scale < 0.001 else 3) if v is not None else v for v in values]
            rows.append({"label": re.sub(r"\s+([’'),.;:])", r"\1", label), "values": values, "raw": nums})
        currency = _tidy_foreign(rows, notes_col)
        numeric = [r for r in rows if r["values"]]
        if len(numeric) < 2:
            continue
        first = rows.index(numeric[0])
        header = [" ".join([r["label"]] + r["raw"]).strip() for r in rows[:first]
                  if not all(CURRENCY.match(c) for c in ([r["label"]] if r["label"] else []) + (r.get("raw") or []))]
        width = max(len(r["values"]) for r in numeric)
        # headings printed between the column titles and the first figure ("Assets", "Current assets:")
        dated = [i for i, r in enumerate(rows[:first])
                 if r["raw"] or re.search(r"(?:19|20)\d\d|ended|unaudited|^(?:as of )?\w+ \d", r["label"], re.I)]
        lead = [r["label"] for r in rows[(dated[-1] + 1 if dated else 0):first] if r["label"]]
        out.append({
            "lead": lead,
            "page": page,
            "caption": "",
            "columns": _html_columns(header, width),
            "rows": [{"label": r["label"], "values": r["values"]} for r in rows[first:]],
            **({"currency": currency} if currency else {}),
        })
    return out


CURRENCY = re.compile(r"^(?:US\$|USD|\$|RMB|CNY|HK\$|HKD|SGD|S\$|MYR|RM|EUR|€|GBP|£|CHF|JPY|¥|AUD|A\$|CAD|C\$|TWD|NT\$|KRW|INR|ILS|SEK|DKK|NOK|THB|IDR|PHP|VND)$", re.I)


def _tidy_foreign(rows, notes_col):
    """Small foreign filers (Focus Media, Nov 2026) print a column of note numbers left of the figures,
    and a last column that repeats the latest year translated into US dollars. Drop both, so every row
    holds one value per period in the company's own currency, and return that currency when it is not
    the US dollar."""
    years = next((r["raw"] for r in rows if not r["values"] and r.get("raw") and not r["label"]), None)
    width = len(years) if years else None
    first_num = next((i for i, r in enumerate(rows) if r["values"]), len(rows))
    head_text = " ".join(" ".join([r["label"]] + (r.get("raw") or [])) for r in rows[:first_num])
    if not notes_col and re.search(r"\bnotes?\b", head_text, re.I):
        # "AS OF NOTES DECEMBER 31, 2025 DECEMBER 31, 2024" (Windward Bio, Nov 2026): the notes column is
        # named inside the header text, and the dates carry months, so the years are counted in the text
        notes_col = True
        width = width or len(re.findall(r"\b(?:19|20)\d\d\b", head_text)) or None
    if notes_col:
        # rows that cite a note are one value longer, and that first value is a small whole number
        lens = [len(r["values"]) for r in rows if r["values"]]
        longest = max(lens) if lens else 0
        longer = [r for r in rows if len(r["values"]) == longest]
        def note_like(r):
            raw = next((c for c in r.get("raw") or [] if re.match(r"^[\d(]", c)), "")
            return bool(re.fullmatch(r"\d{1,2}(?:\s*,\s*\d{1,2})*", raw.strip()))
        if width and longest == width + 1 or (longest - 1 in lens and longer and all(note_like(r) for r in longer)):
            for r in longer:
                r["values"] = r["values"][1:]
    first_num = next((i for i, r in enumerate(rows) if r["values"]), len(rows))
    codes = None
    for r in rows[:first_num]:
        cells = ([r["label"]] if r["label"] else []) + (r.get("raw") or [])
        if cells and all(CURRENCY.match(c) for c in cells):
            codes = cells
    if not codes or not width or len(codes) != width:
        return None
    usd = lambda c: c.upper() in ("US$", "USD", "$")
    if not usd(codes[0]) and usd(codes[-1]) and years[-1] == years[-2]:
        for r in rows:
            if len(r["values"]) == width:
                r["values"] = r["values"][:-1]
        if years:
            del years[-1]
        return codes[0].upper().replace("S$", "SGD")
    return None if usd(codes[0]) else codes[0].upper()


def _html_columns(header_lines, width):
    """Spread the header's years over the columns: 'Year Ended September 30, 2025 2024' -> one title each."""
    text = " ".join(header_lines)
    # "for the period from July 5, 2024, to December 31, 2024" is one column: only its end year counts
    text = re.sub(r"\bfrom\s+[A-Za-z]+\s+\d{1,2},?\s+(?:19|20)\d\d,?\s*(?:\([^)]*\)\s*)?(?:to|through)\b", "to", text, flags=re.I)
    years = re.findall(r"(?:19|20)\d\d", text)
    if len(years) >= width:
        years = years[-width:]
        lead = re.sub(r"(?:19|20)\d\d", "", text).strip()
        return [(lead + " " + y).strip() if i == 0 else y for i, y in enumerate(years)]
    return [text] * width


def read(path):
    from .pages import read_html
    html = read_html(path)
    soup = BeautifulSoup(html, "html.parser")
    from .pages import page_boxes
    boxes = page_boxes(soup)
    if boxes:
        tables = []
        for i, box in enumerate(boxes):
            tables.extend(positioned_tables(box, i + 1))
        return "positioned", tables
    from .pages import html_chunks, _number, _mark_financial_pages
    tables, labels = [], []
    for i, chunk in enumerate(html_chunks(html)):
        part = BeautifulSoup(chunk, "lxml")
        text = part.get_text("\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        scale = thousands_scale(text)  # everything in $ millions
        label = _number(lines) or "unnumbered"
        labels.append({"page": label, "text": "\n".join(lines[:40])})
        for t in html_tables(part, label, scale):
            t["_chunk"] = i
            tables.append(t)
    _mark_financial_pages(labels)  # the same F- labels the page splitter gives (bank filings)
    for t in tables:
        t["page"] = labels[t.pop("_chunk")]["page"]
    return "html", tables


def main(path):
    layout, tables = read(path)
    out = Path(path).with_suffix(".tables.json")
    out.write_text(json.dumps({"layout": layout, "tables": tables}))
    print(f"{layout} layout: {len(tables)} tables -> {out.name}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
