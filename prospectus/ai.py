"""The second way to ask: your own AI key, or a free model running on this computer.

The first way (ask.py, APPS) hands the question to an app you already pay for. This one sends it
straight to a provider you pick. Two request shapes exist and this file speaks both: the common
one (POST .../chat/completions: OpenAI, Google's compatible address, xAI, Mistral, OpenRouter,
Ollama, LM Studio and most others) and Anthropic's own (POST .../v1/messages, also offered by
DeepSeek, Kimi, MiniMax, Z.ai and Alibaba's Qwen). A preset fills the shape, the address and a
starting model; any of the three can be changed, and "any other endpoint" takes all three by hand.

The presets are the GreekSoup desk's (one-person-equity-research-desk, ai.py), copied as they are.

Where the key lives: one file on this computer, .ai.json in the program folder, readable by you
only, listed in .gitignore. It is never written into library/, never put in a page, never
printed or logged, and goes only to the address you chose.
"""
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / ".ai.json"

FORMATS = {
    "openai": "the common way (most labs, every local model)",
    "anthropic": "Anthropic's own way",
}

# id -> preset. base_url ends where the format's path is appended.
# model "" = the reader types the name from the provider's model page.
PROVIDERS = {
    "anthropic":  {"label": "Anthropic", "format": "anthropic", "base_url": "https://api.anthropic.com", "model": "claude-opus-5", "needs_key": True,
                   "keys": "https://console.anthropic.com/settings/keys"},
    "openai":     {"label": "OpenAI", "format": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-5", "needs_key": True,
                   "keys": "https://platform.openai.com/api-keys"},
    "google":     {"label": "Google (Gemini)", "format": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.8-flash", "needs_key": True,
                   "keys": "https://aistudio.google.com/apikey"},
    "deepseek":   {"label": "DeepSeek", "format": "openai", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "needs_key": True,
                   "alt": {"format": "anthropic", "base_url": "https://api.deepseek.com/anthropic"}, "keys": "https://platform.deepseek.com/api_keys"},
    "kimi":       {"label": "Kimi (Moonshot)", "format": "openai", "base_url": "https://api.moonshot.ai/v1", "model": "kimi-k3", "needs_key": True,
                   "alt": {"format": "anthropic", "base_url": "https://api.moonshot.ai/anthropic"}, "keys": "https://platform.moonshot.ai/console/api-keys"},
    "minimax":    {"label": "MiniMax", "format": "anthropic", "base_url": "https://api.minimax.io/anthropic", "model": "", "needs_key": True,
                   "alt": {"format": "openai", "base_url": "https://api.minimax.io/v1"}, "keys": "https://www.minimax.io/platform"},
    "zai":        {"label": "Z.ai (GLM)", "format": "anthropic", "base_url": "https://api.z.ai/api/anthropic", "model": "", "needs_key": True,
                   "keys": "https://z.ai/manage-apikey/apikey-list"},
    "qwen":       {"label": "Alibaba (Qwen)", "format": "anthropic", "base_url": "https://dashscope-intl.aliyuncs.com/apps/anthropic", "model": "", "needs_key": True,
                   "keys": "https://modelstudio.console.alibabacloud.com/"},
    "xai":        {"label": "xAI (Grok)", "format": "openai", "base_url": "https://api.x.ai/v1", "model": "", "needs_key": True,
                   "keys": "https://console.x.ai/"},
    "mistral":    {"label": "Mistral", "format": "openai", "base_url": "https://api.mistral.ai/v1", "model": "", "needs_key": True,
                   "keys": "https://console.mistral.ai/api-keys"},
    "openrouter": {"label": "OpenRouter (many models, one key)", "format": "openai", "base_url": "https://openrouter.ai/api/v1", "model": "", "needs_key": True,
                   "keys": "https://openrouter.ai/keys"},
    "ollama":     {"label": "Ollama on this computer (free)", "format": "openai", "base_url": "http://localhost:11434/v1", "model": "", "needs_key": False,
                   "local": True, "get": "https://ollama.com/download"},
    "lmstudio":   {"label": "LM Studio on this computer (free)", "format": "openai", "base_url": "http://localhost:1234/v1", "model": "", "needs_key": False,
                   "local": True, "get": "https://lmstudio.ai"},
    "custom":     {"label": "Any other endpoint", "format": "openai", "base_url": "", "model": "", "needs_key": False},
}

_PING = "Reply with the single word: ok"
STEP = " Check the provider, the key and the model under Your AI, then try again."


# ---------- the local file ----------

