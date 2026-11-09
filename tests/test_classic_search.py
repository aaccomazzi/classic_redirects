"""
tugboat's unit tests for the classic search translation
(tugboat/tests/tests_unit/test_search_redirect.py in github.com/adsabs/tugboat),
run against cgi-bin/classic_search.py.

The test bodies are unchanged. A small shim stands in for tugboat's view,
request and MultiDict, and rebuilds the string tugboat produced (query,
messages and trailing "/") from the translation, so the original
assertions apply as they are.
"""
import sys
import urllib.parse
import unittest
from unittest import TestCase
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cgi-bin"))
import classic_search  # noqa: E402


class MultiDict:
    """the bits of werkzeug's MultiDict the tests use (update() appends)"""
    def __init__(self, pairs=()):
        self.pairs = list(pairs)

    def update(self, other):
        self.pairs += other.pairs

    def as_lists(self):
        out = {}
        for k, v in self.pairs:
            out.setdefault(k, []).append(v)
        return out


class Request:
    def __init__(self, *a, **kw):
        self.args = MultiDict()

    def prepare(self):
        pass


def tugboat_string(t):
    """the string tugboat's ClassicSearchRedirectView.translate() returned"""
    q = t.query
    if t.error_message:
        q += '&error_message=' + '&error_message='.join(t.error_message)
    if not t.myads:
        if t.warning_message:
            q += '&warning_message=' + '&warning_message='.join(t.warning_message)
        if t.unprocessed_fields:
            q += '&unprocessed_parameter=' + '&unprocessed_parameter='.join(t.unprocessed_fields)
        if t.leftover:
            q += '&unprocessed_parameter=' + urllib.parse.quote('Parameters not processed: ' + ' '.join(t.leftover))
    return q + '/'


class ClassicSearchRedirectView:
    def translate(self, req):
        return tugboat_string(classic_search.translate(req.args.as_lists()))


