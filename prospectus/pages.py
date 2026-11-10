"""Split a prospectus into its printed pages, each with the page number printed on it.

Filings made with Workiva (most large IPOs) put every printed page in its own 612x792pt box
(792x612pt when the page is printed landscape, e.g. a wide ownership table). The same filings also
draw a page-sized border as a 792pt-high background picture inside some pages; that is decoration,
not a page, and is skipped. Other filings mark page breaks with CSS; both are handled.

A page whose number cannot be read from its text (a full-page picture prints its number inside the
image) gets a number only when the pages around it prove it: between printed pages 211 and 232,
twenty unreadable pages are 212 to 231. Such a page carries "inferred": true. Anything else stays
"unnumbered", never guessed.
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

PAGE_BOX = re.compile(r"height:\s*(?:792|612)pt")
PAGE_NUMBER = re.compile(r"^(?:F-\d{1,3}|[A-Z]{1,3}-\d{1,3}|\d{1,3}|[ivxlc]{1,7})$")


def _pt(style, key):
    m = re.search(r"(?<![-\w])" + key + r":\s*([\d.]+)pt", style or "")
    return m.group(1) if m else None


def page_boxes(soup):
    """The printed pages of a Workiva filing, in order: a relatively positioned div of 612x792pt
    (portrait) or 792x612pt (landscape). The absolutely positioned 792pt border pictures that sit
    inside some pages are not pages."""
    out = []
    for d in soup.find_all("div", style=PAGE_BOX):
        st = d.get("style", "")
        if "position:relative" not in st.replace(" ", ""):
            continue
        if {_pt(st, "height"), _pt(st, "width")} == {"792", "612"}:
            out.append(d)
    return out


def _parts(number):
    """'212' -> ('', 212); 'F-7' -> ('F-', 7); roman numerals and anything else -> None."""
    m = re.match(r"^([A-Z]{1,3}-)?(\d{1,3})$", number or "")
    return (m.group(1) or "", int(m.group(2))) if m else None


def fill_between(numbers):
    """Number a run of unreadable pages only when the readable pages on both sides leave exactly
    that many numbers free. Returns (numbers, set of inferred indexes)."""
    numbers, inferred = list(numbers), set()
    i = 0
    while i < len(numbers):
        if numbers[i] is not None:
            i += 1
            continue
        j = i
        while j < len(numbers) and numbers[j] is None:
            j += 1
        before = _parts(numbers[i - 1]) if i > 0 else None
        after = _parts(numbers[j]) if j < len(numbers) else None
        if before and after and before[0] == after[0] and after[1] - before[1] - 1 == j - i:
            for k in range(i, j):
                numbers[k] = f"{before[0]}{before[1] + (k - i) + 1}"
                inferred.add(k)
        i = j
    return numbers, inferred


def _text(node):
    return re.sub(r"[ \t ]+", " ", node.get_text("\n")).strip()


def _number(lines):
    """The printed page number sits alone on one of the last few lines (sometimes the first)."""
    head = lines[:2]
    if any(l.strip().lower().endswith(".htm") for l in lines[:4]):
        head = []  # EDGAR's own header ("S-1/A", "1", "<file>.htm") opens the first chunk: its "1" is no page
    for line in list(reversed(lines[-4:])) + head:
        token = line.strip()
        if PAGE_NUMBER.match(token):
            return token
    return None


# Older filings write page-break-before: always; newer ones (M2 Compliance, 2026) the CSS3 form
# break-before: page. Either starts a new printed page.
BREAK = re.compile(r"<[^>]+(?:page-break-(?:before|after)\s*:\s*always|(?<![-\w])break-(?:before|after)\s*:\s*page)[^>]*>", re.I)


def html_chunks(html):
    """Cut the raw HTML at every element that forces a new printed page (filings without page boxes).
    A page-break-BEFORE starts the page at that element; a page-break-AFTER ends the page after it. Cutting
    at the start of a break-after element (Alopexx, SeeQC, Focus Media, Nov 2026) moved each page's printed
    number to the top of the next page, so every page was labelled with the previous page's number."""
    cuts = []
    for m in BREAK.finditer(html):
        tag = re.match(r"<\s*([a-zA-Z0-9]+)", m.group(0))
        name = tag.group(1).lower() if tag else ""
        # only a small break-after element (a paragraph holding the page number) is cut after; a break-after
        # DIV that wraps a whole page (Rezera) starts that page, so it is cut at its start as before
        if re.search(r"break-after\s*:\s*(?:always|page)", m.group(0), re.I) and name in ("p", "span", "font", "a", "b", "i"):
            end = html.find("</" + tag.group(1), m.end())
            if end != -1 and end - m.end() < 4000:
                close = html.find(">", end)
                cuts.append(close + 1 if close != -1 else m.start())
                continue
        cuts.append(m.start())
    cuts = sorted(set(c for c in cuts if 0 < c < len(html)))
    bounds = [0] + cuts + [len(html)]
    return [html[a:b] for a, b in zip(bounds, bounds[1:]) if b > a]



