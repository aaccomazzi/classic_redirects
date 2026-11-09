#!/usr/bin/env python3
"""
Differential replay: run request URIs from an access log through both the
original Perl handler (legacy/legacy_handler.pl, in a simulated Apache
environment) and the new Python handler, and report where they disagree.

    python3 tests/replay.py [--log logs/access_log.sample] [--per-endpoint 1500] [--out report.txt]

The Perl redirects point at ui.adsabs.harvard.edu; they are rewritten to the
SciX base before comparing. Query parameters are compared order-insensitively
(Perl hash order is random).
"""
import argparse
import collections
import importlib.machinery
import importlib.util
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qsl

ROOT = Path(__file__).resolve().parent.parent
PERL = ROOT / "legacy" / "legacy_handler.pl"
OLD_BASE = "https://ui.adsabs.harvard.edu"
NEW_BASE = "https://scixplorer.org"


sys.dont_write_bytecode = True  # keep cgi-bin/ free of __pycache__


def load_handler():
    path = str(ROOT / "cgi-bin" / "legacy_handler")
    loader = importlib.machinery.SourceFileLoader("legacy_handler", path)
    spec = importlib.util.spec_from_loader("legacy_handler", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


LH = load_handler()

# files that exist (and are executable) on the old server, per the error_log
EXEC_HTDOCS = {"journals_service.html", "bulletins_service.html",
               "proceedings_service.html", "ast_toc_ascii.html"}
STUB = "#!/bin/sh\nprintf 'Status: 299 Executed\\r\\n\\r\\n'\n"
LOGIN_STUB = "#!/bin/sh\nprintf 'Status: 298 insert_login\\r\\n\\r\\n'\n"


def make_tree(tmp, cgi_scripts):
    cgi = Path(tmp, "cgi", "bin"); cgi.mkdir(parents=True)
    docs = Path(tmp, "htdocs"); docs.mkdir()
    names = set(cgi_scripts) | {"nph-" + n for n in cgi_scripts} | {n[4:] for n in cgi_scripts if n.startswith("nph-")}
    for s in names:
        if "/" in s or not s.strip() or s in ("nph-",):
            continue
        p = cgi / s
        p.write_text(STUB); p.chmod(0o755)
    rmap = LH.build_redirect_map(NEW_BASE)
    for k in list(rmap) + list(EXEC_HTDOCS):
        if k and k not in ("local", "mirror", "z3950", "www", "books", "BOBeo", "pubs", "cfa"):
            (docs / k).write_text("x")
            if k in EXEC_HTDOCS:
                (docs / k).write_text(STUB); (docs / k).chmod(0o755)
    (docs / "insert_login").write_text(LOGIN_STUB); (docs / "insert_login").chmod(0o755)
    return cgi, docs


def run_perl(uri, cgi, docs):
    path, _, qs = uri.partition("?")
    dpath = re.sub(r"^/{2,}", "/", unquote(path))
    if dpath.startswith("/cgi-bin/"):
        translated = str(cgi) + dpath[len("/cgi-bin"):]
    else:
        translated = str(docs) + dpath
    env = {"REQUEST_METHOD": "GET", "QUERY_STRING": qs, "PATH_INFO": dpath,
           "PATH_TRANSLATED": translated, "REQUEST_URI": uri, "SCRIPT_NAME": "/cgi-bin/legacy_handler",
           "DOCUMENT_ROOT": str(docs), "PATH": "/usr/bin:/bin", "PERL_HASH_SEED": "0"}
    out = subprocess.run(["perl", str(PERL)], env=env, capture_output=True, timeout=10).stdout
    head = out.split(b"\r\n\r\n", 1)[0].decode("latin-1")
    status = re.search(r"Status: (\d+)", head)
    loc = re.search(r"Location: (.*)", head)
    return (int(status.group(1)) if status else None), (loc.group(1).strip() if loc else None)


def run_python(uri):
    path, _, qs = uri.partition("?")
    env = {"REQUEST_METHOD": "GET", "REQUEST_URI": uri, "QUERY_STRING": qs}
    req = LH.request_from_env(env)
    return LH.handle(req, NEW_BASE), req


def norm(url):
    if not url:
        return url
    url = url.replace(OLD_BASE, NEW_BASE)
    s = urlsplit(url)
    return (s.scheme, s.netloc, unquote(s.path), tuple(sorted(parse_qsl(s.query, keep_blank_values=True))))


def main():
    ap = argparse.ArgumentParser()
    full = ROOT / "logs" / "access_log"
    ap.add_argument("--log", default=str(full if full.exists() else ROOT / "logs" / "access_log.sample"),
                    help="default: logs/access_log if present, else logs/access_log.sample")
    ap.add_argument("--per-endpoint", type=int, default=1500)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    uris = collections.Counter()
    with open(args.log, encoding="latin-1") as f:
        for line in f:
            m = re.search(r'"(?:GET|HEAD) (\S+) HTTP', line)
            if m:
                uris[m.group(1)] += 1

    by_ep = collections.defaultdict(list)
    for u in uris:
        (_, _), req = run_python(u)
        by_ep[(req.is_cgi, req.endpoint)].append(u)

    random.seed(args.seed)
    cgi_scripts = {u.partition("?")[0][len("/cgi-bin/"):].split("/")[0]
                   for u in uris if u.startswith("/cgi-bin/")}
    rmap = LH.build_redirect_map(NEW_BASE)

    results = collections.Counter()
    diffs = []
    with tempfile.TemporaryDirectory() as tmp:
        cgi, docs = make_tree(tmp, {unquote(s) for s in cgi_scripts})
        for (is_cgi, ep), group in sorted(by_ep.items()):
            hits = sum(uris[u] for u in group)
            if not is_cgi and ep not in rmap:
                (status, _), _ = run_python(group[0])
                results[f"htdocs unmapped -> {status}"] += hits
                continue
            sample = group if len(group) <= args.per_endpoint else random.sample(group, args.per_endpoint)
            for u in sample:
                (pstatus, purl), _ = run_python(u)
                ostatus, ourl = run_perl(u, cgi, docs)
                key = f"{'/cgi-bin/' if is_cgi else '/'}{ep}"
                if ostatus == 301 and pstatus == 301:
                    same = norm(ourl) == norm(purl)
                    results[f"{key}: 301 {'same' if same else 'DIFFERENT'}"] += 1
                    if not same:
                        diffs.append((key, u, ourl, purl))
                else:
                    results[f"{key}: perl {ostatus} -> python {pstatus}"] += 1
                    if pstatus == 301:
                        diffs.append((key, u, f"[{ostatus}] {ourl}", purl))

    out = open(args.out, "w") if args.out else sys.stdout
    print("== outcome counts (sampled unique URIs; htdocs-unmapped rows are request hits) ==", file=out)
    for k, v in sorted(results.items()):
        print(f"{v:8d}  {k}", file=out)
    print(f"\n== differences ({len(diffs)}) ==", file=out)
    for key, u, o, p in diffs:
        print(f"{key}\n  uri:    {u}\n  perl:   {o}\n  python: {p}", file=out)


if __name__ == "__main__":
    main()