class TestSearchParametersTranslation(TestCase):
    """
    Test translation of each of the classic search parameters

    """

    def append_defaults(self):
        return MultiDict([('aut_syn', 'YES'), ('ttl_syn', 'YES'), ('txt_syn', 'YES'),
                          ('aut_wt',  '1.0'), ('obj_wt',  '1.0'), ('ttl_wt',  '0.3'), ('txt_wt',  '3.0'),
                          ('aut_wgt', 'YES'), ('obj_wgt', 'YES'), ('ttl_wgt', 'YES'), ('txt_wgt', 'YES'),
                          ('ttl_sco', 'YES'), ('txt_sco', 'YES'),
                          ('sim_query', 'YES'), ('ned_query', 'YES'),
                          ('min_score', ''),
                          ('data_type', 'SHORT'),
                          ('start_entry_day', ''), ('start_entry_mon', ''), ('start_entry_year', ''),
                          ('end_entry_day', ''), ('end_entry_mon', ''), ('end_entry_year', '')])

    def test_authors(self):
        """authors: single, multple, quoted,  and/or"""

        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        empty_search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/', empty_search, 'author test')  # no authors

        req.args = MultiDict([('author', urllib.parse.quote('+Huchra, John'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        # parentheses are not urlencoded
        self.assertEqual('q=' + urllib.parse.quote('author:') + '(' + urllib.parse.quote('"Huchra, John"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # single author no quotes

        req.args = MultiDict([('author', urllib.parse.quote('Huchra\r\n-Huchra,John'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('author:') + '(' + urllib.parse.quote('"Huchra" AND -"Huchra,John"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # single author with quotes

        req.args = MultiDict([('author', urllib.parse.quote('Huchra, John\r\nMacri, Lucas M.'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('author:') + '(' + urllib.parse.quote('"Huchra, John" AND "Macri, Lucas M."') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # authors, newline separator

        req.args = MultiDict([('author', urllib.parse.quote('+Huchra, John;-Macri, Lucas M.'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('author:') + '(' + urllib.parse.quote('"Huchra, John" AND -"Macri, Lucas M."') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # authors, semicolon separator

        req.args = MultiDict([('author', urllib.parse.quote('Huchra, John')), ('aut_xct', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('=author:') + '(' + urllib.parse.quote('"Huchra, John"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # author with exact match

        # changing OR to AND and issuing a warning
        # 10/30/2019 From Alberto: let's recognize what boolean user has used
        req.args = MultiDict([('author', urllib.parse.quote('Huchra, John;Macri, Lucas M.')), ('aut_logic', 'OR')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('author:') + '(' + urllib.parse.quote('"Huchra, John" OR "Macri, Lucas M."') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # authors with or

        # first author
        req.args = MultiDict([('author', urllib.parse.quote('^Huchra, John'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + 'author:' + '"Huchra, John"' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # first author no quotes

        # single author
        req.args = MultiDict([('author', urllib.parse.quote('^Huchra, John$'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + '(author:"Huchra, John" and author_count:1)' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # single author no quotes

        # multi word last name author, no initials
        req.args = MultiDict([('author', urllib.parse.quote('^Dorigo Jones'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + 'author:"Dorigo Jones,"' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # single author, no initials, no quotes

        # multi word last name author, no initials, quoted
        req.args = MultiDict([('author', urllib.parse.quote('"^Dorigo Jones"'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        author_search = view.translate(req)
        self.assertEqual('q=' + 'author:"Dorigo Jones,"' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
                         '&format=SHORT' + '/',
                         author_search) # single author, no initials, with quotes

    def test_object(self):
        """object: single, multple, etc"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.args = MultiDict()
        req.mimetype = None

        req.args = MultiDict([('object', urllib.parse.quote('M31'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('object:') + '(' + urllib.parse.quote('"M31"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # single object

        req.args = MultiDict([('object', urllib.parse.quote('M31\r\nM32'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('object:') + '(' + urllib.parse.quote('"M31" AND "M32"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/',
                         search) # objects, newline separator

        req.args = MultiDict([('object', urllib.parse.quote('M31;M32;M33'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('object:') + '(' + urllib.parse.quote('"M31" AND "M32" AND "M33"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/',
                         search) # object, semicolor separator

        req.args = MultiDict([('object', urllib.parse.quote('GX 1+4'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('object:') + '(' + urllib.parse.quote('"GX 1+4"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

    def test_title(self):
        """title field"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('title', urllib.parse.quote('ADS'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +
                         urllib.parse.quote('title:') + '(' + urllib.parse.quote('ADS') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # single object

        req.args = MultiDict([('title', urllib.parse.quote('ADS Kurtz')), ('ttl_logic', 'OR')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +
                         urllib.parse.quote('title:') + '(' + urllib.parse.quote('ADS Kurtz') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # single object

    def test_text(self):
        """text search"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('text', urllib.parse.quote('M31'))])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +
                         urllib.parse.quote('abs:') + '(' + urllib.parse.quote('M31') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # single object

        req.args = MultiDict([('text', urllib.parse.quote('foo bar')), ('txt_logic', 'OR')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +
                         urllib.parse.quote('abs:') + '(' + urllib.parse.quote('foo bar') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # single object

    def test_pubdate(self):
        """test pubdate"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.args = MultiDict()
        req.args.update(self.append_defaults())
        req.mimetype = None
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)  # no pub date

        req.args = MultiDict([('start_year', 1990), ('end_year', 1991)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[1990-01 TO 1991-12]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)  # both years only

        req.args = MultiDict([('start_year', 1990), ('start_mon', 5), ('end_year', 1991), ('end_mon', 10)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[1990-05 TO 1991-10]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)  # years and months

        req.args = MultiDict([('start_year', 1990), ('end_year', 1991), ('end_mon', 10)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[1990-01 TO 1991-10]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # no start mon

        req.args = MultiDict([('start_year', 1990), ('start_mon', 5), ('end_year', 1991)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[1990-05 TO 1991-12]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # no end mon

        req.args = MultiDict([('start_year', 1990), ('start_mon', 5)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        n = datetime.now()
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[1990-05 TO *]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # no end

        req.args = MultiDict([('end_year', 1991), ('end_mon', 10)])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('pubdate:[* TO 1991-10]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search) # no start


    def test_database(self):
        """database can be astronomy or physics

        not clear how to test with more than one database set"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('db_key', 'AST')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        # the search query should be 'q=*:*&fq={!type=aqp v=$fq_database}&fq_database=(database:"astronomy")'
        # but with only some of the special characters html encoded
        self.assertEqual('filter_database_fq_database=OR' +
                         '&filter_database_fq_database=database:"astronomy"' +
                         '&q=*:*&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/',
                         search)  # astronomy only

        req.args = MultiDict([('db_key', 'PHY')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR' +
                         '&filter_database_fq_database=database:"physics"' +
                         '&q=*:*&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22physics%22)' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/',
                         search) # physics only

        req.args = MultiDict([('db_key', 'GEN')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'db_key' + '/', search) # general only

    def test_article_sel(self):
        """article_sel to property:article"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('article_sel', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_doctype_facet_hier_fq_doctype=AND' +
                         '&filter_doctype_facet_hier_fq_doctype=' + urllib.parse.quote_plus('doctype_facet_hier:"0/Article"') +
                         '&q=*:*&fq=' + urllib.parse.quote('{') + '!' + urllib.parse.quote('type=aqp v=$fq_doctype}') +
                         '&fq_doctype=(' + urllib.parse.quote_plus('doctype_facet_hier:"0/Article"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)
        req.args = MultiDict([('article_sel', 'NO')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'article_sel' + '/', search)

    def test_data_link(self):
        """data_link to property:data"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_link', 'YES'), ('data_and', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('esources:*') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_preprint_link(self):
        """preprint_link to property:eprint"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('preprint_link', 'YES'), ('data_and', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('esources:("EPRINT_HTML")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_open_link(self):
        """open_link to property:OPENACCESS"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('open_link', 'YES'), ('data_and', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("OPENACCESS")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_multiple_link_properties(self):
        """multiple Bumblebee property fields set"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('open_link', 'YES'), ('data_link', 'YES'), ('data_and', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=(' + urllib.parse.quote('esources:*') + ' AND ' +  urllib.parse.quote('property:("OPENACCESS")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_classic_parameters_entry_date(self):
        """test entry date"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # no pub date

        req.args = MultiDict([('start_entry_year', "1990"), ('end_entry_year', "1991")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-01-02:00:00" TO "1992-01-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # both years only

        req.args = MultiDict([('start_entry_year', "1990"), ('start_entry_mon', "5"),
                              ('end_entry_year', "1991"), ('end_entry_mon', "9")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-05-02:00:00" TO "1991-10-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # years and months

        req.args = MultiDict([('start_entry_year', "1990"), ('end_entry_year', "1991"), ('end_entry_mon', "10")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-01-02:00:00" TO "1991-11-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # no start mon

        req.args = MultiDict([('start_entry_year', "1990"), ('start_entry_mon', "5"), ('end_entry_year', "1991")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-05-02:00:00" TO "1992-01-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # no end mon

        req.args = MultiDict([('start_entry_year', "1990"), ('start_entry_mon', "5")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-05-02:00:00" TO "{}"]'.format(datetime.now().strftime("%Y-%m-%d"))) +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # no end
        req.args = MultiDict([('end_entry_year', "1991"), ('end_entry_mon', "10")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["0001-01-01:00:00" TO "1991-11-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # no start

        req.args = MultiDict([('start_entry_year', "1990"), ('start_entry_mon', "5"), ('start_entry_day', "6"),
                              ('end_entry_year', "1991"), ('end_entry_mon', "9"), ('end_entry_day', "10")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-05-07:00:00" TO "1991-09-11"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # years, months, days

        req.args = MultiDict([('start_entry_year', "90"), ('end_entry_year', "10")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('entdate:["1990-01-02:00:00" TO "2011-01-01"]') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # years, months, days

        req.args = MultiDict([('start_entry_year', "26"), ('end_entry_year', "22")])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        # updated: a 2-digit year 26 now means 2026 (the original test, written in 2023,
        # expected 1926); 2-digit years are read as at most next year
        y26 = 2026 if 2026 <= datetime.now().year + 1 else 1926
        self.assertEqual('q=' + urllib.parse.quote('entdate:["{}-01-02:00:00" TO "2023-01-01"]'.format(y26)) +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # years, months, days

    def test_classic_results_subset(self):
        """test results subset"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # no results subset

        req.args = MultiDict([('nr_to_return', 20) , ('start_nr', 1)])
        view = ClassicSearchRedirectView()
        req.args.update(self.append_defaults())
        search = view.translate(req)
        # disabled this for now since it is not implemented, not that it is an error
        # self.assertTrue('error_message' in search)  # both number to return and start index

        req.args = MultiDict([('nr_to_return', 20)])
        view = ClassicSearchRedirectView()
        req.args.update(self.append_defaults())
        search = view.translate(req)
        # self.assertTrue('error_message' in search)  # only number to return

        req.args = MultiDict([('start_nr', 1)])
        view = ClassicSearchRedirectView()
        req.args.update(self.append_defaults())
        search = view.translate(req)
        # self.assertTrue('error_message' in search)  # only start index

    def test_return_req(self):
        """test results subset"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # no value

        req.args = MultiDict([('return_req', 'result')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # only valid value

        req.args = MultiDict([('return_req', 'no_params')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # another valid value as of 1/13/2020

        req.args = MultiDict([('return_req', 'form')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertTrue('error_message' in search)  # unsuppoprted value for return_req
        self.assertTrue('UNRECOGNIZABLE_VALUE' in search)  # unsuppoprted value for return_req

    def test_jou_pick(self):
        """test jou_pick (refereed)"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # no value

        req.args = MultiDict([('jou_pick', 'ALL')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # no clause should be specified, defaults to all

        req.args = MultiDict([('jou_pick', 'NO')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_property_fq_property=AND' +
                         '&filter_property_fq_property=property:"refereed"' +
                         '&q=*:*&fq=' + urllib.parse.quote('{') + '!' + urllib.parse.quote('type=aqp v=$fq_property}') +
                         '&fq_property=(' + urllib.parse.quote('property:("refereed")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search) # only refereed

        req.args = MultiDict([('jou_pick', 'EXCL')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_property_fq_property=AND' +
                         '&filter_property_fq_property=property:"not refereed"' +
                         '&q=*:*&fq=' + urllib.parse.quote('{') + '!' + urllib.parse.quote('type=aqp v=$fq_property}') +
                         '&fq_property=(' + urllib.parse.quote('property:("not refereed")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)    # exclude refereed

        req.args = MultiDict([('jou_pick', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertTrue('error_message' in search)  # invalid value for jou_pick
        self.assertTrue('UNRECOGNIZABLE_VALUE' in search)  # invalid value for jou_pick

    def test_not_processed(self):
        """verify parameters that are not processed show up in message to user

        passes in parameters that are not currently translated
        """
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.args = MultiDict([('aut_syn', 'foo')])
        req.mimetype = None
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertTrue('unprocessed_parameter' in search)
        self.assertTrue(urllib.parse.quote('Synonym Replacement') in search)

        req.args = MultiDict([('aut_syn', 'foo'), ('aut_wt', 'bar')])
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertTrue('unprocessed_parameter' in search)
        self.assertTrue(urllib.parse.quote('Synonym Replacement') in search)
        self.assertTrue(urllib.parse.quote('Relative Weights') in search)

    def test_qsearch(self):
        """qsearch searches metadata

        used by unfielded form
        """
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('qsearch', 'bIbcOde=2005LRSP....2....4B')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibcode%3A%222005LRSP....2....4B%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', '2005LRSP....2....4B')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibcode%3A%222005LRSP....2....4B%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'title ads')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=title%3A%22ads%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'Author:accomazzi')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=author%3A%22accomazzi%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'Doi:10.5281/zenodo.10505 e')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=doi%3A%2210.5281%2Fzenodo.10505+e%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', '10.5281/zenodo.10505 e')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=doi%3A%2210.5281%2Fzenodo.10505+e%22&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'Year 2017-2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=year%3A2017-2019&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'year=2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=year%3A2019&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)

        req.args = MultiDict([('qsearch', 'accomazzi 2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=accomazzi+2019&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' + '/', search)


    def test_data_and(self):
        """test data_and"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)  # no value

        req.args = MultiDict([('data_and', 'NO'), ('article', 'YES'), ('gif_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=(' +
                         urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML")') + ' OR ' + urllib.parse.quote('esources:("ADS_SCAN")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('data_and', 'NO'), ('article', 'YES'), ('gif_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=(' +
                         urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML")') + ' OR ' + urllib.parse.quote('esources:("ADS_SCAN")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('data_and', 'YES'), ('article', 'YES'), ('gif_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=(' +
                         urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML")') + ' AND ' + urllib.parse.quote('esources:("ADS_SCAN")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('data_and', 'NOT'), ('article', 'YES'), ('gif_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=(NOT ' +
                         urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML")') + ' NOT ' + urllib.parse.quote('esources:("ADS_SCAN")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('data_and', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertTrue('error_message' in search)  # invalid value for data_and
        self.assertTrue('UNRECOGNIZABLE_VALUE' in search)  # invalid value for data_and

    def test_article_link(self):
        """test article_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('article_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +
                         urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML" OR "AUTHOR_PDF" OR "AUTHOR_HTML" OR "ADS_PDF" OR "ADS_SCAN")') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_gif_link(self):
        """test gif_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('gif_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('esources:("ADS_SCAN")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_article(self):
        """test article"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('article', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('esources:("PUB_PDF" OR "PUB_HTML")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_toc_link(self):
        """test toc_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('toc_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("TOC")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_ref_link(self):
        """test ref_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('ref_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('reference:*') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_citation_link(self):
        """test citation_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('citation_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('citation_count:[1 TO *]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_associated_link(self):
        """test associated_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('associated_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("ASSOCIATED")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_simb_obj(self):
        """test simb_obj"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('simb_obj', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('data:("simbad")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_ned_obj(self):
        """test ned_obj"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('ned_obj', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('data:("ned")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_pds_link(self):
        """test pds_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('pds_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('data:("PDS")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_aut_note(self):
        """test aut_note"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('aut_note', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("NOTE")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_ar_link(self):
        """test ar_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('ar_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('read_count:[1 TO *]') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_multimedia_link(self):
        """test multimedia_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('multimedia_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("PRESENTATION")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_spires_link(self):
        """test spires_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('spires_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("INSPIRE")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_abstract(self):
        """test abstract"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('data_and', 'YES'), ('abstract', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('abstract:*') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_lib_link(self):
        """test lib_link"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('lib_link', 'YES')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('property:("LIBRARYCATALOG")') + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_error_link(self):
        """test error in data group"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None
        req.args = MultiDict([('data_and', 'YES'), ('abstract', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'abstract' + '/', search)

    def test_group_and(self):
        """test group_and"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('group_and', 'ALL')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('group_and', 'NO'), ('group_sel', 'ARI'), ('group_sel', 'ESO/Lib'), ('group_sel', 'HST')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_bibgroup_facet_fq_bibgroup_facet=OR' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"ARI"' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"ESO/Lib"' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"HST"' +
                         '&q=*:*' + '&fq=' + urllib.parse.quote('{') + '!' + urllib.parse.quote('type=aqp v=$fq_bibgroup_facet}') +
                         '&fq_bibgroup_facet=(' + urllib.parse.quote_plus('bibgroup_facet:("ARI" OR "ESO/Lib" OR "HST")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('group_and', 'YES'), ('group_sel', 'ARI'), ('group_sel', 'ESO/Lib'), ('group_sel', 'HST')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_bibgroup_facet_fq_bibgroup_facet=AND' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"ARI"' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"ESO/Lib"' +
                         '&filter_bibgroup_facet_fq_bibgroup_facet=bibgroup_facet:"HST"' +
                         '&q=*:*' + '&fq=' + urllib.parse.quote('{') + '!' + urllib.parse.quote('type=aqp v=$fq_bibgroup_facet}') +
                         '&fq_bibgroup_facet=(' + urllib.parse.quote_plus('bibgroup_facet:("ARI" AND "ESO/Lib" AND "HST")') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('group_and', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'group_and' + '/', search)

        req.args = MultiDict([('group_and', 'YES'), ('group_sel', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'group_sel' + '/', search)

        req.args = MultiDict([('group_and', 'YES'), ('group_sel', '')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'group_sel' + '/', search)

    def test_sort(self):
        """test sort"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict()
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('sort', 'SCORE')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('score desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('sort', 'foo')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&format=SHORT' + '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'sort' + '/', search)

    def test_arxiv_sel(self):
        """test arxiv_sel"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('arxiv_sel', 'cs'), ('arxiv_sel', 'physics')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=keyword:(' + urllib.parse.quote('"computer science" OR "physics"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('arxiv_sel', '')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  \
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'arxiv_sel' + '/', search)

        req.args = MultiDict([('arxiv_sel', 'ADS')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  \
                         '&error_message=' + 'UNRECOGNIZABLE_VALUE' + '&unprocessed_parameter=' + 'arxiv_sel' + '/', search)

        req.args = MultiDict([('arxiv_sel', 'astro-ph'), ('arxiv_sel', 'cond-mat'), ('arxiv_sel', 'cs'), ('arxiv_sel', 'gr-qc'),
                              ('arxiv_sel', 'hep-ex'), ('arxiv_sel', 'hep-lat'), ('arxiv_sel', 'hep-ph'), ('arxiv_sel', 'hep-th'),
                              ('arxiv_sel', 'math'), ('arxiv_sel', 'math-ph'), ('arxiv_sel', 'nlin'), ('arxiv_sel', 'nucl-ex'),
                              ('arxiv_sel', 'nucl-th'), ('arxiv_sel', 'physics'), ('arxiv_sel', 'quant-ph'), ('arxiv_sel', 'q-bio')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=property:(' + urllib.parse.quote("EPRINT_OPENACCESS") + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        # 3/19/2019 remove the warning, as per Alberto.
        # req.args = MultiDict([('db_key', 'AST'), ('arxiv_sel', 'cs'), ('arxiv_sel', 'physics')])
        # req.args.update(self.append_defaults())
        # view = ClassicSearchRedirectView()
        # search = view.translate(req)
        # self.assertEqual('filter_database_fq_database=OR' +
        #                  '&filter_database_fq_database=database:"astronomy"' +
        #                  '&q=*:*&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
        #                  '&sort=' + urllib.parse.quote('date desc, bibcode desc') +
        #                  '&warning_message=' + urllib.parse.quote('when the astronomy or physics databases are selected, the arXiv selection is ignored') + '/',
        #                  search)  # astronomy only

    def test_ref_stems(self):
        """test ref_stems"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('ref_stems', 'ApJ, AJ, AAS')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibstem:(' + urllib.parse.quote('"ApJ"') + ' OR ' +  urllib.parse.quote('"AJ"') + ' OR ' +  urllib.parse.quote('"AAS"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('ref_stems', '-AAS')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=-bibstem:(' + urllib.parse.quote('"AAS"')  + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('ref_stems', '-AAS, -arXiv')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=-bibstem:(' + urllib.parse.quote('"AAS"') + ' OR ' +  urllib.parse.quote('"arXiv"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('ref_stems', 'arxiv, -AAS, EPJWC')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibstem:(' + urllib.parse.quote('"arxiv"') + ' OR ' +  urllib.parse.quote('"EPJWC"') + ') AND ' +
                         '-bibstem:(' + urllib.parse.quote('"AAS"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('ref_stems', 'A&A, GCN1, -CLic2, JPhy3, -JPhy4')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibstem:(' + urllib.parse.quote('"A&A"') + ' OR ' +  urllib.parse.quote('"GCN1"') + ' OR ' +  urllib.parse.quote('"JPhy3"') + ') AND ' +
                         '-bibstem:(' + urllib.parse.quote('"CLic2"') + ' OR ' +  urllib.parse.quote('"JPhy4"') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

        req.args = MultiDict([('ref_stems', 'A&A....33')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=bibstem:(' + urllib.parse.quote('"A&A....33"')  + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +  '/', search)

    def test_myads_query(self):
        """test query_type"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        # Daily arXiv query with db_key DAILY_PRE => OR
        req.args = MultiDict([('query_type', 'PAPERS'), ('db_key', 'DAILY_PRE'),
                              ('arxiv_sel', 'astro-ph'), ('start_year', '2019'),
                              ('start_entry_day', '15'), ('start_entry_mon', '10'), ('start_entry_year', '2019'),
                              ('end_entry_day', '16'), ('end_entry_mon', '10'), ('end_entry_year', '2019'),
                              ('title', '*+"nuclear star cluster"')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('bibstem:arxiv ((arxiv_class:astro-ph.*) OR (+"nuclear star cluster")) entdate:["2019-10-16:00:00" TO "2019-10-17"] pubdate:[2019-00 TO *]') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Daily arXiv query with db_key other than DAILY_PRE => no OR
        req.args = MultiDict([('query_type', 'PAPERS'), ('db_key', 'PRE'),
                              ('arxiv_sel', 'astro-ph'), ('start_year', '2019'),
                              ('start_entry_day', '15'), ('start_entry_mon', '10'), ('start_entry_year', '2019'),
                              ('end_entry_day', '16'), ('end_entry_mon', '10'), ('end_entry_year', '2019'),
                              ('title', '*+"nuclear star cluster"')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('bibstem:arxiv ((arxiv_class:astro-ph.*) (+"nuclear star cluster")) entdate:["2019-10-16:00:00" TO "2019-10-17"] pubdate:[2019-00 TO *]') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly citations query
        req.args = MultiDict([('query_type', 'CITES'), ('db_key', 'ALL'),
                              ('author', 'LOCKHART, KELLY')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('citations(author:"LOCKHART, KELLY")') +
                         '&sort=' + urllib.parse.quote('entry_date desc') +  '/', search)

        # Weekly authors query with db_key other than PRE => no prefix
        req.args = MultiDict([('query_type', 'PAPERS'), ('db_key', 'AST'),
                              ('author', 'LU, JESSICA\r\nHOSEK, MATTHEW\r\nKEWLEY, LISA\r\nACCOMAZZI, ALBERTO\r\nKURTZ, MICHAEL'),
                              ('start_entry_day', '26'), ('start_entry_mon', '9'), ('start_entry_year', '2019'),
                              ('end_entry_day', '18'), ('end_entry_mon', '10'), ('end_entry_year', '2019'),
                              ('start_year', '2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR&filter_database_fq_database=database:"astronomy"&'
                         'q=' + urllib.parse.quote('author:"LU, JESSICA" OR author:"HOSEK, MATTHEW" OR author:"KEWLEY, LISA" OR author:"ACCOMAZZI, ALBERTO" OR author:"KURTZ, MICHAEL" entdate:["2019-09-27:00:00" TO "2019-10-19"] pubdate:[2019-00 TO *]') +
                         '&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly authors query with db_key PRE => add arxiv
        req.args = MultiDict([('query_type', 'PAPERS'), ('db_key', 'PRE'), ('arxiv_sel', 'astro-ph'),
                              ('author', 'LU, JESSICA\r\nHOSEK, MATTHEW\r\nKEWLEY, LISA\r\nACCOMAZZI, ALBERTO\r\nKURTZ, MICHAEL'),
                              ('start_entry_day', '26'), ('start_entry_mon', '9'), ('start_entry_year', '2019'),
                              ('end_entry_day', '18'), ('end_entry_mon', '10'), ('end_entry_year', '2019'),
                              ('start_year', '2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q='  + urllib.parse.quote('bibstem:arxiv (arxiv_class:astro-ph.*) author:"LU, JESSICA" OR author:"HOSEK, MATTHEW" OR author:"KEWLEY, LISA" OR author:"ACCOMAZZI, ALBERTO" OR author:"KURTZ, MICHAEL" entdate:["2019-09-27:00:00" TO "2019-10-19"] pubdate:[2019-00 TO *]') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (recent papers) query
        req.args = MultiDict([('query_type', 'PAPERS'), ('db_key', 'AST'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU'),
                              ('start_entry_day', '26'), ('start_entry_mon', '9'), ('start_entry_year', '2019'),
                              ('end_entry_day', '18'), ('end_entry_mon', '10'), ('end_entry_year', '2019'),
                              ('start_year', '2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR&filter_database_fq_database=database:"astronomy"&'
                         'q=' + urllib.parse.quote('("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) entdate:["2019-09-27:00:00" TO "2019-10-19"] pubdate:[2019-00 TO *]') +
                         '&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('entry_date desc') +  '/', search)

        # Weekly keyword (popular papers) query
        req.args = MultiDict([('query_type', 'ALSOREADS'), ('db_key', 'AST'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR&filter_database_fq_database=database:"astronomy"&' +
                         'q=' + urllib.parse.quote('trending("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU)') +
                         '&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (most cited) query
        req.args = MultiDict([('query_type', 'REFS'), ('db_key', 'AST'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR&filter_database_fq_database=database:"astronomy"&' +
                         'q=' + urllib.parse.quote('useful("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU)') +
                         '&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly citations query with db_key PRE => add arxiv
        req.args = MultiDict([('query_type', 'CITES'), ('db_key', 'PRE'), ('arxiv_sel', 'astro-ph'),
                              ('author', 'LOCKHART, KELLY')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('citations((author:"LOCKHART, KELLY") bibstem:arxiv (arxiv_class:astro-ph.*))') +
                         '&sort=' + urllib.parse.quote('entry_date desc') +  '/', search)

        # Weekly keyword (popular papers) query with db_key PRE => add arxiv
        req.args = MultiDict([('query_type', 'ALSOREADS'), ('db_key', 'PRE'), ('arxiv_sel', 'astro-ph'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('trending(("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) bibstem:arxiv (arxiv_class:astro-ph.*))') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (most cited) query with db_key PRE => add arxiv
        req.args = MultiDict([('query_type', 'REFS'), ('db_key', 'PRE'), ('arxiv_sel', 'astro-ph'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('useful(("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) bibstem:arxiv (arxiv_class:astro-ph.*))') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (popular papers) query with db_key PRE => no arxiv classes specified
        req.args = MultiDict([('query_type', 'ALSOREADS'), ('db_key', 'PRE'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('trending(("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) bibstem:arxiv )') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (most cited) query with db_key PRE => no arxiv classes specified, so no arxiv
        req.args = MultiDict([('query_type', 'REFS'), ('db_key', 'PRE'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('useful(("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) bibstem:arxiv )') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly keyword (most cited) query with db_key PRE no arxiv class => add bibstem:arxiv only
        req.args = MultiDict([('query_type', 'REFS'), ('db_key', 'PRE'),
                              ('title', '"nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('useful(("nuclear star cluster" OR ADS OR "supermassive black holes" OR M31 OR "Andromeda Galaxy" OR OSIRIS OR IFU) bibstem:arxiv )') +
                         '&sort=' + urllib.parse.quote('score desc') + '/', search)

        # Weekly citations query with db_key2 AST
        req.args = MultiDict([('query_type', 'CITES'), ('db_key', 'ALL'), ('db_key2', 'AST'),
                              ('author', 'LOCKHART, KELLY')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('filter_database_fq_database=OR&filter_database_fq_database=database:"astronomy"&' +
                         'q=' + urllib.parse.quote('citations(author:"LOCKHART, KELLY")') +
                         '&fq=%7B!type%3Daqp%20v%3D%24fq_database%7D&fq_database=(database%3A%22astronomy%22)' +
                         '&sort=' + urllib.parse.quote('entry_date desc') +  '/', search)

        # Weekly citations query with db_key2 PRE
        req.args = MultiDict([('query_type', 'CITES'), ('db_key', 'ALL'), ('db_key2', 'PRE'),
                              ('author', 'LOCKHART, KELLY')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + urllib.parse.quote('citations((author:"LOCKHART, KELLY") bibstem:arxiv )') +
                         '&sort=' + urllib.parse.quote('entry_date desc') +  '/', search)

    def test_myads_query_error(self):
        """test query_type"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        # undefined query_type
        req.args = MultiDict([('query_type', 'error')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' +  '&error_message=UNRECOGNIZABLE_VALUE/', search)

        # missing params
        req.args = MultiDict([('query_type', 'ALSOREADS')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' +  '&error_message=MISSING_REQUIRED_PARAMETER/', search)

        # when both author and title is supplied to query_type == 'PAPER' and db_key == 'AST'
        req.args = MultiDict([('query_type', 'PAPER'),
                              ('author', 'LU, JESSICA\r\nHOSEK, MATTHEW\r\nKEWLEY, LISA\r\nACCOMAZZI, ALBERTO\r\nKURTZ, MICHAEL'),
                              ('title', '"nuclear star cluster" or ADS or "supermassive black holes" or M31 or "Andromeda Galaxy" or OSIRIS or IFU'),
                              ('start_year', '2019')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' +  '&error_message=UNRECOGNIZABLE_VALUE/', search)

    def test_translate_to_ignore(self):
        """ test translate_to_ignore"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('lpi_query', 'NO')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&unprocessed_parameter=lpi_query/', search)

    def test_translate_weights(self):
        """ test translate_weights"""
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('aut_syn', 'NO')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=*:*' + '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT' +
                         '&unprocessed_parameter=Synonym%20Replacement/', search)

    def test_translate_bibcode(self):
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('bibcode', '1977PhRvC..16..427G')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +  urllib.parse.quote('bibcode:') + '(' + urllib.parse.quote('1977PhRvC..16..427G') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('bibcode', '2???ivoa.spec* OR 2???ivoa.rept*')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' +  urllib.parse.quote('bibcode:') + '(' + urllib.parse.quote('2???ivoa.spec* OR 2???ivoa.rept*') + ')' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

    def test_translate_search_docs(self):
        req = Request('get', 'http://test.test?')
        req.prepare()
        req.mimetype = None

        req.args = MultiDict([('bibstem', 'Ap&SS')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'bibstem:(' + urllib.parse.quote('"Ap&SS"') + ')'
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('bibstem', 'ApJ,AJ')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'bibstem:(' + urllib.parse.quote('"ApJ"') + ' OR ' + urllib.parse.quote('"AJ"')  + ')'
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('year', '2019-2020')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'year:[2019 TO 2020]' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('year', '2020')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'year:2020' +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') +  '&format=SHORT/', search)

        req.args = MultiDict([('volume', '12')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'volume:' + urllib.parse.quote('"12"') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('page', '211')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'page:' + urllib.parse.quote('"211"') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

        req.args = MultiDict([('bibstem', 'Ap&SS'), ('year', '1987'), ('page', '211')])
        req.args.update(self.append_defaults())
        view = ClassicSearchRedirectView()
        search = view.translate(req)
        self.assertEqual('q=' + 'bibstem:(' + urllib.parse.quote('"Ap&SS"') + ')' + urllib.parse.quote(' AND ') + 'year:1987' + urllib.parse.quote(' AND ') + 'page:' + urllib.parse.quote('"211"') +
                         '&sort=' + urllib.parse.quote('date desc, bibcode desc') + '&format=SHORT/', search)

if __name__ == '__main__':
    unittest.main(verbosity=2)
