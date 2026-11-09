# Background

This repo contains the script that handles redirections from the ADS classic URLs and the ones handled by "ADS bumblebee" and eventually the Science Explorer (or SciX).

The environment for the redirection is the CGI-BIN environment typically run under the Apache http daemon. The system is configured as follows:

- `cgi-bin`: folder where the CGI scripts reside; since we no longer want to execute scripts locally, we will rely on just a single executable, `legacy_handler` to redirect or execute locally all incoming requests. The file `cgi-bin.htaccess` provides the access control rules
- `htdocs`: folder where the original content (files and folders) used to live, including URLs that required script execution such as `abstract_service.html.` The file `htdocs.htaccess` provides the access control rules.
- `logs` contain sample log entries collected from the current http daemon. Since the `legacy_handler` produces verbose output sent to stderr, most of the information regarding which actions are being taken can be found there.

# Requirements

The original implementation consisted in the perl script `cgi-bin/legacy_handler` which had a set of rules which determined whether a request to a particular URL would trigger a redirection or a local execution of a binary executable. We want to translate the script to a minimal python (3.14) script with as few dependencies as possible and make the following changes:

- The script will run under a CGI-BIN environment provided by nginx
- Update all redirection URLs to be under [https://scixplorer.org](https://scixplorer.org) and [https://dev.scixplorer.org](https://dev.scixplorer.org) rather than [https://ui.adsabs.harvard.edu](https://ui.adsabs.harvard.edu) and [https://dev.adsabs.harvard.edu](https://dev.adsabs.harvard.edu) 
- Create rules for redirecting the article service urls `/full`) using a function that maps parameters in the URLs to the ones accepted by the scan explorer ([https://scixplorer.org/scan](https://scixplorer.org/scan)) 
- No longer support execution of local binaries/scripts, which are not present in the new environment; if there is no redirection URL, we should respond with a 404
- If there is a request for a document in `htdocs` which is not in the `REDIRECT_MAP` then simply redirect the request to [https://scixplorer.org](https://scixplorer.org) with a 302.

## Redirects for /full/ urls

All URLs of the kind `/full/bibcode` should be redirected to https://scixplorer.org/scan/manifest/bibcode?art=true

## Redirects for scan explorer iarticle_query

URLs should be redirected using the syntax used by the scan explorer, which uses a single query parameter "q" containing the searchable fields. The syntax is https://scixplorer.org/scan/search?q=XXX, where XXX represents a URL-encoded elasticsearch syntax supporting the following parameters:
- bibcode - find scans associated with a particular bibcode
- bibstem - find scans for a journal with a particular bibstem
- page - find scans with a particular page number
- page_sequence - find scans with a particular scan sequence within the volume
- pagecolor - find scans with a particular; available colors are "bw", "grayscale" and "color"
- pagetype - find scans with a particular page type; available options are "normal", "backmatter", "frontmatter", "insert" and "plate"
- project - find scans associated with a particular project (example: project:PHaEDRA)
- volume - find scans associated with a particular volume (example: volume:10)
