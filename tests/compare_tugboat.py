#!/usr/bin/env python3
"""
Compare cgi-bin/classic_search.py with tugboat itself on the abs_connect /
basic_connect requests in an access log.

tugboat is not a dependency of this repo; to run the comparison, check it
out and install the few packages its translation needs, in a virtual
environment with Python 3.11 (tugboat's Flask/werkzeug versions predate 3.12):

    git clone https://github.com/adsabs/tugboat /tmp/tugboat
    python3.11 -m venv /tmp/tbenv && . /tmp/tbenv/bin/activate
    pip install flask==2.0.3 werkzeug==2.0.3 jinja2==3.0.3 itsdangerous==2.0.1 \\
        markupsafe==2.0.1 webargs==5.5.3 'marshmallow<3.10' future==0.18.3 \\
        python-dateutil requests flask-restful
    python tests/compare_tugboat.py --tugboat /tmp/tugboat [--log logs/access_log]

adsparser is replaced by a stub that raises, which is what tugboat
effectively did under Python 3 (see classic_search.translate_title_for_myads).
Both sides are compared as decoded (name, value) pairs -- what SciX sees --
leaving out tugboat's error/warning/unprocessed notes, which classic_search
logs instead.
"""
import argparse
import collections
import re
import sys
import tempfile
import types
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "cgi-bin"))
import classic_search as cs  # noqa: E402

NOTES = {"error_message", "warning_message", "unprocessed_parameter"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tugboat", required=True, help="path to a tugboat checkout")
    full = ROOT / "logs" / "access_log"
    ap.add_argument("--log", default=str(full if full.exists() else ROOT / "logs" / "access_log.sample"))
    ap.add_argument("--show", type=int, default=10, help="differences to print")
    args = ap.parse_args()

    stub = types.ModuleType("adsparser")
    def parse_classic_keywords(q):
        raise RuntimeError("adsparser stub")
    stub.parse_classic_keywords = parse_classic_keywords
    sys.modules["adsparser"] = stub
    sys.path.insert(0, args.tugboat)
    from flask import Flask, request
    from tugboat.views import ClassicSearchRedirectView
    app = Flask("compare")

    uris = set()
    with open(args.log, encoding="latin-1") as f:
        for line in f:
            m = re.search(r'"GET (/+cgi-bin/(?:nph-)?(?:abs|basic)_connect\?\S+) HTTP', line)
            if m:
                uris.add(m.group(1))

    results = collections.Counter()
    diffs = []
    for u in sorted(uris):
        qs = u.partition("?")[2]
        with app.test_request_context("/tugboat/classicSearchRedirect", query_string=qs):
            try:
                ref = ClassicSearchRedirectView().translate(request)
            except Exception:
                results["tugboat error"] += 1
                continue
        ref = [p for p in cs.query_pairs(ref[:-1] if ref.endswith("/") else ref) if p[0] not in NOTES]
        multi = collections.defaultdict(list)
        for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True, errors="replace"):
            multi[k].append(v)
        mine = cs.query_pairs(cs.translate(multi).query)
        if mine == ref:
            results["same"] += 1
        else:
            results["different"] += 1
            diffs.append((u, ref, mine))

    print(f"{len(uris)} unique search URLs: " + ", ".join(f"{v} {k}" for k, v in results.items()))
    for u, ref, mine in diffs[:args.show]:
        print(f"\n{u}\n  tugboat: {ref}\n  ours:    {mine}")


if __name__ == "__main__":
    main()
