"""Find a company on SEC EDGAR and download its IPO registration filings.

Usage: python -m prospectus.fetch "Anthropic"   (or a ticker, or a CIK number)
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import os

# SEC asks every program to say who it is. Set S1_PROSPECTUS_TERMINAL_UA to "your-name your@email" if SEC ever refuses.
USER_AGENT = os.environ.get("S1_PROSPECTUS_TERMINAL_UA", "s1-prospectus-terminal/0.1 (open-source prospectus reader)")
REGISTRATION_FORMS = {"S-1", "S-1/A", "F-1", "F-1/A", "424B1", "424B4"}
DATA = Path(__file__).resolve().parent.parent / "data"


def filing_path(p):
    """A saved filing's path, found under this copy's data/ folder even when the index was written
    in a folder that has since moved or been renamed."""
    p = Path(p)
    if p.exists():
        return str(p)
    parts = p.parts
    if "data" in parts:
        alt = DATA.joinpath(*parts[len(parts) - parts[::-1].index("data"):])
        if alt.exists():
            return str(alt)
    return str(p)

# python.org's Python on a Mac ships without certificates; use certifi's when it is installed.
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=SSL_CONTEXT) as r:
        body = r.read()
    time.sleep(0.15)  # stay well under SEC's 10 requests a second
    return body


def find_company(query):
    """Return (cik, name) for a name, ticker or CIK."""
    if query.strip().isdigit():
        cik = int(query)
        sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
        return cik, sub["name"]
    url = "https://efts.sec.gov/LATEST/search-index?keysTyped=" + urllib.parse.quote(query)
    hits = json.loads(get(url))["hits"]["hits"]
    if not hits:
        raise SystemExit(f"No company on EDGAR matches '{query}'.")
    top = hits[0]
    return int(top["_id"]), top["_source"]["entity"]


def registration_filings(cik):
    """Every S-1/F-1 family filing, oldest first, including older pages of the history."""
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    tables = [sub["filings"]["recent"]]
    for extra in sub["filings"].get("files", []):
        tables.append(json.loads(get("https://data.sec.gov/submissions/" + extra["name"])))
    out = []
    for t in tables:
        for i, form in enumerate(t["form"]):
            if form in REGISTRATION_FORMS:
                out.append({
                    "form": form,
                    "date": t["filingDate"][i],
                    "accession": t["accessionNumber"][i],
                    "document": t["primaryDocument"][i],
                })
    return sorted(out, key=lambda f: (f["date"], f["accession"]))


def download(cik, filing):
    folder = DATA / str(cik) / "filings"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{filing['date']}_{filing['form'].replace('/', '-')}_{filing['accession']}.htm"
    path = folder / name
    if not path.exists():
        acc = filing["accession"].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{filing['document']}"
        path.write_bytes(get(url))
    filing["path"] = str(path)
    return filing


def main(query):
    cik, name = find_company(query)
    filings = registration_filings(cik)
    if not filings:
        raise SystemExit(f"{name} has no public S-1 or F-1 on EDGAR yet.")
    print(f"{name} (CIK {cik}): {len(filings)} registration filings")
    for f in filings:
        download(cik, f)
        print(f"  {f['date']}  {f['form']:<6} {f['accession']}")
    index = DATA / str(cik) / "filings.json"
    index.write_text(json.dumps({"cik": cik, "name": name, "filings": filings}, indent=2))
    return index


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "Anthropic")