def _read():
    try:
        d = json.loads(FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d):
    FILE.write_text(json.dumps(d, indent=1))
    try:
        os.chmod(FILE, 0o600)  # readable by you only
    except OSError:
        pass


def settings():
    """What is saved, with the preset filling what was left empty. Holds the key: never send this to the page."""
    d = _read()
    p = str(d.get("provider") or "").strip().lower()
    preset = PROVIDERS.get(p, {})
    fmt = str(d.get("format") or "").strip().lower() or preset.get("format", "openai")
    if fmt not in FORMATS:
        fmt = "openai"
    return {
        "provider": p if p in PROVIDERS else "",
        "format": fmt,
        "key": str(d.get("key") or "").strip(),
        "model": str(d.get("model") or "").strip() or preset.get("model", ""),
        "base_url": str(d.get("base_url") or "").strip() or preset.get("base_url", ""),
        "needs_key": preset.get("needs_key", False),
    }


def masked(key):
    if not key:
        return ""
    return "saved, ends " + key[-4:] if len(key) > 12 else "saved"


def public():
    """What the page may see: everything but the key itself."""
    s = settings()
    return {"provider": s["provider"], "format": s["format"], "model": s["model"], "base_url": s["base_url"],
            "key": masked(s["key"]), "ready": not_ready(s) is None, "why": not_ready(s) or "",
            "label": PROVIDERS.get(s["provider"], {}).get("label", ""),
            "providers": {k: {x: v[x] for x in v} for k, v in PROVIDERS.items()}, "formats": FORMATS,
            "file": ".ai.json in the program folder"}


def save(body):
    """Save the provider, model, address and shape; the key only when a new one is typed.
    `clear_key` removes the key. Returns the public view."""
    d = _read()
    p = str(body.get("provider") or "").strip().lower()
    if p and p not in PROVIDERS:
        raise ValueError("no such provider")
    if p != d.get("provider"):
        # a key belongs to one provider: switching provider drops the old one
        d.pop("key", None)
    d["provider"] = p
    for k in ("model", "base_url"):
        d[k] = str(body.get(k) or "").strip()[:300]
    fmt = str(body.get("format") or "").strip().lower()
    d["format"] = fmt if fmt in FORMATS else ""
    key = str(body.get("key") or "").strip()
    if key:
        d["key"] = key[:400]
    if body.get("clear_key"):
        d.pop("key", None)
    if not p:
        d = {}
    _write(d)
    return public()


# ---------- the request ----------

def not_ready(s):
    """Why a request cannot be made yet, in the reader's words, or None."""
    if not s["provider"]:
        return "Pick a provider first."
    if s["needs_key"] and not s["key"]:
        return "No key saved yet for " + PROVIDERS[s["provider"]]["label"] + "."
    if not s["model"]:
        return "Type the model's name; " + ("pick one from the models on this computer." if PROVIDERS[s["provider"]].get("local") else "this provider's page lists them.")
    if not s["base_url"]:
        return "Type the endpoint's address."
    return None


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


class _Resp:
    def __init__(self, status, text):
        self.status, self.text = status, text

    def json(self):
        return json.loads(self.text or "{}")


def _post(url, headers, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx() if url.startswith("https") else None) as r:
            return _Resp(r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return _Resp(e.code, e.read().decode("utf-8", "replace"))


def _get(url, headers, timeout=6):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx() if url.startswith("https") else None) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def _err(r):
    """The endpoint's own words, short, for the page."""
    try:
        j = r.json()
        e = j.get("error")
        msg = e.get("message") if isinstance(e, dict) else (e or j.get("message"))
        if msg:
            return f"{msg}"[:240] + STEP
    except Exception:  # noqa: BLE001
        pass
    return ((r.text or "").strip()[:240] or f"answered {r.status}") + STEP


def _anthropic(s, messages, system, max_tokens, bearer, timeout):
    headers = {"anthropic-version": "2023-06-01", "content-type": "application/json"}
    if s["key"]:
        headers["authorization" if bearer else "x-api-key"] = ("Bearer " + s["key"]) if bearer else s["key"]
    body = {"model": s["model"], "max_tokens": max_tokens, "messages": messages}
    if system:
        body["system"] = system
    return _post(s["base_url"].rstrip("/") + "/v1/messages", headers, body, timeout)


def _openai(s, messages, system, max_tokens, timeout):
    headers = {"content-type": "application/json"}
    if s["key"]:
        headers["authorization"] = "Bearer " + s["key"]
    body = {"model": s["model"], "messages": ([{"role": "system", "content": system}] if system else []) + messages}
    if max_tokens:
        body["max_tokens"] = max_tokens
    return _post(s["base_url"].rstrip("/") + "/chat/completions", headers, body, timeout)


