"""One command for everything.

  python3 -m prospectus "Anthropic"            read the newest prospectus and build its dashboard
  python3 -m prospectus serve [port]           open the dashboards with the question box working
  python3 -m prospectus ask 2130357 "question" ask your own AI app about the filing, from the terminal
                                        (add --app grok, codex, claude... or --app key for your own key/local model, and --model NAME)
  python3 -m prospectus apps                   list every AI app, whether it is installed and signed in, and how to install it
  python3 -m prospectus update                check GitHub for a newer version and offer it (the starters do this each time)
  python3 -m prospectus redraw                 redraw every dashboard with the current design (no downloads)
  python3 -m prospectus reread                 re-read every company from the filings on disk with the current code (no SEC calls)
  python3 -m prospectus refresh                check EDGAR for newer filings of every company and rebuild those
  python3 -m prospectus library FILE           build every company named in FILE (one name or ticker a line)
"""
import json
import sys
import time
import webbrowser
from pathlib import Path


def build(query, open_browser=True, others=True):
    from . import dashboard, fetch, flags, pages, questions, versions
    from . import others as others_mod
    t0 = time.time()
    index_path = fetch.main(query)
    index = json.loads(Path(index_path).read_text())
    latest = fetch.filing_path(index["filings"][-1]["path"])
    t1 = time.time()
    pages.main(latest)
    q = questions.answer(latest)
    fl = flags.run(latest)
    read_seconds = round(time.time() - t1, 1)
    print("comparing versions...")
    vs = versions.run(index_path)
    Path(index_path).with_name("versions.json").write_text(json.dumps(vs))
    ot = {}
    if others:
        print("searching other filings that name it...")
        try:
            ot = others_mod.run(index_path)
        except Exception as e:  # the dashboard still builds if SEC search is down
            ot = {"error": str(e)}
    n_pages = len(json.loads(Path(latest).with_suffix(".pages.json").read_text()))
    stats = {"pages": n_pages, "seconds": read_seconds, "total_seconds": round(time.time() - t0, 1), "ai_tokens": 0}
    st, ql = {}, {}
    try:
        from . import statements
        st = statements.run(latest)
    except Exception as e:  # the dashboard still builds without the full statements
        print(f"full statements not read: {e}")
    try:
        from . import qual
        ql = qual.run(latest)
    except Exception as e:
        print(f"offer, owners and people not read: {e}")
    sh, mt = {}, {}
    try:
        from . import shares
        sh = shares.run(latest)
    except Exception as e:
        print(f"share counts not read: {e}")
    try:
        from . import metrics
        mt = metrics.run(latest)
    except Exception as e:
        print(f"quarterly results and commitments not read: {e}")
    data = dashboard.bundle(index_path, latest, q, fl, vs, ot, stats, st, ql, sh, mt)
    out = dashboard.write(data)
    print(f"\n{index['name']}: {n_pages} pages read in {read_seconds}s, {len(fl['flags'])} flags, 0 AI tokens")
    print(f"dashboard: {out}")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out


def reread():
    """Re-read every company in library/ from the filing already on disk, with the current code.
    Keeps the version comparison and the other-filings search from the last full build (no SEC calls)."""
    from . import dashboard, flags, pages, questions
    out = []
    for p in sorted(dashboard.LIB.glob("*.json")):
        old = json.loads(p.read_text())
        cik = old["meta"]["cik"]
        index_path = dashboard.ROOT / "data" / str(cik) / "filings.json"
        if not index_path.exists():
            out.append(f"{old['meta']['name']}: filing not on disk, run python3 -m prospectus {cik}")
            continue
        latest = __import__("prospectus.fetch", fromlist=["x"]).filing_path(json.loads(index_path.read_text())["filings"][-1]["path"])
        t1 = time.time()
        pages.main(latest)
        q, fl = questions.answer(latest), flags.run(latest)
        parts = {}
        for mod in ("statements", "qual", "shares", "metrics"):
            try:
                parts[mod] = __import__(f"prospectus.{mod}", fromlist=["run"]).run(latest)
            except Exception as e:
                parts[mod] = {}
                print(f"{old['meta']['name']}: {mod} not read ({e})")
        stats = dict(old["meta"].get("stats", {}), pages=len(json.loads(Path(latest).with_suffix(".pages.json").read_text())),
                     seconds=round(time.time() - t1, 1))
        data = dashboard.bundle(index_path, latest, q, fl, old.get("versions", []), old.get("others", {}), stats,
                                parts["statements"], parts["qual"], parts["shares"], parts["metrics"])
        dashboard.write(data)
        out.append(f"{data['meta']['name']}: {stats['pages']} pages in {stats['seconds']}s")
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return
    if argv[0] == "setup":
        from .setup import main as setup
        sys.exit(setup(argv[1:]))
    elif argv[0] == "update":
        from .update import main as update
        sys.exit(update(argv[1:]))
    elif argv[0] == "version":
        from . import __version__
        print(__version__)
    elif argv[0] == "redraw":
        from .dashboard import redraw
        print(f"redrew {redraw()} dashboards")
    elif argv[0] == "serve":
        from .serve import serve
        rest = [a for a in argv[1:] if not a.startswith("--")]
        serve(int(rest[0]) if rest else 8861, open_browser="--no-open" not in argv)
    elif argv[0] == "reread":
        for line in reread():
            print(line)
    elif argv[0] == "refresh":
        from .refresh import run
        for name, what in run():
            print(f"{name}: {what}")
    elif argv[0] == "library":
        for line in Path(argv[1]).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                build(line.strip(), open_browser=False)
    elif argv[0] == "apps":
        from .ask import apps
        for a in apps():
            print(f"{a['label']:<12} {'found' if a['found'] else 'not installed':<14} {a['state']:<8} {a['note']}")
            if not a["found"]:
                print(f"{'':<12} install: {a['install']}")
        from .ai import public
        k = public()
        print(f"\nYour key / local model: {k['label'] + ' · ' + k['model'] if k['provider'] else 'none saved'}"
              f"{' (ready)' if k['ready'] else (' (' + k['why'] + ')' if k['provider'] else '')}")
    elif argv[0] == "ask":
        from .ask import ask
        opt = {argv[i][2:]: argv[i + 1] for i in range(len(argv) - 1) if argv[i] in ("--app", "--model")}
        words = [a for i, a in enumerate(argv[2:], 2) if not a.startswith("--") and argv[i - 1] not in ("--app", "--model")]
        r = ask(argv[1], " ".join(words), app=opt.get("app", ""), model=opt.get("model", ""))
        print(r.get("answer") or r.get("error"))
        print("\npages used:", ", ".join(r.get("pages", [])), "| app:", r.get("app"))
    else:
        flags = {a for a in argv if a.startswith("--")}
        build(" ".join(a for a in argv if not a.startswith("--")), open_browser="--no-open" not in flags,
              others="--no-others" not in flags)


if __name__ == "__main__":
    main([a for a in sys.argv[1:]])
