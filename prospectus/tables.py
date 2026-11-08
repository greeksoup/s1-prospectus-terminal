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


def thousands_scale(text):
    """0.001 when the page reports in thousands, so every figure ends up in $ millions.
    "(In millions, except share amounts which are in thousands)" is millions: the dollars decide."""
    if re.search(r"in\s+thousands", text, re.I) and not re.search(r"in\s+millions", text, re.I):
        return 0.001
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
                values[i] = round(v * scale, 3) if (v is not None and not per_share) else v
            rows.append({"label": r["label"], "values": values})
        tables.append({"seq": seq, "page": page, "caption": caption, "columns": titles, "rows": rows})
    return tables


def html_tables(soup, page, scale=1.0):
    """Ordinary <table> markup on one printed page. `scale` turns thousands into millions."""
    out = []
    for table in soup.find_all("table"):
        rows, heading = [], ""
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
            if values and not label and all(YEAR.match(c.replace(" ", "")) for c in nums):
                rows.append({"label": "", "values": [], "raw": nums})  # a row of years is the heading
                continue
            if not values:
                heading = label
            if not _unscaled(label, heading):
                values = [round(v * scale, 3) if v is not None else v for v in values]
            rows.append({"label": re.sub(r"\s+([’'),.;:])", r"\1", label), "values": values, "raw": nums})
        numeric = [r for r in rows if r["values"]]
        if len(numeric) < 2:
            continue
        first = rows.index(numeric[0])
        header = [" ".join([r["label"]] + r["raw"]).strip() for r in rows[:first]]
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
        })
    return out


def _html_columns(header_lines, width):
    """Spread the header's years over the columns: 'Year Ended September 30, 2025 2024' -> one title each."""
    text = " ".join(header_lines)
    years = re.findall(r"(?:19|20)\d\d", text)
    if len(years) >= width:
        years = years[-width:]
        lead = re.sub(r"(?:19|20)\d\d", "", text).strip()
        return [(lead + " " + y).strip() if i == 0 else y for i, y in enumerate(years)]
    return [text] * width


def read(path):
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    from .pages import page_boxes
    boxes = page_boxes(soup)
    if boxes:
        tables = []
        for i, box in enumerate(boxes):
            tables.extend(positioned_tables(box, i + 1))
        return "positioned", tables
    from .pages import html_chunks, _number
    tables = []
    for chunk in html_chunks(html):
        part = BeautifulSoup(chunk, "lxml")
        text = part.get_text("\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        scale = thousands_scale(text)  # everything in $ millions
        tables.extend(html_tables(part, _number(lines) or "unnumbered", scale))
    return "html", tables


def main(path):
    layout, tables = read(path)
    out = Path(path).with_suffix(".tables.json")
    out.write_text(json.dumps({"layout": layout, "tables": tables}))
    print(f"{layout} layout: {len(tables)} tables -> {out.name}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
