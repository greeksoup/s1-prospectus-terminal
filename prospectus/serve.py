"""A small local server: shows the dashboards and lets the question box reach your AI app.
It listens on this computer only (127.0.0.1); nothing is reachable from outside."""
import json
import re
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import ai
from .ask import apps, ask, open_window
from .dashboard import OUT, ROOT, write_index

NOTES = ROOT / "notes"  # your own notes, one file per company; never part of the shared library

_apps_cache = {}


class Handler(SimpleHTTPRequestHandler):
    def _json(self, result):
        data = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/refresh":
            from urllib.parse import parse_qs, urlparse
            from .refresh import check
            cik = (parse_qs(urlparse(self.path).query).get("cik") or [""])[0]
            try:
                return self._json(check(int(cik)))
            except Exception as e:
                return self._json({"error": f"could not reach SEC EDGAR ({type(e).__name__})"})
        if self.path.split("?")[0] == "/notes":
            from urllib.parse import parse_qs, urlparse
            slug_ = re.sub(r"[^a-z0-9-]", "", (parse_qs(urlparse(self.path).query).get("company") or [""])[0])[:60]
            f = NOTES / f"{slug_}.json"
            return self._json(json.loads(f.read_text()) if slug_ and f.exists() else {})
        if self.path.split("?")[0].startswith("/companies/"):
            from urllib.parse import parse_qs, urlparse
            from . import addco
            u = urlparse(self.path)
            try:
                if u.path == "/companies/search":
                    return self._json({"rows": addco.search((parse_qs(u.query).get("q") or [""])[0])})
                if u.path == "/companies/recent":
                    return self._json({"rows": addco.recent()})
                if u.path == "/companies/jobs":
                    return self._json({"jobs": addco.jobs()})
                if u.path == "/companies/list":
                    from .dashboard import index_rows
                    return self._json({"rows": index_rows()})
            except SystemExit as e:
                return self._json({"rows": [], "error": str(e)})
            except Exception as e:
                return self._json({"rows": [], "error": f"could not reach SEC EDGAR ({type(e).__name__})"})
        if self.path.split("?")[0] == "/ai":
            return self._json(ai.public())
        if self.path.split("?")[0] == "/ai/models":
            from urllib.parse import parse_qs, urlparse
            return self._json(ai.local_models((parse_qs(urlparse(self.path).query).get("provider") or [""])[0]))
        if self.path.split("?")[0] == "/apps":
            if "fresh" in self.path or "rows" not in _apps_cache:
                _apps_cache["rows"] = apps()
            return self._json({"apps": _apps_cache["rows"]})
        return super().do_GET()

    def _same_site(self):
        """Only this program's own page may post here: a web page elsewhere in the browser
        cannot save a key, open a terminal or spend your AI plan."""
        origin = self.headers.get("Origin") or ""
        return not origin or re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origin) is not None

    def do_POST(self):
        if not self._same_site():
            self.send_error(403)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/ai/save":
            try:
                return self._json(dict(ai.save(body), ok=True))
            except ValueError as e:
                return self._json({"error": str(e)})
        if self.path == "/ai/check":
            return self._json(ai.ping())
        if self.path == "/apps/open":
            r = open_window(str(body.get("app") or ""), str(body.get("what") or ""))
            _apps_cache.pop("rows", None)
            return self._json(r)
        if self.path == "/notes":
            slug_ = re.sub(r"[^a-z0-9-]", "", str(body.get("company", "")))[:60]
            if not slug_:
                return self._json({"error": "no company"})
            NOTES.mkdir(exist_ok=True)
            notes = {k: str(v)[:20000] for k, v in (body.get("notes") or {}).items() if k in ("zero", "after", "free")}
            (NOTES / f"{slug_}.json").write_text(json.dumps(notes))
            md = [f"# {body.get('name', slug_)}: my notes", ""]
            for k, t in (("zero", "Five lines, before any number"), ("after", "What changed after the filing"), ("free", "Anything else")):
                if notes.get(k):
                    md += [f"## {t}", "", notes[k], ""]
            (NOTES / f"{slug_}.md").write_text("\n".join(md))
            return self._json({"ok": True, "file": str((NOTES / f"{slug_}.md").resolve())})
        if self.path == "/companies/add":
            from . import addco
            try:
                return self._json({"job": addco.add(int(body["cik"]), str(body.get("name") or ""))})
            except (KeyError, ValueError):
                return self._json({"error": "no company picked"})
        if self.path == "/rebuild":
            from .__main__ import build
            try:
                build(str(int(body["cik"])), open_browser=False)
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"error": f"could not rebuild ({e})"})
        if self.path != "/ask":
            self.send_error(404)
            return
        try:
            result = ask(body["cik"], str(body["question"])[:500], app=str(body.get("app") or ""), model=str(body.get("model") or ""),
                         history=body.get("history") or [], fresh=bool(body.get("fresh")))
        except Exception as e:
            result = {"error": f"Could not answer: {e}"}
        self._json(result)

    def log_message(self, *args):
        pass


def serve(port=8861, open_browser=True):
    OUT.mkdir(exist_ok=True)
    write_index()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(OUT)))
    except OSError:
        # most often the program is already open from an earlier double-click: show that one
        print(f"S-1 Prospectus Terminal is already running at http://127.0.0.1:{port}/ (opening it). "
              f"If that is some other program, start this one on another port: python3 -m prospectus serve {port + 1}")
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return
    url = f"http://127.0.0.1:{port}/"
    print(f"S-1 Prospectus Terminal at {url}  (keep this window open; Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
