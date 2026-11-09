"""Adding a company from the browser (prospectus/addco.py and its routes in serve.py): names and
tickers read from SEC's search rows, progress lines in plain words, a company picked twice is read
once, a failed read says why, and only this program's own page may start a read. No internet:
SEC and the reader are stood in for. Run: python3 -m tests.test_addco
"""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from prospectus import addco, fetch, serve
import prospectus.__main__ as main_mod

CHECKS = []

CHECKS += [
    ("name and ticker from a filing row", addco._short("Rezera Inc.  (RZRA)  (CIK 0002141583)"), ("Rezera Inc.", "RZRA")),
    ("a row with no ticker", addco._short("Alopexx, Inc.  (CIK 0001880995)"), ("Alopexx, Inc.", "")),
    ("two tickers keep the first", addco._short("Foo Corp  (FOO, FOOW)  (CIK 0000000001)"), ("Foo Corp", "FOO")),
    ("a blank-check company is marked", bool(addco.SPAC.search("ZA Acquisition Corp. I")), True),
    ("an operating company is not", bool(addco.SPAC.search("Exozymes Inc.")), False),
    ("download line in words", addco._plain("2026-11-06  S-1    0001493152-26-050521"), "downloading the S-1 of 6 Nov 2026"),
    ("filing count in words", addco._plain("EXOZYMES INC. (CIK 2010788): 12 registration filings"), "found 12 filings on SEC EDGAR"),
    ("page count in words, no file name",
     addco._plain("212 pages, 3 without a readable number -> /x/data/1/filings/a.pages.json"), "split into 212 printed pages"),
    ("other lines lose paths", addco._plain("dashboard: /Users/me/prospectus/dashboards/x.html"), "dashboard:"),
    ("one letter does not search", addco.search("a"), []),
]

# SEC search stood in for
fetch.get = lambda url: json.dumps({"hits": {"hits": [
    {"_id": "2010788", "_source": {"entity": "EXOZYMES INC.  (EXOZ)  (CIK 0002010788)", "tickers": "EXOZ"}},
    {"_id": "2127714", "_source": {"entity": "ZA Acquisition Corp. I  (CIK 0002127714)"}}]}}).encode()
rows = addco.search("exo")
CHECKS += [("search rows carry cik, name, ticker", [(r["cik"], r["name"], r["ticker"], r["blank_check"]) for r in rows],
            [(2010788, "EXOZYMES INC.", "EXOZ", False), (2127714, "ZA Acquisition Corp. I", "", True)])]

# the reader stood in for: one slow success, one company with no S-1
calls = []


class FakeOut:
    def relative_to(self, _):
        return self

    def as_posix(self):
        return "exozymes-inc.html"


def fake_build(q, open_browser=True, others=True):
    calls.append(q)
    print("2026-11-06  S-1    0001493152-26-050521")
    time.sleep(0.3)
    if q == "1":
        raise SystemExit("Nobody Inc has no public S-1 or F-1 on EDGAR yet.")
    return FakeOut()


main_mod.build = fake_build
addco.add(2010788, "Exozymes Inc.")
addco.add(2010788, "Exozymes Inc.")      # picked twice while the first read runs
addco.add(1, "Nobody Inc")
for _ in range(50):
    if all(j["state"] in ("done", "failed") for j in addco.jobs()):
        break
    time.sleep(0.1)
by = {j["cik"]: j for j in addco.jobs()}
CHECKS += [
    ("a company picked twice is read once", calls.count("2010788"), 1),
    ("a read that finishes points at its dashboard", (by[2010788]["state"], by[2010788]["file"]), ("done", "exozymes-inc.html")),
    ("a company with no S-1 says why", (by[1]["state"], "no public S-1" in by[1]["error"]), ("failed", True)),
]

# the routes: only this program's own page may start a read
srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"


def post(path, body, origin=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code


jobs = json.loads(urllib.request.urlopen(base + "/companies/jobs", timeout=5).read())["jobs"]
CHECKS += [
    ("the page sees the reads", sorted(j["cik"] for j in jobs), [1, 2010788]),
    ("another website cannot start a read", post("/companies/add", {"cik": 5}, "https://evil.example"), 403),
    ("this page can start a read", "job" in post("/companies/add", {"cik": 2010788, "name": "Exozymes Inc."}, base), True),
    ("a read with no company is refused", post("/companies/add", {}, base), {"error": "no company picked"}),
]
srv.shutdown()

misses = 0
for name, got, want in CHECKS:
    ok = got == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
