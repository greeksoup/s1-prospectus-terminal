"""What changed between one version of the prospectus and the next.

A company files an S-1, then amendments (S-1/A), then the final prospectus (424B4). Each one is a
new photograph. This compares them section by section, sentence by sentence, and puts the
changes with numbers in them first: a price range filled in, a new risk, a restated figure.
"""
import difflib
import json
import re
import sys
from pathlib import Path

from .flags import sentences
from .questions import Filing

TOC_LINE = re.compile(r"^([A-Z][A-Z ,’'&\-/().]{3,90}?)\s+(\d{1,3}|F-1)$")
NUMBERED = re.compile(r"\$\s?[\d,.]+|\d+(?:\.\d+)?%|\b\d{1,3}(?:,\d{3})+\b")


def table_of_contents(filing):
    """[(section name, first printed page)] read from the prospectus's own contents page."""
    for p in filing.pages[:40]:
        lines = [l.strip() for l in p["text"].split("\n")]
        hits = [TOC_LINE.match(l) for l in lines]
        hits = [(m.group(1).strip(), m.group(2)) for m in hits if m]
        if len(hits) >= 8 and any("RISK FACTORS" in h[0] for h in hits):
            out = []
            for name, page in hits:
                if name.startswith("OF ") or name.startswith("AND "):
                    name = "MANAGEMENT’S DISCUSSION AND ANALYSIS"  # the long title wraps onto two lines
                out.append((name.title().replace("’S", "’s").replace("'S", "'s"), page))
            return out
    return []


def section_of(toc):
    starts = [(int(p), n) for n, p in toc if p.isdigit()]

    def which(page):
        if page.startswith("F-"):
            return "Financial Statements"
        if not page.isdigit():
            return "Cover and front pages"
        name = "Cover and front pages"
        for start, n in starts:
            if int(page) >= start:
                name = n
        return name
    return which


def _norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\(\d+\)$", "", s)


def sentences_by_section(filing):
    """Each section read as one continuous text (so a sentence broken by a page break stays whole),
    split into sentences, each remembering the printed page it starts on."""
    from .pages import PAGE_NUMBER
    which = section_of(table_of_contents(filing))
    streams = {}
    for p in filing.pages:
        lines = [l for l in p["text"].split("\n")
                 if l.strip() and l.strip() != "Table of Contents" and not PAGE_NUMBER.match(l.strip())]
        text = re.sub(r"\s+", " ", " ".join(lines))
        text = re.sub(r"\s+([’'),.;:])", r"\1", text)
        streams.setdefault(which(p["page"]), []).append((p["page"], text))
    out = {}
    for name, parts in streams.items():
        full, marks = "", []
        for page, text in parts:
            marks.append((len(full), page))
            full += text + " "
        pos = 0
        for piece in re.split(r"(?<=[.;])\s+(?=[A-Z(“\"])", full):
            start = full.find(piece, pos)
            pos = start + len(piece)
            letters = sum(ch.isalpha() for ch in piece)
            if 30 < len(piece) < 1500 and letters >= 0.5 * len(piece) and "____" not in piece:
                page = [pg for off, pg in marks if off <= start][-1]
                out.setdefault(name, {})[_norm(piece)] = page
    return out


def word_diff(before, after):
    """'up to [-additional-] {+83,333,333 additional+} shares': only the words that moved."""
    a, b = before.split(), after.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            chunk = a[i1:i2]
            out.append(" ".join(chunk if len(chunk) <= 8 else chunk[:3] + ["…"] + chunk[-3:]))
        else:
            if i2 > i1:
                out.append("[-" + " ".join(a[i1:i2]) + "-]")
            if j2 > j1:
                out.append("{+" + " ".join(b[j1:j2]) + "+}")
    return " ".join(out)


def price_of(filing):
    cover = re.sub(r"\s+", " ", "\n".join(p["text"] for p in filing.pages[:6]))
    fixed = re.search(r"(?:initial )?public offering price (?:is|of)\s*\$\s*(\d+(?:\.\d+)?)\s*per share", cover)
    if fixed:
        return f"${fixed.group(1)} per share"
    rng = re.search(r"between\s*\$\s*(\d+(?:\.\d+)?)\s*and\s*\$\s*(\d+(?:\.\d+)?)", cover)
    if rng:
        return f"${rng.group(1)} to ${rng.group(2)} per share"
    return "not disclosed"


def compare(a_path, b_path, limit=8):
    a, b = Filing(a_path), Filing(b_path)
    sa, sb = sentences_by_section(a), sentences_by_section(b)
    sections = []
    for name in list(dict.fromkeys(list(sb) + list(sa))):
        old, new = sa.get(name, {}), sb.get(name, {})
        added = [s for s in new if s not in old]
        removed = [s for s in old if s not in new]
        changed, pool = [], list(removed)
        if len(added) * max(len(pool), 1) < 400_000:
            for s in list(added):
                match = difflib.get_close_matches(s, pool, n=1, cutoff=0.8)
                if match and re.sub(r"[\s\-—]", "", match[0]) == re.sub(r"[\s\-—]", "", s):
                    pool.remove(match[0])  # only spacing or hyphenation moved: text extraction, not a change
                    added.remove(s)
                    continue
                if match:
                    changed.append({"before": match[0], "after": s, "page": new[s], "diff": word_diff(match[0], s)})
                    pool.remove(match[0])
                    added.remove(s)
            removed = pool
        if not (added or removed or changed):
            continue

        def rank(s):  # sentences carrying numbers first: that is where the information moves
            return (0 if NUMBERED.search(s) else 1, -len(s))
        sections.append({
            "section": name,
            "added": len(added), "removed": len(removed), "changed": len(changed),
            "examples_added": [{"text": s, "page": new[s]} for s in sorted(added, key=rank)[:limit]],
            "examples_changed": sorted(changed, key=lambda c: rank(c["after"]))[:limit],
            "examples_removed": [{"text": s, "page": old[s]} for s in sorted(removed, key=rank)[:limit // 2]],
        })
    sections.sort(key=lambda s: -(s["added"] + s["changed"] + s["removed"]))
    return {"from": a.path.name, "to": b.path.name,
            "price_from": price_of(a), "price_to": price_of(b), "sections": sections}


def run(index_path):
    index = json.loads(Path(index_path).read_text())
    from .fetch import filing_path
    files = [filing_path(f["path"]) for f in index["filings"]]
    return [compare(x, y) for x, y in zip(files, files[1:])]


def main(index_path):
    result = run(index_path)
    out = Path(index_path).with_name("versions.json")
    out.write_text(json.dumps(result, indent=2))
    for v in result:
        print(f"{v['from'][:22]} -> {v['to'][:22]}  price: {v['price_from']} -> {v['price_to']}")
        for s in v["sections"][:6]:
            print(f"   {s['section'][:40]:<40} +{s['added']} -{s['removed']} ~{s['changed']}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
