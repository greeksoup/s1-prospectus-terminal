"""Add a company from the browser: search SEC EDGAR, list the newest S-1 and F-1 filers, and read
the chosen company in the background while the page shows how far it has got.

The page calls these through serve.py; nothing here needs a terminal. One company is read at a
time (SEC asks for a gentle pace); a second pick waits its turn in the queue.
"""
import contextlib
import datetime as dt
import io
import json
import re
import sys
import threading
import time
import urllib.parse

from . import fetch

_lock = threading.Lock()
_jobs = {}          # cik -> {"cik", "name", "state": waiting|reading|done|failed, "step", "file", "error", "started", "ended"}
_queue = []
_worker = None
_recent_cache = {"at": 0, "rows": []}

SPAC = re.compile(r"\b(acquisition|capital)\s+corp", re.I)


def _short(entity):
    """'Rezera Inc.  (RZRA)  (CIK 0002141583)' -> ('Rezera Inc.', 'RZRA')"""
    name = re.sub(r"\s*\(CIK \d+\)\s*$", "", entity or "").strip()
    m = re.search(r"\s*\(([A-Z0-9.,\- ]{1,30})\)\s*$", name)
    ticker = ""
    if m:
        ticker, name = m.group(1).split(",")[0].strip(), name[:m.start()].strip()
    return name, ticker


def search(q):
    """Companies on EDGAR whose name or ticker starts like q (SEC's own company finder)."""
    q = (q or "").strip()[:80]
    if len(q) < 2:
        return []
    if q.isdigit():
        cik, name = fetch.find_company(q)
        return [{"cik": cik, "name": name, "ticker": ""}]
    hits = json.loads(fetch.get("https://efts.sec.gov/LATEST/search-index?keysTyped=" + urllib.parse.quote(q)))["hits"]["hits"]
    out = []
    for h in hits[:10]:
        src = h.get("_source", {})
        name, ticker = _short(src.get("entity", ""))
        tk = src.get("tickers") or ticker
        out.append({"cik": int(h["_id"]), "name": name, "ticker": tk.split(",")[0] if tk else "",
                    "blank_check": bool(SPAC.search(name))})
    return out


def recent(days=21):
    """Companies that filed an S-1 or F-1 in the last few weeks, newest first, one row each.
    Cached for an hour: the list changes a few times a day."""
    if time.time() - _recent_cache["at"] < 3600 and _recent_cache["rows"]:
        return _recent_cache["rows"]
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    seen, rows = set(), []
    for form in ("S-1", "F-1"):   # one form a query: a comma list returns far fewer hits
        url = (f"https://efts.sec.gov/LATEST/search-index?forms={form}&dateRange=custom"
               f"&startdt={start.isoformat()}&enddt={end.isoformat()}")
        for h in json.loads(fetch.get(url))["hits"]["hits"]:
            src = h.get("_source", {})
            ciks = src.get("ciks") or []
            names = src.get("display_names") or []
            if not ciks or not names:
                continue
            cik = int(ciks[0])
            if cik in seen:
                continue
            seen.add(cik)
            name, ticker = _short(names[0])
            rows.append({"cik": cik, "name": name, "ticker": ticker, "form": src.get("form") or form,
                         "date": src.get("file_date", ""), "blank_check": bool(SPAC.search(name))})
    rows.sort(key=lambda r: r["date"], reverse=True)
    _recent_cache.update(at=time.time(), rows=rows)
    return rows


class _Steps(io.TextIOBase):
    """Catches what the reader prints, so the page can show the step it is on."""
    def __init__(self, job, echo):
        self.job, self.echo = job, echo

    def write(self, s):
        if self.echo:
            self.echo.write(s)
        line = s.strip()
        if line:
            self.job["step"] = _plain(line)
        return len(s)


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _plain(line):
    """The reader's own progress lines, in words a reader follows (no file names or paths)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})\s+(\S+)\s+\d{10}-\d{2}-\d{6}$", line)
    if m:
        y, mo, d, form = m.groups()
        return f"downloading the {form} of {int(d)} {MONTHS[int(mo) - 1]} {y}"
    m = re.search(r"\):\s*(\d+) registration filings", line)
    if m:
        return f"found {m.group(1)} filings on SEC EDGAR"
    m = re.match(r"(\d+) pages,", line)
    if m:
        return f"split into {m.group(1)} printed pages"
    line = re.sub(r"\s*->\s*\S+$", "", line)
    line = re.sub(r"/\S+", "", line)
    return line.rstrip(".").strip()[:140]


def _run(job):
    from .__main__ import build
    from .dashboard import OUT
    job.update(state="reading", started=time.time(), step="finding its filings on SEC EDGAR")
    try:
        with contextlib.redirect_stdout(_Steps(job, sys.__stdout__)):
            out = build(str(job["cik"]), open_browser=False)
        job.update(state="done", file=out.relative_to(OUT).as_posix(), step="ready")
    except SystemExit as e:          # fetch says so when a company has no S-1 or F-1
        job.update(state="failed", error=str(e) or "no S-1 or F-1 on EDGAR")
    except Exception as e:
        job.update(state="failed", error=f"{type(e).__name__}: {e}"[:300])
    job["ended"] = time.time()


def _work():
    global _worker
    while True:
        with _lock:
            if not _queue:
                _worker = None
                return
            job = _queue.pop(0)
        _run(job)


def add(cik, name=""):
    """Queue a company to be read. Re-adding one already waiting or reading does nothing."""
    global _worker
    cik = int(cik)
    with _lock:
        cur = _jobs.get(cik)
        if cur and cur["state"] in ("waiting", "reading"):
            return cur
        job = {"cik": cik, "name": str(name)[:120] or f"CIK {cik}", "state": "waiting", "step": "waiting its turn",
               "file": "", "error": "", "added": time.time()}
        _jobs[cik] = job
        _queue.append(job)
        if _worker is None:
            _worker = threading.Thread(target=_work, daemon=True)
            _worker.start()
    return job


def jobs():
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["added"], reverse=True)
