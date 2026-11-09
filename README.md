# classic_redirects

Redirects ADS Classic URLs (adsabs.harvard.edu, articles.adsabs.harvard.edu)
to SciX (https://scixplorer.org). It replaces the Perl `legacy_handler` that
ran under Apache; see `REQUIREMENTS.md` for the background and requirements.

## Contents

| Path | What it is |
|---|---|
| `cgi-bin/legacy_handler` | The handler: a single Python 3.14 CGI script, standard library only |
| `nginx/classic_redirects.conf` | Sample nginx + fcgiwrap configuration |
| `tests/test_legacy_handler.py` | Unit tests |
| `tests/replay.py` | Replays `logs/access_log` through the old Perl handler and the new one and reports differences |
| `tests/replay_report.txt` | Output of the last replay |
| `legacy/legacy_handler.pl` | The original Perl handler, kept for reference and used by the replay |
| `cgi-bin/cgi-bin.htaccess`, `htdocs/htdocs.htaccess` | The old Apache rules, for reference (their redirects now live in the handler) |
| `tests/make_log_sample.py` | Makes the anonymized log samples from the full logs |
| `logs/access_log.sample`, `logs/error_log.sample` | Anonymized samples of one day (November 8, 2026) of Apache logs from the Classic server |

## Deployment

nginx has no built-in CGI support, so the handler runs under
[fcgiwrap](https://github.com/gnosek/fcgiwrap). There is no content left to
serve: nginx sends **every** request to the handler, which never executes
anything locally. `nginx/classic_redirects.conf` is a starting point:

```nginx
location / {
    include fastcgi_params;
    fastcgi_param SCRIPT_FILENAME /srv/classic_redirects/cgi-bin/legacy_handler;
    fastcgi_param SCIX_ENV        prod;
    fastcgi_pass  unix:/run/fcgiwrap.socket;
}
```

Requirements:

* Python 3.14 as `python3` on the PATH of the fcgiwrap user (the script uses
  `#!/usr/bin/env python3`; it also runs on 3.10+). No third-party packages.
* `cgi-bin/legacy_handler` must be executable.
* nginx must pass `REQUEST_URI`, `QUERY_STRING`, `REQUEST_METHOD` and
  `CONTENT_LENGTH` (the stock `fastcgi_params` does). The handler reads the
  path from `REQUEST_URI`, falling back to `DOCUMENT_URI` or
  `SCRIPT_NAME` + `PATH_INFO`.
* The same configuration can serve both adsabs.harvard.edu and
  articles.adsabs.harvard.edu (where `/full` URLs come from).

### Configuration

fcgiwrap exports every `fastcgi_param` to the script as an environment variable.

| Variable | Effect |
|---|---|
| `SCIX_ENV` | `prod` (default) → `https://scixplorer.org`; `dev` → `https://dev.scixplorer.org` |
| `SCIX_BASE_URL` | Overrides the base URL entirely (useful for testing) |

### Logging

The handler logs one or two lines per request to stderr, prefixed with
`legacy_handler:`: how the request was understood (endpoint, path, query),
then the outcome (`301 redirect to ...`, `404`, ...). fcgiwrap forwards
stderr to the nginx error log.

## Behaviour

Every request ends in one of three responses:

* **301 Moved Permanently** when the endpoint is in the redirect map.
* **302 Found** to the SciX home page for an htdocs document (anything not
  under `/cgi-bin/`) that has no mapping.
* **404 Not Found**
  * for a `/cgi-bin/` script with no mapping (`author_form`, `toc_query`,
    `journal_query`, `list_connect`, ...). These used to be executed locally;
  * for a `/cgi-bin/` request asking for machine-readable output that SciX
    doesn't provide (`data_type=XML|RSS|VOTABLE|REFMAN|PORTABLE|Custom`);
  * for `abs_connect` with a `library` parameter;
  * for a mapped endpoint whose parameters can't be translated, e.g.
    `bib_query` with no bibcode, or `/full/` with nothing after it.

Responses carry a short HTML body with a link to the target, except for HEAD
requests. POST requests are handled like GET, with the body as the query string.

### Redirect map

Paths are relative to the SciX base URL unless shown in full.

| Classic | SciX |
|---|---|
| `/cgi-bin/abs_connect?...` | `/tugboat/classicSearchRedirect?...` (no query: `/classic-form/`) |
| `/cgi-bin/basic_connect?...` | `/tugboat/classicSearchRedirect?...` (no query: home page) |
| `/cgi-bin/bib_query?<bibcode>&...` | `/abs/<bibcode>?<remaining params>` |
| `/cgi-bin/data_query?bibcode=X&link_type=T` | `/link_gateway/X/<t>` (type mapping below) |
| `/cgi-bin/ref_query?bibcode=X&refs=T` | `/abs/X/citations`, `/abs/X/references` or `/abs/X/coreads` (default `citations`) |
| `/cgi-bin/ref_history?bibcode=X` | `/abs/X/metrics` |
| `/cgi-bin/iarticle_query?...`, `/cgi-bin/article_query?...` | `/scan/search?q=...` (see [Scan explorer](#scan-explorer)) |
| `/cgi-bin/manage_account?man_cmd=login` | `/user/account/login` |
| `/cgi-bin/manage_account?man_cmd=register` | `/user/account/register` |
| `/cgi-bin/manage_account` (anything else) | `/user/settings` |
| `/cgi-bin/myads_set`, `myads2_set`, `exec_myads2` | `/user/notifications` |
| `/abs/<id>`, `/arXiv/<id>`, `/abs?bibcode=<id>` | `/abs/<id>/abstract` (path kept as is if it already has a sub-page) |
| `/doi/<doi>` | `/abs/<doi>` |
| `/full/<bibcode>[/...]`, `/full/gif/<bibcode>/...` | `/scan/manifest/<bibcode>?art=true` |
| `/full/seri/<J>/<vol>/<page>...` | `/scan/search?q=bibstem:J AND volume:V AND page:P` |
| `/`, `/index.html`, `/mighty_search.html` | home page |
| `basic_search.html`, `basic_service.html`, `quick_service.html`, `fulltext_service.html`, `advanced_fulltext_service.html` | home page |
| `abstract_service.html`, `physics_service.html`, `preprint_service.html`, `general_service.html`, `education_service.html`, `default_service.html` | `/classic-form/` |
| `ast_bib.html`, `pre_bib.html`, `gen_bib.html`, `phy_bib.html`, `custom_bib.html`, `bib_abs.html` | `/paper-form/` |
| `/adsug.html` | `http://adsabs.github.io/about/adsug/` |
| `/local/...`, `/mirror/...`, `/z3950/...`, `/www/...`, `/books/...`, `/BOBeo/...`, `/pubs/...`, `/cfa/...` | `http://ads.harvard.edu/<same path>` |

`data_query` link types (case-insensitive; unknown types give `/link_gateway/X`):

| `link_type` | link_gateway | `link_type` | link_gateway |
|---|---|---|---|
| ABSTRACT | abstract | NED | ned |
| CITATIONS | citations | ASSOCIATED | associated |
| DATA | data | PDS | pds |
| EJOURNAL | pub_html | REFERENCES | references |
| ARTICLE | article | SIMBAD | simbad |
| GIF | ads_scan | TOC | toc |
| SPIRES | inspire | AR | coreads |
| LIBRARY | librarycatalog | PREPRINT | eprint_html |
| VIDEO | presentation | | |

### Scan explorer

`iarticle_query` and `article_query` parameters are translated into the scan
explorer's single `q` parameter (URL-encoded, terms joined with `AND`):

| Classic parameter | Scan explorer term |
|---|---|
| `bibcode=X` (or a bare `?X`) | `bibcode:X` |
| `journal=J` (used only when there is no bibcode) | `bibstem:J`, padding dots removed |
| `volume=..33` | `volume:33`, padding dots and leading zeros removed |
| `page_ind=N` (journal/volume browsing only) | `page_sequence:N+1` |
| `page=P` | `page:P` |

For example
`iarticle_query?journal=MNRAS&volume=..33&page_ind=305&data_type=GIF` →
`/scan/search?q=bibstem%3AMNRAS%20AND%20volume%3A33%20AND%20page_sequence%3A306`.

* `page_ind` is 0-based in Classic; `page_sequence` is taken to be 1-based.
* `page_ind` is dropped for bibcode queries, where it is an offset within the
  article that the scan explorer can't express.
* Display parameters (`data_type`, `type`, `db_key`, `plate_select`, `letter`,
  `year`, `classic`, ...) are ignored.

`/full/seri/<J>/<vol>/<page>` URLs (e.g. `/full/seri/ApJ../0365/0000704.000.html`)
become a search on `bibstem`, `volume` and `page` with the same cleanup.

## Implementation

`cgi-bin/legacy_handler` is organised top to bottom as follows.

### 1. Request parsing — `request_from_env()`

Builds a `Request` (dataclass) from the CGI environment:

| Field | Meaning |
|---|---|
| `method` | `REQUEST_METHOD` |
| `is_cgi` | the path starts with `/cgi-bin/` |
| `endpoint` | for `/cgi-bin/` the script name, otherwise the first path segment (`abs`, `full`, `abstract_service.html`, `""` for `/`) |
| `path_info` | the rest of the path after the endpoint, e.g. `/2013A&A...549A..39A` |
| `qs` | the raw query string, or the POST body |
| `params` | the parsed parameters |

Under Apache the Perl script found the original script by walking the file
system from `PATH_TRANSLATED`. The files no longer exist, so the endpoint is
now derived from the URL alone. Script names are cleaned up by
`clean_script()`: whitespace is removed (log entries such as
`/cgi-bin/%20nph-bib_query` and `nph-%0Abib_query`) and the `nph-` prefix is
stripped. Leading double slashes (`//cgi-bin/...`) are collapsed; slashes
inside the path are kept, so `/abs/https://...` style paths survive.

### 2. Parameter parsing — `parse_params()`

A port of the Perl `ReadParse`, since the `cgi` module was removed from the
standard library in Python 3.13:

* parameters are split on `&` or `&amp;`; `+` becomes a space; `%XX` is decoded;
* a key starting with `amp;` (from an encoded `&amp%3B`) loses that prefix;
* repeated keys are joined with `\0`, as in Perl;
* for GET and HEAD, `fix_bibcode_amp()` first re-encodes an unencoded `&` in a
  19-character bibcode, either after `bibcode=` or as a bare leading parameter
  (`bibcode=2016A&A...590A.124R`, `bib_query?2018A&A...610A..71T`).

**Byte handling.** Strings are handled as latin-1 "byte strings" (one
character per byte), as the Perl script handled bytes. `as_bytestr()` converts
environment strings, `unescape()` decodes `%XX` to single bytes, `escape()`
re-encodes path components with the same character set as the Perl
`escape()`, and `safe_url()` percent-encodes anything left that isn't
printable ASCII before it goes into the `Location` header. Non-ASCII input
(UTF-8 or otherwise) therefore round-trips byte for byte.

### 3. Bibcode extraction — `bib_extract()`

Returns `(bibcode, remaining params)` from `?bibcode=X&...` or a bare `?X&...`
(the first parameter with an empty value). It also repairs two breakages that
are common in the logs:

* `?link_type=ABSTRACTbibcode=X` (missing `&`): the bibcode is taken out of
  the value, and `link_type` keeps `ABSTRACT`;
* `?A...415..145B&bibcode=2004A&link_type=...` (an unencoded `&` split the
  bibcode): a short bibcode is joined with an empty-valued parameter when
  together they make 19 characters.

### 4. Rules — `build_redirect_map(base)`

The redirect map is a dict from endpoint name to a *rule*: a function that
takes a `Request` and returns the target URL, or `None` when the request
can't be translated (which becomes a 404). Rules are built by small factories:

| Factory | Behaviour | Perl equivalent |
|---|---|---|
| `fixed(url)` | always `url` | `nopath` |
| `passthrough(url, noparams)` | `url` + path + `?query`; `noparams` if both are empty | no `map` + `noparams` |
| `bibpath(url)` | `/abs`, `/doi`, `/arXiv` identifiers | `bibpath` |
| `bib2abs(url)` | `bib_query` | `bib2abspath` |
| `ref2abs(url)` | `ref_query` | `ref2abspath` |
| `refhist2abs(url)` | `ref_history` | `refhist2abspath` |
| `data2resolver(url)` | `data_query` → link_gateway | `data2resolver` |
| `full2scan(url)` | `/full` → scan explorer | new |
| `iarticle2scan(url)` | `iarticle_query`, `article_query` → scan search | new |
| `account(url)` | `manage_account` → user pages | new |
| `ads_harvard(seg)` | `/local`, `/books`, ... → ads.harvard.edu | `htdocs.htaccess` `RedirectMatch` |

The map is built per request from the base URL, so production and dev differ
only in `SCIX_ENV`.

### 5. Dispatch — `handle(req, base)`

Returns `(status, url)`:

1. For `/cgi-bin/` requests: a `data_type` in `MACHINE_READABLE`, or a
   parameter listed in `LOCAL_ONLY_PARAMS` for that script → 404.
2. Endpoint in the map → run the rule: 301 to its URL, or 404 if it returned `None`.
3. Unmapped `/cgi-bin/` script → 404.
4. Anything else → 302 to the SciX home page.

### 6. Response — `respond()` and `main()`

`respond()` writes the CGI headers (`Status`, `Content-Type`, `Location`)
and, except for HEAD, a small HTML body. `main()` ties the steps together
and catches unexpected exceptions: they are logged with a traceback and the
client gets a 302 to the home page, so a bug never produces a broken page.

### Adding or changing a redirect

* **New endpoint with a fixed target:** add `"name": fixed(f"{base}/...")`
  to `rmap` in `build_redirect_map()`. Use the script name without `nph-`
  for cgi-bin scripts, the first path segment for documents.
* **New endpoint that needs its parameters translated:** write a factory
  that returns `rule(req)`, use `bib_extract()` for bibcodes and `escape()`
  for path components, and return `None` when the request can't be
  translated.
* **Stop serving machine-readable output for another data type:** add it to
  `MACHINE_READABLE`.
* Add a case to `tests/test_legacy_handler.py` for each change.

## Changes from the Perl handler

* All redirects point to `scixplorer.org` / `dev.scixplorer.org`, chosen by
  `SCIX_ENV`, instead of `ui.adsabs.harvard.edu` / `dev.adsabs.harvard.edu`.
* Nothing is executed locally. Requests that used to be (`author_form`,
  `toc_query`, `list_connect`, XML/RSS output from `abs_connect`, ...)
  return 404; static htdocs documents get a 302 to the home page instead of
  being served through `insert_login`.
* New rules for `/full`, `iarticle_query`/`article_query`, `manage_account`
  and the myADS scripts.
* The redirects from `htdocs.htaccess` moved into the handler.
  `mighty_search.html` goes to the home page, as the `.htaccess` rule did.
* The `debug` parameter, which printed the server environment, is gone.
* Mapped endpoints that can't be translated (no bibcode, etc.) return 404
  instead of redirecting to a bare `/abs` or `/link_gateway`.
* Malformed URLs are repaired more often (unencoded `&` in bibcodes, missing
  `&` before `bibcode=`, `&amp;`, junk in script names, `/abs?bibcode=X`).
* Bibcode extraction is deterministic: Perl picked the first empty-valued
  parameter in hash order, which was random.

## Testing

```sh
python3 -m unittest discover tests            # unit tests
python3 tests/replay.py --out tests/replay_report.txt   # replay against the Perl handler
```

The unit tests call the handler's functions directly and also run it as a CGI
process (GET, HEAD, POST, `SCIX_ENV=dev`, 404 and 302).

`tests/replay.py` takes the unique URLs in `logs/access_log` (or
`logs/access_log.sample` when the full log isn't there; `--log` picks another file), up to
`--per-endpoint` (default 1500) per endpoint, and runs each through both
handlers. The Perl handler runs against a temporary file tree that imitates
the old server, with stub scripts standing in for the local programs. The
Perl targets are rewritten from `ui.adsabs.harvard.edu` to `scixplorer.org`,
and query parameters are compared without regard to order. The report counts
outcomes per endpoint (`301 same`, `301 DIFFERENT`, `perl 299 -> python 404`,
where 299 means "Perl executed a local program") and lists every difference.
On the November 8, 2026 logs, every difference is either one of the
intended rule changes above or a repaired malformed URL.

### Log samples

The full logs (`logs/access_log`, `logs/error_log`, about 180 MB) are not in
git: they are too large and contain visitors' IP addresses. The repository
keeps anonymized samples made with

```sh
python3 tests/make_log_sample.py [--per-endpoint 25] [--error-lines 1000]
```

* `access_log.sample` has up to 25 random requests for every endpoint (cgi-bin
  script or first path segment, with numbers collapsed so that e.g. all
  `sitemap_bib.NNNN.xml.gz` files count as one), so rare endpoints are all
  represented.
* `error_log.sample` has the first 1000 lines plus up to three examples of
  every distinct handler message.
* Client and server addresses, and any other IPv4 address in a line, are
  replaced by pseudonyms in 10.0.0.0/8 (fd00::/8 for IPv6), computed with an
  HMAC whose random key is discarded: an address keeps the same pseudonym
  throughout one sample but can't be recovered. The cookie field of the
  access log is replaced by `-`.

`tests/replay_report.txt` was produced from the full access log.

## Open points

* The SciX paths `/tugboat/classicSearchRedirect`, `/classic-form/` and
  `/paper-form/` are carried over from the ADS user interface, and the account
  paths (`/user/account/login`, `/user/account/register`, `/user/settings`,
  `/user/notifications`) are assumed. All of them should be checked on
  scixplorer.org.
* The mapping of `page_ind` to `page_sequence` assumes the scan explorer's
  sequence numbers start at 1.
