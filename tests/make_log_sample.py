#!/usr/bin/env python3
"""
Make a small, anonymized sample of the server logs for the repository.

    python3 tests/make_log_sample.py [--per-endpoint 40] [--error-lines 1000]

Reads logs/access_log and logs/error_log (not in git) and writes
logs/access_log.sample and logs/error_log.sample:

* access_log.sample: up to --per-endpoint random requests for every endpoint
  (cgi-bin script or first path segment), so rare endpoints are all kept.
* error_log.sample: the first --error-lines lines, plus a few examples of
  every distinct handler message (executing, handling script, ...).

Anonymization: client and server addresses (IPv4 or IPv6), and any other
IPv4 address in a line, are replaced by pseudonyms in 10.0.0.0/8 (or
fd00::/8), derived with HMAC from a random key that is thrown away: the
same address maps to the same pseudonym within one run, but can't be
recovered. The cookie field of the access log is blanked.
"""
import argparse
import collections
import hashlib
import hmac
import random
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = secrets.token_bytes(32)

# an IPv4 address anywhere in the line (referers etc.), but not inside a
# version string such as Chrome/145.0.0.0 or a longer dotted token
IPV4 = re.compile(r"(?<![\w./])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
# client and server address fields: start of an access_log line,
# "[client <ip>:<port>]" in error_log (these may also be IPv6)
ACCESS_IPS = re.compile(r"^(\S+) (\S+) ")
ERROR_CLIENT = re.compile(r"\[client (.+?):(\d+)\]")
# combined log format + "cookie" "via": isolate the cookie field
_Q = r'"(?:[^"\\]|\\.)*"'
ACCESS = re.compile(rf'^(\S+ \S+ \S+ \S+ \[[^\]]+\] {_Q} \d+ \S+ {_Q} {_Q}) (.*) ({_Q})\s*$')
_cache = {}


def pseudonym(ip):
    if ip not in _cache:
        d = hmac.new(KEY, ip.encode(), hashlib.sha256).digest()
        _cache[ip] = (f"10.{d[0]}.{d[1]}.{d[2]}" if ":" not in ip
                      else "fd00::" + ":".join(f"{d[i]:02x}{d[i+1]:02x}" for i in (0, 2, 4)))
    return _cache[ip]


def anonymize_access(line):
    m = ACCESS.match(line)
    if m:  # blank the cookie field
        line = f'{m.group(1)} "-" {m.group(3)}\n'
    line = ACCESS_IPS.sub(lambda m: f"{pseudonym(m.group(1))} {pseudonym(m.group(2))} ", line, count=1)
    return IPV4.sub(lambda m: pseudonym(m.group(1)), line)


def anonymize_error(line):
    line = ERROR_CLIENT.sub(lambda m: f"[client {pseudonym(m.group(1))}:{m.group(2)}]", line)
    return IPV4.sub(lambda m: pseudonym(m.group(1)), line)


def endpoint(line):
    m = re.search(r'"[A-Z]+ (\S+)', line)
    if not m:
        return "?"
    path = m.group(1).split("?")[0]
    seg = path.lstrip("/").split("/")
    name = "/cgi-bin/" + seg[1] if seg[0] == "cgi-bin" and len(seg) > 1 else "/" + seg[0]
    return re.sub(r"\d+", "#", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-endpoint", type=int, default=25)
    ap.add_argument("--error-lines", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)

    groups = collections.defaultdict(list)
    with open(ROOT / "logs" / "access_log", encoding="latin-1") as f:
        for n, line in enumerate(f):
            groups[endpoint(line)].append((n, line))
    picked = []
    for g in groups.values():
        picked += g if len(g) <= args.per_endpoint else random.sample(g, args.per_endpoint)
    picked.sort()
    with open(ROOT / "logs" / "access_log.sample", "w", encoding="latin-1") as out:
        for _, line in picked:
            out.write(anonymize_access(line))

    kinds = collections.Counter()
    kept = []
    with open(ROOT / "logs" / "error_log", encoding="latin-1") as f:
        for n, line in enumerate(f):
            m = re.search(r"legacy_handler: (\D{0,30}?)(?:[\"/]|https?:|$)", line)
            kind = m.group(1).strip() if m else line[:40]
            kinds[kind] += 1
            if n < args.error_lines or kinds[kind] <= 3:
                kept.append(line)
    with open(ROOT / "logs" / "error_log.sample", "w", encoding="latin-1") as out:
        for line in kept:
            out.write(anonymize_error(line))
    print(f"access_log.sample: {len(picked)} lines from {len(groups)} endpoints; "
          f"error_log.sample: {len(kept)} lines; {len(_cache)} addresses anonymized")


if __name__ == "__main__":
    main()
