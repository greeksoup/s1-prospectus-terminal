"""Write the dashboard: one HTML file per company that opens in any browser, offline.

Everything on it comes from the files the earlier stages saved. No AI was used to make it.
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboards"
LIB = ROOT / "library"  # the built data for every company read; kept in the repo so a fresh copy has them all


def sec_url(cik, f):
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['accession'].replace('-', '')}/{f['document']}"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def _trim_versions(versions, keep=6):
    out = []
    for v in versions:
        v = dict(v)
        v["sections"] = [dict(s, examples_added=s["examples_added"][:keep], examples_changed=s["examples_changed"][:keep],
                              examples_removed=s["examples_removed"][:3]) for s in v["sections"][:14]]
        out.append(v)
    return out


def bundle(index_path, latest, questions, flags, versions, others, stats, statements=None, qual=None, shares=None, metrics=None):
    index = json.loads(Path(index_path).read_text())
    cik = index["cik"]
    filings = [{"form": f["form"], "date": f["date"], "url": sec_url(cik, f)} for f in index["filings"]]
    name = re.sub(r"\s*\(([A-Z.\-]+)\)\s*$", "", index["name"]).strip()
    if name.isupper():  # EDGAR stores some names in capitals
        name = " ".join(w if w in ("LLC", "PBC", "LP", "PLC", "AG", "SA", "NV") else w.capitalize() for w in name.split())
    ticker = re.search(r"\(([A-Z.\-]+)\)\s*$", index["name"])
    ticker = ticker.group(1) if ticker else ""
    if not ticker:  # built from a CIK, EDGAR's name carries no ticker: take the filing's own, else the last build's
        t = ((qual or {}).get("offer") or {}).get("ticker") or {}
        ticker = t.get("value") if isinstance(t, dict) and isinstance(t.get("value"), str) else ""
    if not ticker and (LIB / f"{slug(name)}.json").exists():
        ticker = json.loads((LIB / f"{slug(name)}.json").read_text()).get("meta", {}).get("ticker", "")
    return {
        "meta": {
            "name": name, "ticker": ticker, "cik": cik,
            "filings": filings, "latest": filings[-1] if filings else None,
            "latest_file": Path(latest).name, "generated": datetime.now().strftime("%d %B %Y, %H:%M"),
            "stats": stats,
        },
        "q": questions, "flags": flags.get("flags", []), "versions": _trim_versions(versions), "others": others,
        "statements": statements or {}, "qual": qual or {}, "shares": shares or {}, "metrics": metrics or {},
    }


def write(data, save=True):
    OUT.mkdir(exist_ok=True)
    if save:
        LIB.mkdir(exist_ok=True)
        (LIB / f"{slug(data['meta']['name'])}.json").write_text(json.dumps(data, indent=0))
    path = OUT / f"{slug(data['meta']['name'])}.html"
    payload = json.dumps(data).replace("</", "<\\/")
    path.write_text(_template("dashboard.html").replace("__TITLE__", data["meta"]["name"]).replace("__DATA__", payload))
    write_index()
    return path


def redraw():
    """Redraw every dashboard with the current design: from library/ (the source of truth), and
    from any older dashboard that has no library file yet."""
    n, done = 0, set()
    for p in sorted(LIB.glob("*.json")) if LIB.exists() else []:
        d = json.loads(p.read_text())
        write(d, save=False)
        done.add(slug(d["meta"]["name"]))
        n += 1
    for p in OUT.glob("*.html"):
        if p.name == "index.html" or p.stem in done:
            continue
        m = re.search(r'const DATA = (\{.*?\});\n', p.read_text(), re.S)
        if m:
            write(json.loads(m.group(1).replace("<\\/", "</")))
            n += 1
    write_index()
    return n


def index_rows():
    """Every company already read, newest first (the front page and the Companies menu)."""
    rows = []
    for p in sorted(OUT.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        if p.name == "index.html":
            continue
        m = re.search(r'const DATA = (\{.*?\});\n', p.read_text(), re.S)
        if m:
            rows.append(_index_row(p, json.loads(m.group(1).replace("<\\/", "</"))))
    return rows


def write_index():
    """A front page listing every company already read, newest first."""
    rows = index_rows()
    (OUT / "index.html").write_text(_template("index.html").replace("__CARDS__", json.dumps(rows).replace("</", "<\\/")))


WEB = Path(__file__).resolve().parent / "web"


def _template(name):
    return (WEB / name).read_text()


def _tone_watch(f, converts):
    """Same rule as the page: silences, converting funding and non-cash losses are context."""
    if f.get("kind") == "silence":
        return False
    if converts and "Equity below zero" in f.get("title", ""):
        return False
    if f.get("kind") == "numbers" and re.search(r"not cash|turns into shares", f.get("title", ""), re.I):
        return False
    return True


def _index_row(p, d):
    meta, q = d["meta"], d.get("q", {})
    flags = d.get("flags", [])
    converts = any(re.search(r"turns into shares", f.get("title", ""), re.I) for f in flags)
    g = q.get("q1_growth", {})
    rev, revi = (g.get("revenue") or {}).get("values") or {}, (g.get("revenue_interim") or {}).get("values") or {}
    revenue = label = growth = None
    if revi and len(revi) >= 2:
        ks = sorted(revi, key=lambda k: k[-4:])
        a, b = ks[-2], ks[-1]
        revenue, label = revi[b], b
        if revi.get(a) and a.split()[0] == b.split()[0]:
            growth = (revi[b] / revi[a] - 1) * 100
    elif rev:
        k = sorted(rev)[-1]
        revenue, label, growth = rev[k], "FY" + k[2:], (g.get("growth_pct") or {}).get(k)
    pr = q.get("q5_price", {})
    price = ("$%g" % pr["price"]["value"]) if (pr.get("price") or {}).get("value") else \
        ("$%g–%g" % (pr["price_range"]["low"], pr["price_range"]["high"]) if pr.get("price_range") else "Not set")
    return {"file": p.name, "name": meta["name"], "ticker": meta["ticker"], "latest": meta["latest"],
            "versions": len(meta.get("filings", [])), "price": price, "revenue": revenue, "revenue_label": label,
            "growth": growth, "flags": len(flags), "watch": sum(_tone_watch(f, converts) for f in flags),
            "generated": meta["generated"], "pages": meta["stats"].get("pages"), "seconds": meta["stats"].get("seconds")}
