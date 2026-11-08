"""Your AI: every app listed whether installed or not, and the key path (prospectus/ai.py) on both wire
shapes plus Ollama's own address, against a stand-in model server on this computer. No real key,
no internet. Run: python3 -m tests.test_ai
"""
import json
import os
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

from prospectus import ai, ask

SEEN = []


class Mock(BaseHTTPRequestHandler):
    def _j(self, code, d):
        b = json.dumps(d).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._j(200, {"data": [{"id": "small:1b"}, {"id": "big:8b"}]}) if self.path.endswith("/models") else self._j(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"path": self.path, "x-api-key": self.headers.get("x-api-key"), "authorization": self.headers.get("authorization"),
                     "num_ctx": (body.get("options") or {}).get("num_ctx"), "system": body.get("system")})
        if body.get("model") == "wrong":
            return self._j(404, {"error": {"message": "model 'wrong' not found"}})
        if self.path == "/api/chat":
            return self._j(200, {"message": {"content": "ollama ok"}})
        if self.path.endswith("/v1/messages"):
            return self._j(200, {"content": [{"type": "text", "text": "anthropic ok"}], "stop_reason": "end_turn"})
        self._j(200, {"choices": [{"message": {"content": "openai ok"}}]})

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"

tmp = Path(tempfile.mkdtemp())
ai.FILE = tmp / ".ai.json"  # never touch the real key file
KEY = "sk-test-0000000000000000wxyz"

CHECKS = []
rows = ask.apps()
CHECKS += [
    ("all seven apps listed, installed or not", [r["app"] for r in rows], list(ask.APPS)),
    ("every app carries an install line", all(r["install"] for r in rows), True),
    ("every app carries its maker's page", all(r["site"].startswith("https://") for r in rows), True),
    ("a missing app says missing, not hidden", all(r["state"] == "missing" for r in rows if not r["found"]), True),
    ("fourteen provider presets", len(ai.PROVIDERS), 14),
    ("Ollama and LM Studio need no key", (ai.PROVIDERS["ollama"]["needs_key"], ai.PROVIDERS["lmstudio"]["needs_key"]), (False, False)),
    ("nothing saved: not ready, says why", (ai.public()["ready"], ai.public()["why"]), (False, "Pick a provider first.")),
    ("open_window refuses an unknown app", ask.open_window("rm -rf", "install")["ok"], False),
    ("open_window refuses an unknown action", ask.open_window("claude", "run")["ok"], False),
]

# the common way, with a key
pub = ai.save({"provider": "custom", "base_url": BASE + "/v1", "model": "m1", "format": "openai", "key": KEY})
CHECKS += [
    ("the page never sees the key", KEY in json.dumps(pub), False),
    ("the page sees that a key is saved", pub["key"], "saved, ends wxyz"),
    ("key file readable by you only", oct(os.stat(ai.FILE).st_mode & 0o777), "0o600"),
    ("common way answers", ai.ping(), {"ok": True, "reply": "openai ok"}),
    ("common way sends the key as Bearer", SEEN[-1]["authorization"], "Bearer " + KEY),
    ("common way path", SEEN[-1]["path"], "/v1/chat/completions"),
]

# Anthropic's way
ai.save({"provider": "custom", "base_url": BASE, "model": "m2", "format": "anthropic"})
CHECKS += [
    ("same provider, no new key typed: key kept", ai.settings()["key"], KEY),
    ("Anthropic way answers", ai.answer("QUESTION: x")["answer"], "anthropic ok"),
    ("Anthropic way sends x-api-key", (SEEN[-1]["path"], SEEN[-1]["x-api-key"]), ("/v1/messages", KEY)),
]

# the endpoint's own words come back
ai.save({"provider": "custom", "base_url": BASE + "/v1", "model": "wrong", "format": "openai"})
r = ai.ping()
CHECKS += [("a refusal comes back in the endpoint's words", (r["ok"], "model 'wrong' not found" in r["error"]), (False, True))]

# switching provider drops the old key
pub = ai.save({"provider": "ollama", "base_url": BASE + "/v1", "model": "small:1b"})
CHECKS += [
    ("switching provider drops the old key", (ai.settings()["key"], pub["key"]), ("", "")),
    ("Ollama ready with no key", pub["ready"], True),
    ("Ollama answers on its own address", ai.ping()["reply"], "ollama ok"),
    ("Ollama gets the long window", (SEEN[-1]["path"], SEEN[-1]["num_ctx"]), ("/api/chat", ai.OLLAMA_WINDOW)),
    ("Ollama sends no key", (SEEN[-1]["authorization"], SEEN[-1]["x-api-key"]), (None, None)),
    ("models on this computer are listed", ai.local_models("ollama")["models"], ["big:8b", "small:1b"]),
]

# nothing answering
ai.save({"provider": "lmstudio", "base_url": "http://127.0.0.1:9/v1", "model": "x"})
r = ai.ping()
CHECKS += [("a local app that is not open says so", (r["ok"], "Is the app open" in r["error"]), (False, True))]

# the server: only this program's own page may post
from functools import partial  # noqa: E402

from prospectus import serve  # noqa: E402

web = ThreadingHTTPServer(("127.0.0.1", 0), partial(serve.Handler, directory=str(tmp)))
threading.Thread(target=web.serve_forever, daemon=True).start()


def post(path, origin):
    req = urllib.request.Request(f"http://127.0.0.1:{web.server_port}{path}", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
    try:
        return urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code


got = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{web.server_port}/ai", timeout=10).read())
CHECKS += [
    ("another website cannot post", post("/ai/check", "https://evil.example"), 403),
    ("this page can post", post("/ai/check", f"http://127.0.0.1:{web.server_port}"), 200),
    ("GET /ai holds no key", KEY in json.dumps(got), False),
]

misses = 0
for name, got_, want in CHECKS:
    ok = got_ == want
    misses += not ok
    print(("ok  " if ok else "MISS"), name, "" if ok else f"-> got {got_}, want {want}")
print(f"\n{len(CHECKS) - misses}/{len(CHECKS)} match")
raise SystemExit(misses)