# The brief (rules, the dashboard's record, the matching pages) runs to about 17,000 tokens.
# Ollama's common-way address keeps its own short default memory and silently cuts a longer
# text, so a question to Ollama goes to its own chat address, which takes a longer window.
OLLAMA_WINDOW = 32768


def _ollama(s, messages, system, timeout):
    base = s["base_url"].rstrip("/")
    base = base[:-3] if base.endswith("/v1") else base
    body = {"model": s["model"], "stream": False, "options": {"num_ctx": OLLAMA_WINDOW},
            "messages": ([{"role": "system", "content": system}] if system else []) + messages}
    return _post(base + "/api/chat", {"content-type": "application/json"}, body, timeout)


def complete(messages, system=None, max_tokens=16, timeout=60, s=None):
    """One request in whichever shape the endpoint speaks.
    {'ok': True, 'text': ...} or {'ok': False, 'error': words}."""
    s = s or settings()
    why = not_ready(s)
    if why:
        return {"ok": False, "error": why}
    try:
        if s["provider"] == "ollama" and s["format"] == "openai":
            r = _ollama(s, messages, system, timeout)
            if r.status != 200:
                return {"ok": False, "error": _err(r)}
            return {"ok": True, "text": str((r.json().get("message") or {}).get("content") or "").strip()}
        if s["format"] == "anthropic":
            r = _anthropic(s, messages, system, max_tokens, False, timeout)
            if r.status == 401 and s["key"]:
                r = _anthropic(s, messages, system, max_tokens, True, timeout)  # a few compatible endpoints want Bearer
            if r.status != 200:
                return {"ok": False, "error": _err(r)}
            j = r.json()
            if j.get("stop_reason") == "refusal":
                return {"ok": True, "text": "", "refused": True}
            return {"ok": True, "text": " ".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text").strip()}
        r = _openai(s, messages, system, max_tokens if max_tokens > 16 else None, timeout)
        if r.status != 200:
            return {"ok": False, "error": _err(r)}
        j = r.json()
        return {"ok": True, "text": str(((j.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()}
    except urllib.error.URLError as e:
        if "timed out" in str(e.reason).lower():
            return {"ok": False, "error": "The model did not answer in time. Try once more, or a smaller model."}
        local = PROVIDERS.get(s["provider"], {}).get("local")
        return {"ok": False, "error": "Nothing answered at " + s["base_url"] + "." + (
            " Is the app open, with a model downloaded?" if local else " Is the address right?")}
    except TimeoutError:
        return {"ok": False, "error": "The model did not answer in time. Try once more, or a smaller model."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:240]}


def ping(s=None):
    """The Check button: one tiny request. {'ok': True, 'reply': text} or {'ok': False, 'error': words}."""
    out = complete([{"role": "user", "content": _PING}], max_tokens=16, timeout=60, s=s)
    if not out["ok"]:
        return out
    if out.get("refused"):
        return {"ok": True, "reply": "(the model declined the test line; the key itself works)"}
    return {"ok": True, "reply": (out["text"] or "(empty reply)")[:200]}


def local_models(provider):
    """The models already downloaded into Ollama or LM Studio on this computer (no key, no internet)."""
    p = PROVIDERS.get(provider) or {}
    if not p.get("local"):
        return {"ok": False, "models": []}
    s = settings()
    base = s["base_url"] if s["provider"] == provider and s["base_url"] else p["base_url"]
    try:
        j = _get(base.rstrip("/") + "/models", {})
        return {"ok": True, "models": sorted(m.get("id", "") for m in j.get("data", []) if m.get("id"))}
    except Exception:  # noqa: BLE001
        return {"ok": False, "models": [], "error": p["label"].replace(" (free)", "") + " is not answering at " + base + ": is it installed and open?"}


def answer(text, timeout=240):
    """Ask the saved provider. `text` is the whole brief (rules, record, pages, question)."""
    s = settings()
    label = PROVIDERS.get(s["provider"], {}).get("label", "your key").replace(" (free)", "")
    out = complete([{"role": "user", "content": text}], max_tokens=1600, timeout=timeout, s=s)
    if not out["ok"]:
        return {"ok": False, "error": f"{label}: {out['error']}"}
    if out.get("refused") or not out["text"]:
        return {"ok": False, "error": f"{label} sent an empty answer."}
    return {"ok": True, "answer": out["text"], "via": f"{label} · {s['model']}"}