# Zero-width characters some filing agents put inside empty table cells and above titles (Rezera's S-1,
# Nov 2026: every row label read as blank and every statement went unread). They print as nothing, so
# they are removed before any reading; non-breaking spaces become ordinary spaces.
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]|&#(?:8203|8204|8205|8288|65279);|&#x(?:200b|200c|200d|2060|feff);", re.I)


def read_html(path):
    """A filing's HTML, with the invisible characters taken out."""
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    html = re.sub(r"^\s*<\?xml[^>]*\?>", "", html)  # an XML declaration line (SeeQC, Nov 2026)
    return _INVISIBLE.sub("", html)


def split(path):
    html = read_html(path)
    soup = BeautifulSoup(html, "lxml")
    boxes = page_boxes(soup)
    if not boxes:
        texts = [_text(BeautifulSoup(chunk, "lxml")) for chunk in html_chunks(html)]
        numbers = [None] * len(texts)
    else:
        # read the page in printed order (top to bottom) so the footer number is found where it is printed
        from .tables import positioned_lines, _page_number
        texts, numbers = [], []
        for b in boxes:
            lines = positioned_lines(b)
            texts.append("\n".join(" ".join(t for _, t in words) for _, words in lines))
            n = _page_number(lines)
            numbers.append(None if n == "unnumbered" else n)
    texts = [[l for l in text.split("\n") if l.strip()] for text in texts]
    numbers = [numbers[i] or _number(lines) for i, lines in enumerate(texts)]
    numbers, inferred = fill_between(numbers)
    pages = []
    for i, lines in enumerate(texts):
        page = {"seq": i + 1, "page": numbers[i] or "unnumbered", "text": "\n".join(lines)}
        if i in inferred:
            page["inferred"] = True
        pages.append(page)
    _mark_financial_pages(pages)
    return pages


FIN_START = re.compile(r"report of independent|independent auditor|balance sheets?|statements? of financial (?:condition|position)", re.I)


def _mark_financial_pages(pages):
    """Some filers (banks especially; Hometown Financial, Nov 2026) number the financial statements 1, 2, 3
    again after the main text, with no "F-" in front. Those pages are labelled F-1, F-2... so every reader
    knows they are the financial statements; the number printed on the page is kept as "printed"."""
    if any(p["page"].startswith("F-") for p in pages):
        return
    best = 0
    for i, p in enumerate(pages):
        n = p["page"]
        if n.isdigit() and int(n) > best:
            best = int(n)
        if n == "1" and best >= 30 and any(FIN_START.search(q["text"][:600]) for q in pages[i:i + 6]):
            for q in pages[i:]:
                m = q["page"]
                if q is not p and m == "1":
                    break  # numbering restarts again: a later section, not these statements
                if m.isdigit():
                    q["printed"], q["page"] = m, "F-" + m
            return


def main(path):
    pages = split(path)
    out = Path(path).with_suffix(".pages.json")
    out.write_text(json.dumps(pages))
    unnumbered = sum(p["page"] == "unnumbered" for p in pages)
    print(f"{len(pages)} pages, {unnumbered} without a readable number -> {out.name}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
