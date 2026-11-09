"""Unit tests for cgi-bin/legacy_handler.   python3 -m unittest discover tests"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANDLER = ROOT / "cgi-bin" / "legacy_handler"
B = "https://scixplorer.org"


sys.dont_write_bytecode = True  # keep cgi-bin/ free of __pycache__


def load():
    loader = importlib.machinery.SourceFileLoader("legacy_handler", str(HANDLER))
    spec = importlib.util.spec_from_loader("legacy_handler", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


LH = load()


def go(uri, method="GET", base=B):
    qs = uri.partition("?")[2]
    req = LH.request_from_env({"REQUEST_METHOD": method, "REQUEST_URI": uri, "QUERY_STRING": qs})
    return LH.handle(req, base)


class Redirects(unittest.TestCase):
    def check(self, uri, url, status=301):
        self.assertEqual(go(uri), (status, url), uri)

    def test_search_scripts(self):
        self.check("/cgi-bin/basic_connect?qsearch=10.1126%2Fscience.1087251",
                   f"{B}/tugboat/classicSearchRedirect?qsearch=10.1126%2Fscience.1087251")
        self.check("/cgi-bin/nph-abs_connect?author=Accomazzi",
                   f"{B}/tugboat/classicSearchRedirect?author=Accomazzi")
        self.check("/cgi-bin/abs_connect", f"{B}/classic-form/")
        self.check("/cgi-bin/basic_connect", B)

    def test_bib_query(self):
        self.check("/cgi-bin/bib_query?1979Tectp..58...21P", f"{B}/abs/1979Tectp..58...21P")
        self.check("/cgi-bin/nph-bib_query?bibcode=1979Tectp..58...21P&db_key=AST",
                   f"{B}/abs/1979Tectp..58...21P?db_key=AST")
        self.check("/cgi-bin/bib_query?2018A&A...610A..71T", f"{B}/abs/2018A&A...610A..71T")
        self.check("/cgi-bin/bib_query", None, 404)

    def test_data_query(self):
        self.check("/cgi-bin/nph-data_query?link_type=ABSTRACT&bibcode=2012PLoSO...742190C",
                   f"{B}/link_gateway/2012PLoSO...742190C/abstract")
        self.check("/cgi-bin/nph-data_query?bibcode=2016A&A...590A.124R&link_type=ARTICLE",
                   f"{B}/link_gateway/2016A&A...590A.124R/article")
        self.check("/cgi-bin/nph-data_query?bibcode=1990ApJ...365..704S&link_type=GIF",
                   f"{B}/link_gateway/1990ApJ...365..704S/ads_scan")
        self.check("/cgi-bin/nph-data_query?link_type=ABSTRACTbibcode=1957AJ.....62...90B",
                   f"{B}/link_gateway/1957AJ.....62...90B/abstract")
        self.check("/cgi-bin/nph-data_query?A...415..145B&bibcode=2004A&link_type=ABSTRACT",
                   f"{B}/link_gateway/2004A&A...415..145B/abstract")

    def test_refs(self):
        self.check("/cgi-bin/nph-ref_query?bibcode=1976ApJ...203..297S&refs=REFERENCES",
                   f"{B}/abs/1976ApJ...203..297S/references")
        self.check("/cgi-bin/nph-ref_query?1976ApJ...203..297S&refs=AR", f"{B}/abs/1976ApJ...203..297S/coreads")
        self.check("/cgi-bin/nph-ref_history?refs=AR&bibcode=1976ApJ...203..297S",
                   f"{B}/abs/1976ApJ...203..297S/metrics")

    def test_identifiers(self):
        self.check("/abs/1976ApJ...203..297S", f"{B}/abs/1976ApJ...203..297S/abstract")
        self.check("/abs/2013A&amp;A...549A..39A", f"{B}/abs/2013A&A...549A..39A/abstract")
        self.check("/abs/1976ApJ...203..297S/citations", f"{B}/abs/1976ApJ...203..297S/citations")
        self.check("/doi/10.1086/166606", f"{B}/abs/10.1086/166606")
        self.check("/arXiv/2101.00001", f"{B}/abs/2101.00001/abstract")
        self.check("/abs?bibcode=1999ApJ...525C.597A", f"{B}/abs/1999ApJ...525C.597A/abstract")
        self.check("/abs/", None, 404)

    def test_full(self):
        self.check("/full/1990ApJ...365..704S", f"{B}/scan/manifest/1990ApJ...365..704S?art=true")
        self.check("/full/1990ApJ...365..704S/0000704.000.html",
                   f"{B}/scan/manifest/1990ApJ...365..704S?art=true")
        self.check("/full/2013A%26A...549A..39A", f"{B}/scan/manifest/2013A&A...549A..39A?art=true")
        self.check("/full/seri/ApJ../0365/0000704.000.html",
                   f"{B}/scan/search?q=bibstem%3AApJ%20AND%20volume%3A365%20AND%20page%3A704")
        self.check("/full/gif/1990ApJ...365..704S/0000704.000.html",
                   f"{B}/scan/manifest/1990ApJ...365..704S?art=true")
        self.check("/full/", None, 404)

    def test_iarticle_query(self):
        self.check("/cgi-bin/nph-iarticle_query?1979ApJ...233..906K",
                   f"{B}/scan/search?q=bibcode%3A1979ApJ...233..906K")
        self.check("/cgi-bin/nph-iarticle_query?bibcode=1986Icar...65...13H&data_type=GIF&db_key=AST&page_ind=0",
                   f"{B}/scan/search?q=bibcode%3A1986Icar...65...13H")
        self.check("/cgi-bin/nph-iarticle_query?journal=MNRAS&year=%3F%3F%3F%3F&volume=..33&letter=.&db_key=AST"
                   "&page_ind=305&plate_select=NO&data_type=GIF&type=SCREEN_GIF",
                   f"{B}/scan/search?q=bibstem%3AMNRAS%20AND%20volume%3A33%20AND%20page_sequence%3A306")
        self.check("/cgi-bin/nph-article_query?bibcode=1994AJ....108.2233W&page=1&type=GIF",
                   f"{B}/scan/search?q=bibcode%3A1994AJ....108.2233W%20AND%20page%3A1")
        self.check("/cgi-bin/nph-iarticle_query", None, 404)

    def test_account(self):
        self.check("/cgi-bin/nph-manage_account?man_cmd=login&man_url=x", f"{B}/user/account/login")
        self.check("/cgi-bin/manage_account?man_cmd=register", f"{B}/user/account/register")
        self.check("/cgi-bin/nph-manage_account", f"{B}/user/settings")
        self.check("/cgi-bin/myads2_set", f"{B}/user/notifications")

    def test_forms_and_pages(self):
        self.check("/", B)
        self.check("/index.html", B)
        self.check("/abstract_service.html", f"{B}/classic-form/")
        self.check("/abstract_service.html/legacy", f"{B}/classic-form/")
        self.check("/ast_bib.html", f"{B}/paper-form/")
        self.check("/mighty_search.html", B)
        self.check("/adsug.html", "http://adsabs.github.io/about/adsug/")
        self.check("/books/hsaa/", "http://ads.harvard.edu/books/hsaa/")
        self.check("/books", "http://ads.harvard.edu/books/")

    def test_404_and_302(self):
        self.check("/cgi-bin/nph-abs_connect?data_type=XML&author=x", None, 404)
        self.check("/cgi-bin/nph-toc_query?journal=ApJ&data_type=RSS", None, 404)
        self.check("/cgi-bin/abs_connect?library&author=x", None, 404)
        self.check("/cgi-bin/author_form", None, 404)
        self.check("/cgi-bin/nph-toc_query?journal=ApJ", None, 404)
        self.check("/journals_service.html", B, 302)
        self.check("/abs_doc/help_pages/data.html", B, 302)
        self.check("/pdf/1990ApJ...365..704S", B, 302)

    def test_script_name_junk(self):
        self.check("/cgi-bin/%20nph-bib_query?1979Tectp..58...21P", f"{B}/abs/1979Tectp..58...21P")
        self.check("//cgi-bin/nph-%0Abib_query?1979Tectp..58...21P", f"{B}/abs/1979Tectp..58...21P")

    def test_base_url(self):
        self.assertEqual(LH.base_url({}), "https://scixplorer.org")
        self.assertEqual(LH.base_url({"SCIX_ENV": "dev"}), "https://dev.scixplorer.org")
        self.assertEqual(LH.base_url({"SCIX_BASE_URL": "http://localhost:8000/"}), "http://localhost:8000")


class CGI(unittest.TestCase):
    """run the script as a CGI process"""
    def run_cgi(self, uri, method="GET", body=b"", **extra):
        env = {"PATH": os.environ.get("PATH", ""), "REQUEST_METHOD": method, "REQUEST_URI": uri,
               "QUERY_STRING": uri.partition("?")[2], "CONTENT_LENGTH": str(len(body)), **extra}
        out = subprocess.run([sys.executable, str(HANDLER)], env=env, input=body,
                             capture_output=True, check=True).stdout
        head, _, rest = out.partition(b"\r\n\r\n")
        return dict(l.split(": ", 1) for l in head.decode().split("\r\n")), rest

    def test_get(self):
        h, body = self.run_cgi("/cgi-bin/bib_query?1979Tectp..58...21P")
        self.assertEqual(h["Status"], "301 Moved Permanently")
        self.assertEqual(h["Location"], f"{B}/abs/1979Tectp..58...21P")
        self.assertIn(b"1979Tectp..58...21P", body)

    def test_head(self):
        h, body = self.run_cgi("/doi/10.1086/166606", method="HEAD")
        self.assertEqual(h["Location"], f"{B}/abs/10.1086/166606")
        self.assertEqual(body, b"")

    def test_post(self):
        h, _ = self.run_cgi("/cgi-bin/nph-abs_connect", method="POST", body=b"author=Accomazzi&db_key=AST")
        self.assertEqual(h["Location"], f"{B}/tugboat/classicSearchRedirect?author=Accomazzi&db_key=AST")

    def test_dev(self):
        h, _ = self.run_cgi("/full/1990ApJ...365..704S", SCIX_ENV="dev")
        self.assertEqual(h["Location"], "https://dev.scixplorer.org/scan/manifest/1990ApJ...365..704S?art=true")

    def test_404(self):
        h, body = self.run_cgi("/cgi-bin/author_form")
        self.assertEqual(h["Status"], "404 Not Found")
        self.assertNotIn("Location", h)

    def test_302(self):
        h, _ = self.run_cgi("/abs_doc/help.html")
        self.assertEqual(h["Status"], "302 Found")
        self.assertEqual(h["Location"], B)


if __name__ == "__main__":
    unittest.main()
