"""
classic_search -- translate ADS Classic search parameters into a SciX search.

A port of tugboat's ClassicSearchRedirectView
(https://github.com/adsabs/tugboat, tugboat/views.py), so that
abs_connect / basic_connect requests go straight to the SciX search page
instead of going through /tugboat/classicSearchRedirect.

    translate(args) -> Translation
    search_url(base, args) -> (url, messages)

`args` maps classic parameter names to lists of values (unicode strings).
The translation rules are kept as close to tugboat as possible; the
differences are:

* tugboat built a Bumblebee-style path (/search/q=...&sort=.../), which SciX
  turns into /search?q=...; we build the final query string directly;
* the error_message / warning_message / unprocessed_parameter notes are not
  shown by SciX, so they are returned separately (and logged by the handler)
  instead of being appended to the URL;
* adsparser.parse_classic_keywords (myADS title queries) is not used: in
  tugboat it always failed under Python 3 (`.decode` on a str) and fell back
  to classic_field_to_string; we use that too, but wrap the result in the
  parentheses adsparser would have added, which fixes queries such as
  trending"a" OR b (see translate_title_for_myads);
* python-dateutil's relativedelta is replaced by a small standard-library
  helper.

Standard library only.
"""

import calendar
import re
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timedelta

quote = urllib.parse.quote
quote_plus = urllib.parse.quote_plus

# classic parameters tugboat accepts; anything else is dropped (as webargs did)
CLASSIC_PARAMS = {
    'article_sel', 'aut_logic', 'aut_xct', 'author', 'data_link', 'db_key',
    'end_entry_day', 'end_entry_mon', 'end_entry_year', 'end_mon', 'end_year',
    'jou_pick', 'obj_logic', 'object', 'open_link', 'preprint_link', 'qsearch',
    'return_req', 'start_entry_day', 'start_entry_mon', 'start_entry_year',
    'start_mon', 'start_year', 'text', 'txt_logic', 'title', 'ttl_logic',
    'nr_to_return', 'start_nr',
    'article_link', 'gif_link', 'article', 'simb_obj', 'ned_obj', 'data_and',
    'toc_link', 'pds_link', 'multimedia_link', 'ref_link', 'citation_link',
    'associated_link', 'lib_link', 'ar_link', 'aut_note', 'spires_link',
    'group_and', 'group_sel', 'abstract', 'sort',
    'aut_wt', 'obj_wt', 'ttl_wt', 'txt_wt', 'aut_wgt', 'obj_wgt', 'ttl_wgt', 'txt_wgt',
    'aut_syn', 'ttl_syn', 'txt_syn', 'aut_sco', 'ttl_sco', 'txt_sco',
    'aut_req', 'obj_req', 'ttl_req', 'txt_req', 'ref_stems', 'arxiv_sel',
    'sim_query', 'ned_query', 'mail_link', 'gpndb_obj', 'min_score', 'lpi_query',
    'iau_query', 'data_type', 'adsobj_query',
    'kwd_wt', 'full_wt', 'aff_wt', 'full_syn', 'aff_syn', 'kwd_wgt', 'full_wgt',
    'aff_wgt', 'kwd_sco', 'full_sco', 'aff_sco', 'kwd_req', 'full_req', 'aff_req',
    'kwd_logic', 'full_logic', 'aff_logic',
    'query_type', 'qform', 'bibcode', 'db_key2',
    'bibstem', 'year', 'volume', 'page',
}

# parameters whose repeated values are joined with ',' (all others: first value)
MULTI_VALUED = {'group_sel', 'db_key', 'arxiv_sel'}


def classic_args(multi):
    """{name: [values]} -> the args dict tugboat's parser produced"""
    args = {}
    for k, values in multi.items():
        if k in CLASSIC_PARAMS and values:
            args[k] = ','.join(values) if k in MULTI_VALUED else values[0]
    return args


def now():
    return datetime.now()


def shift_back(dt, years=0, months=0, days=0):
    """dt - relativedelta(years=..., months=..., days=...)"""
    total = dt.year * 12 + (dt.month - 1) - (years * 12 + months)
    y, m = divmod(total, 12)
    m += 1
    dt = dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y, m)[1]))
    return dt - timedelta(days=days)


class Translation:
    """translation components (tugboat's TranslationValue)"""

    def __init__(self):
        self.search = []
        self.filter = []
        self.error_message = []
        self.warning_message = []
        self.unprocessed_fields = []
        self.sort = ''
        self.facet = []
        self.params = ''
        self.query = ''        # the assembled solr query string
        self.leftover = []     # parameters nothing translated
        self.myads = False     # translated as a myADS query

    def messages(self):
        out = [f"error: {m}" for m in self.error_message]
        out += [f"warning: {urllib.parse.unquote(m)}" for m in self.warning_message]
        out += [f"unprocessed: {urllib.parse.unquote(m)}" for m in self.unprocessed_fields]
        if self.leftover:
            out.append("parameters not processed: " + " ".join(self.leftover))
        return out


class Translator:
    """tugboat ClassicSearchRedirectView, minus the web framework"""

    def __init__(self):
        self.translation = Translation()

    # -- entry point --------------------------------------------------------

    def translate(self, args):
        args = dict(args)
        if args.get('query_type', None):
            return self.translate_myads_queries(args)

        funcs = [self.translate_authors,
                 self.translate_pubdate, self.translate_entry_date,
                 self.translate_results_subset, self.translate_return_req,
                 self.translate_article_sel, self.translate_database,
                 self.translate_jou_pick, self.translate_group_sel,
                 self.translate_sort, self.translate_to_ignore,
                 self.translate_weights, self.translate_arxiv_sel,
                 self.translate_ref_stems, self.translate_search_docs]
        for f in funcs:
            f(args)

        self.translate_simple(args, 'object', 'object')
        self.translate_simple(args, 'title', 'title')
        self.translate_simple(args, 'text', 'abs')
        self.translate_simple(args, 'bibcode', 'bibcode')

        # a filter in classic, but not in solr
        self.translate_data_entries(args)

        # last: the unfielded form, so that the other parameters are still in args
        self.translate_qsearch(args)

        t = self.translation
        t.query = self.assemble(with_params=True)
        t.leftover = list(args.keys())
        return t

    def assemble(self, with_params):
        t = self.translation
        if len(t.search) == 0:
            t.search = ['*:*']
        q = ''.join(t.facet) + '&' if len(t.facet) > 0 else ''
        q += 'q=' + ' '.join(t.search)
        if len(t.filter) > 0:
            q += '&fq=' + '&fq='.join(t.filter)
        if len(t.sort) > 0:
            q += '&sort=' + t.sort
        if with_params and len(t.params) > 0:
            q += t.params
        return q

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def author_exact(args):
        value = args.pop('aut_xct', None)
        return bool(value) and str(value).upper() == 'YES'

    @staticmethod
    def get_logic(classic_param, args):
        classic_param_to_logic = {'author': 'aut_logic', 'title': 'ttl_logic',
                                  'text': 'txt_logic', 'object': 'obj_logic',
                                  'bibcode': ''}
        if classic_param in args:
            value = args.pop(classic_param_to_logic[classic_param], None)
            if value:
                value = value.upper()
            return value
        return ''

    @staticmethod
    def supplied(value):
        if value is None or (isinstance(value, str) and (len(value) == 0 or not value.isdigit())):
            return False
        return True

    def translate_title_for_myads(self, value):
        """myADS keywords, as one parenthesized group: (+"nuclear star cluster")

        tugboat tried adsparser.parse_classic_keywords first, which always
        failed under Python 3 (it called .decode on a str), and fell back to
        the plain tokenizer without parentheses, which produced broken queries
        such as trending"nuclear star cluster" OR ADS. We use the plain
        tokenizer and add the parentheses adsparser added."""
        value = self.classic_field_to_string(value)[0].lstrip('*')
        return f"({value})" if value else value

    @staticmethod
    def get_db_key_myads_queries(args):
        db_key = args.get('db_key', None)
        if db_key is None or db_key == 'ALL':
            db_key2 = args.get('db_key2', None)
            if db_key2:
                return db_key2
        return db_key

    def arxiv_class_addition_myads_queries(self, args):
        arxiv_sel = args.pop('arxiv_sel', None)
        if arxiv_sel and self.validate_arxiv_sel(arxiv_sel):
            return '(' + ' OR '.join(['arxiv_class:' + c + '.*' for c in arxiv_sel.split(',')]) + ')'
        return ''

    # -- myADS ----------------------------------------------------------------

    def translate_myads_queries(self, args):
        """the six myADS query types"""
        t = self.translation
        t.myads = True
        query_type = args.pop('query_type', None)

        if query_type == 'PAPERS':
            authors_str = args.pop('author', None)
            title_str = args.pop('title', None)
            db_key = self.get_db_key_myads_queries(args)
            arxiv_class = self.arxiv_class_addition_myads_queries(args)

            query = None
            if authors_str and not title_str:
                # weekly authors query (#3)
                author_query = ' OR '.join(['author:' + x for x in self.classic_field_to_array(authors_str)])
                arxiv_addition = 'bibstem:arxiv %s ' % arxiv_class if db_key == 'PRE' else ''
                query = f'{arxiv_addition}{author_query}'
                t.sort = quote('score desc')
            elif title_str and not authors_str:
                if (db_key == 'DAILY_PRE' or db_key == 'PRE') and arxiv_class:
                    # daily arXiv query (#1)
                    title = self.translate_title_for_myads(title_str)
                    add_or = ' OR ' if db_key == 'DAILY_PRE' else ' '
                    query = f'bibstem:arxiv ({arxiv_class}{add_or}{title})'
                    t.sort = quote('score desc')
                elif db_key == 'AST' or db_key == 'PHY':
                    # weekly keyword (recent papers) query (#4)
                    query = self.translate_title_for_myads(title_str)
                    t.sort = quote('entry_date desc')
                else:
                    t.error_message.append('MISSING_REQUIRED_PARAMETER')
            elif authors_str and title_str:
                t.error_message.append('UNRECOGNIZABLE_VALUE')

            if query:
                entry_date = self.translate_entry_date(args, append=False)
                start_year = args.pop('start_year', None)
                if entry_date:
                    query = f'{query} {entry_date}'
                if start_year:
                    query = f'{query} pubdate:[{start_year}-00 TO *]'
                t.search.append(quote(query))
        else:
            param = None
            if query_type == 'CITES':
                # weekly citations query (#2)
                func_type = 'citations'
                authors_str = args.pop('author', None)
                if authors_str:
                    param = '(author:%s)' % ' '.join(self.classic_field_to_array(authors_str))
                sort_type = 'entry_date desc'
            elif query_type == 'ALSOREADS':
                # weekly keyword (popular papers) query (#5)
                func_type = 'trending'
                title_str = args.pop('title', None)
                if title_str:
                    param = self.translate_title_for_myads(title_str)
                sort_type = 'score desc'
            elif query_type == 'REFS':
                # weekly keyword (most cited) query (#6)
                func_type = 'useful'
                title_str = args.pop('title', None)
                if title_str:
                    param = self.translate_title_for_myads(title_str)
                sort_type = 'score desc'
            else:
                func_type = None

            if func_type and param:
                db_key = self.get_db_key_myads_queries(args)
                arxiv_class = self.arxiv_class_addition_myads_queries(args)
                arxiv_addition = 'bibstem:arxiv %s' % arxiv_class if db_key == 'PRE' else None
                query = (f'{func_type}{param}' if arxiv_addition is None
                         else f'{func_type}({param} {arxiv_addition})')
                t.search.append(quote(query))
                t.sort = quote(sort_type)
            elif not func_type:
                t.error_message.append('UNRECOGNIZABLE_VALUE')
            elif not param:
                t.error_message.append('MISSING_REQUIRED_PARAMETER')

        self.translate_database(args)
        self.translate_database_secondary(args)

        t.query = self.assemble(with_params=False)
        return t

    # -- authors, title, abstract, object ---------------------------------

    def translate_authors(self, args):
        connector = ' AND '
        search = ''
        logic = self.get_logic('author', args)
        exact = self.author_exact(args)
        if logic == 'OR':
            connector = ' OR '
        author_field = '=author:' if exact else 'author:'
        authors_str = args.pop('author', None)
        if authors_str:
            authors = self.classic_field_to_array(authors_str)
            single_author = ' '.join(authors).replace('"', '')
            if re.match(r'\^', single_author):
                # single author search: ^last, first$
                match = re.findall(r'\^([^$]*)\$', single_author)
                if match:
                    self.translation.search.append('(author:"' + match[0] + '" and author_count:1)')
                else:
                    # first author search: ^last, first
                    match = re.findall(r'\^([A-Za-z]+,\s+[A-Za-z]+)', single_author)
                    if match:
                        self.translation.search.append('author:"' + match[0] + '"')
                    else:
                        # first author search without first initials
                        match = re.findall(r'\^([A-Za-z\s]+)', single_author)
                        if match:
                            self.translation.search.append('author:"' + match[0] + ',"')
            else:
                search += quote(author_field) + '('
                for author in authors:
                    search += quote(author + connector)
                search = search[:-len(quote(connector))]
                search += ')'
                if len(self.translation.search) > 0:
                    self.translation.search.append('AND')
                self.translation.search.append(search)

    def translate_simple(self, args, classic_param, bbb_param):
        """title, abstract, object, bibcode: rename and apply the connector"""
        connector = ' AND '
        search = ''
        logic = self.get_logic(classic_param, args)
        if logic == 'OR':
            connector = ' OR '
        classic_str = args.pop(classic_param, None)
        if classic_str:
            # only object allows multiple tokens joined by the connector
            if classic_param == 'object':
                terms = self.classic_field_to_array(classic_str)
            else:
                terms = self.classic_field_to_string(classic_str)
            search += quote(bbb_param + ':') + '('
            for term in terms:
                search += quote(term + connector)
            search = search[:-len(quote(connector))]
            search += ')'
            if len(self.translation.search) > 0:
                self.translation.search.append('AND')
            self.translation.search.append(search)

    # -- dates ----------------------------------------------------------------

    @staticmethod
    def convert_year_short_to_long(year):
        """2-digit year -> 4-digit year"""
        if year == 0 or year == 2222:   # markers for min/max year
            return year
        if year > 100:
            return year
        n = now().year
        diff_year = n - (n % 100)
        return year + diff_year if year + diff_year <= n + 1 else year + diff_year - 100

    def translate_pubdate(self, args):
        """pubdate:[1990-01 TO 1990-02]"""
        start_year = args.pop('start_year', None)
        end_year = args.pop('end_year', None)
        start_month = args.pop('start_mon', None)
        end_month = args.pop('end_mon', None)

        if self.supplied(start_year) is False and self.supplied(end_year) is False:
            return

        if not self.supplied(start_year):
            start_year = 0
        if not self.supplied(start_month):
            start_month = 1

        if not self.supplied(end_year):
            end_year = 2222
            if not self.supplied(end_month):
                end_month = now().month
        else:
            if not self.supplied(end_month):
                end_month = 12

        start_year = self.convert_year_short_to_long(int(start_year))
        start_month = int(start_month)
        end_year = self.convert_year_short_to_long(int(end_year))
        end_month = int(end_month)
        if start_year == 0:
            search = 'pubdate' + quote(':[* TO {:04d}-{:02}]'.format(end_year, end_month))
        elif end_year == 2222:
            search = 'pubdate' + quote(':[{:04d}-{:02d} TO *]'.format(start_year, start_month))
        else:
            search = 'pubdate' + quote(':[{:04d}-{:02d} TO {:04d}-{:02}]'.format(
                start_year, start_month, end_year, end_month))
        if len(self.translation.search) > 0:
            self.translation.search.append('AND')
        self.translation.search.append(search)

    def _entry_date_parts(self, args, prefix):
        year = args.pop(f'{prefix}_entry_year', None)
        year = self.convert_year_short_to_long(int(year)) if self.supplied(year) else 0
        month = args.pop(f'{prefix}_entry_mon', None)
        month = int(month) if self.supplied(month) else 0
        day = args.pop(f'{prefix}_entry_day', None)
        day = int(day) if self.supplied(day) else 0
        return year, month, day

    def translate_entry_date_start(self, args):
        try:
            start_year, start_month, start_day = self._entry_date_parts(args, 'start')
            date = sum(d > 0 for d in [start_year, start_month, start_day])
            offset = sum(d < 0 for d in [start_year, start_month, start_day])
            if date > 0 and offset > 0:
                self.translation.error_message.append('ENTRY_DATE_OFFSET_ERROR')
                return None
            if offset > 0:
                return shift_back(now(), -start_year, -start_month, -start_day).strftime("%Y-%m-%d")
            if date >= 0:
                start_year = start_year if start_year != 0 else 1
                start_month = start_month if start_month != 0 else 1
                start_day = start_day if start_day != 0 else 1
                if start_year != 1:
                    # add one day to the translated entry_date
                    next_day = datetime(start_year, start_month, start_day) + timedelta(days=1)
                    return next_day.strftime('%Y-%m-%d')
                return '{:04d}-{:02d}-{:02d}'.format(start_year, start_month, start_day)
        except Exception:
            self.translation.error_message.append('ENTRY_DATE_NON_NUMERIC_ERROR')
            return None

    def translate_entry_date_end(self, args):
        try:
            end_year, end_month, end_day = self._entry_date_parts(args, 'end')
            date = sum(d > 0 for d in [end_year, end_month, end_day])
            offset = sum(d < 0 for d in [end_year, end_month, end_day])
            if date > 0 and offset > 0:
                self.translation.error_message.append('ENTRY_DATE_OFFSET_ERROR')
                return None
            if offset > 0:
                return shift_back(now(), -end_year, -end_month, -end_day).strftime("%Y-%m-%d")
            if date == 0:
                return now().strftime("%Y-%m-%d")
            if date > 0:
                n = now()
                end_year = end_year if end_year != 0 else n.year
                end_month = end_month if end_month != 0 else (n.month if end_year == n.year else 12)
                end_day = end_day if end_day != 0 else \
                    (n.day if end_year == n.year else calendar.monthrange(end_year, end_month)[1])
                next_day = datetime(end_year, end_month, end_day) + timedelta(days=1)
                return next_day.strftime('%Y-%m-%d')
        except Exception:
            self.translation.error_message.append('ENTRY_DATE_NON_NUMERIC_ERROR')
            return None

    def translate_entry_date(self, args, append=True):
        """entdate:["<start>:00:00" TO "<end>"]"""
        fields = ['start_entry_day', 'start_entry_mon', 'start_entry_year',
                  'end_entry_day', 'end_entry_mon', 'end_entry_year']
        if sum([1 for f in fields if f in args]) == 0:
            return
        add = sum([1 for f in fields if len(args.get(f, '')) > 0]) > 0

        start_date = self.translate_entry_date_start(args)
        end_date = self.translate_entry_date_end(args)
        if start_date is not None and end_date is not None and add:
            if append:
                search = 'entdate' + quote(':["{}:00:00" TO "{}"]'.format(start_date, end_date))
                if len(self.translation.search) > 0:
                    self.translation.search.append('AND')
                self.translation.search.append(search)
            else:
                return 'entdate:["{}:00:00" TO "{}"]'.format(start_date, end_date)

    # -- database, refereed, groups, doctype --------------------------------

    @staticmethod
    def validate_db_key(db_key):
        valid_db_key = ['AST', 'PHY', 'PRE', 'DAILY_PRE', 'ALL']
        if len(db_key) == 0:
            return False
        return all(e in valid_db_key for e in db_key.split(','))

    def translate_database_validate(self, value):
        dict_db = {'AST': 'astronomy', 'PHY': 'physics', 'PRE': 'e-prints',
                   'DAILY_PRE': 'e-prints', 'ALL': ''}
        t = self.translation
        if self.validate_db_key(value):
            db_key = ''
            if len(t.facet) > 0:
                t.facet.append('&')
            for e in value.split(','):
                if e != 'PRE' and e != 'DAILY_PRE' and e != 'ALL':
                    if len(db_key) > 0:
                        db_key += ' OR '
                    if len(t.facet) == 0:
                        t.facet.append('filter_database_fq_database=OR')
                    db_key += 'database:"' + dict_db[e] + '"'
                    t.facet.append('&filter_database_fq_database=' + 'database:"' + dict_db[e] + '"')
            if len(db_key) > 0:
                t.filter.append(quote('{') + '!' + quote('type=aqp v=$fq_database}') +
                                '&fq_database=(' + quote(db_key) + ')')
        else:
            t.error_message.append('UNRECOGNIZABLE_VALUE')
            t.unprocessed_fields.append('db_key')

    def translate_database(self, args):
        value = args.pop('db_key', None)
        if value is not None:
            self.translate_database_validate(value)

    def translate_database_secondary(self, args):
        value = args.pop('db_key2', None)
        if value is not None:
            self.translate_database_validate(value)

    def translate_results_subset(self, args):
        """pagination is not passed on"""
        args.pop('nr_to_return', None)
        args.pop('start_nr', None)

    def _property_filter(self, value):
        t = self.translation
        if len(t.facet) > 0:
            t.facet.append('&')
        t.facet.append('filter_property_fq_property=AND')
        t.facet.append(f'&filter_property_fq_property=property:"{value}"')
        t.filter.append(quote('{') + '!' + quote('type=aqp v=$fq_property}') +
                        '&fq_property=(' + quote(f'property:("{value}")') + ')')

    def translate_jou_pick(self, args):
        """refereed / non-refereed"""
        jou_pick = args.pop('jou_pick', None)
        if jou_pick is None or jou_pick == 'ALL':
            pass
        elif jou_pick == 'NO':
            self._property_filter('refereed')
        elif jou_pick == 'EXCL':
            self._property_filter('not refereed')
        else:
            self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
            self.translation.unprocessed_fields.append('jou_pick')

    def translate_data_entries(self, args):
        dict_entries = {'data_link': 'esources:*',
                        'article_link': 'esources:("PUB_PDF" OR "PUB_HTML" OR "AUTHOR_PDF" OR "AUTHOR_HTML" OR "ADS_PDF" OR "ADS_SCAN")',
                        'article': 'esources:("PUB_PDF" OR "PUB_HTML")',
                        'gif_link': 'esources:("ADS_SCAN")',
                        'preprint_link': 'esources:("EPRINT_HTML")',
                        'toc_link': 'property:("TOC")',
                        'ref_link': 'reference:*',
                        'citation_link': 'citation_count:[1 TO *]',
                        'associated_link': 'property:("ASSOCIATED")',
                        'simb_obj': 'data:("simbad")',
                        'ned_obj': 'data:("ned")',
                        'pds_link': 'data:("PDS")',
                        'aut_note': 'property:("NOTE")',
                        'lib_link': 'property:("LIBRARYCATALOG")',
                        'ar_link': 'read_count:[1 TO *]',
                        'multimedia_link': 'property:("PRESENTATION")',
                        'spires_link': 'property:("INSPIRE")',
                        'abstract': 'abstract:*',
                        'open_link': 'property:("OPENACCESS")'}
        search = []
        operator = self.translate_data_and(args)
        if operator is not None:
            for classic, bbb in dict_entries.items():
                value = args.pop(classic, None)
                if value is None:
                    pass
                elif value == 'YES':
                    if (operator == 'NOT') or len(search) > 0:
                        search.append(operator)
                    search.append(quote(bbb))
                else:
                    self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
                    self.translation.unprocessed_fields.append(classic)
        if len(search) == 1:
            self.translation.search.append(''.join(search))
        elif len(search) > 1:
            self.translation.search.append('(' + ' '.join(search) + ')')

    def translate_data_and(self, args):
        data_and = args.pop('data_and', None)
        operators = {'NO': 'OR', 'YES': 'AND', 'NOT': 'NOT'}
        if data_and is None or data_and == 'ALL':
            return None
        if data_and in operators:
            return operators[data_and]
        self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
        self.translation.unprocessed_fields.append('data_and')
        return None

    @staticmethod
    def validate_group_sel(group_sel):
        valid_group_sel = ['ARI', 'CfA', 'CFHT', 'Chandra', 'ESO/Lib', 'ESO/Telescopes', 'Gemini', 'Herschel', 'HST',
                           'ISO', 'IUE', 'JCMT', 'Keck', 'Leiden', 'LPI', 'Magellan', 'NOAO', 'NRAO', 'NRAO/Telescopes',
                           'ROSAT', 'SDO', 'SMA', 'Spitzer', 'Subaru', 'Swift', 'UKIRT', 'USNO', 'VSGC', 'XMM']
        if len(group_sel) == 0:
            return False
        return all(e in valid_group_sel for e in group_sel.split(','))

    def translate_group_sel(self, args):
        t = self.translation
        operator = self.translate_group_and(args)
        if operator is not None:
            value = args.pop('group_sel', None)
            if value is None:
                return
            if self.validate_group_sel(value):
                if len(t.facet) > 0:
                    t.facet.append('&')
                t.facet.append('filter_bibgroup_facet_fq_bibgroup_facet=' + operator)
                group_sel = ''
                for e in value.split(','):
                    if (operator == 'NOT') or len(group_sel) > 0:
                        group_sel += ' ' + operator + ' '
                    group_sel += '"' + e + '"'
                    t.facet.append('&filter_bibgroup_facet_fq_bibgroup_facet=' + 'bibgroup_facet:"' + e + '"')
                if len(group_sel) > 0:
                    t.filter.append(quote('{') + '!' + quote('type=aqp v=$fq_bibgroup_facet}') +
                                    '&fq_bibgroup_facet=(' + quote_plus('bibgroup_facet:({})'.format(group_sel)) + ')')
            else:
                t.error_message.append('UNRECOGNIZABLE_VALUE')
                t.unprocessed_fields.append('group_sel')

    def translate_group_and(self, args):
        group_and = args.pop('group_and', None)
        operators = {'NO': 'OR', 'YES': 'AND'}
        if group_and is None or group_and == 'ALL':
            return None
        if group_and in operators:
            return operators[group_and]
        self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
        self.translation.unprocessed_fields.append('group_and')
        return None

    def translate_return_req(self, args):
        return_req = args.pop('return_req', None)
        if return_req not in (None, 'result', 'no_params'):
            self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
            self.translation.unprocessed_fields.append('return_req')

    def translate_article_sel(self, args):
        t = self.translation
        article_sel = args.pop('article_sel', None)
        if article_sel is None:
            pass
        elif article_sel == 'YES':
            if len(t.facet) > 0:
                t.facet.append('&')
            t.facet.append('filter_doctype_facet_hier_fq_doctype=AND')
            t.facet.append('&filter_doctype_facet_hier_fq_doctype=' + quote_plus('doctype_facet_hier:"0/Article"'))
            t.filter.append(quote('{') + '!' + quote('type=aqp v=$fq_doctype}') +
                            '&fq_doctype=(' + quote_plus('doctype_facet_hier:"0/Article"') + ')')
        else:
            t.error_message.append('UNRECOGNIZABLE_VALUE')
            t.unprocessed_fields.append('article_sel')

    # -- unfielded search ---------------------------------------------------

    REGEX_UNFIELDED_MATCH = OrderedDict([
        (re.compile(r"^(bibcode)?.*([12][089]\d\d[A-Z\.0-9&]{15})$", re.IGNORECASE), r'bibcode:"%s"'),
        (re.compile(r"^(:?bibcode=)(([12][089?][\d?][\d?][A-Z\.&*0-9\s]+[OoAa]?[RrNn]?[Dd]?)+)$", re.IGNORECASE), r'bibcode:"%s"'),
        (re.compile(r"^title[=\s:]+(.*)$", re.IGNORECASE), r'title:"%s"'),
        (re.compile(r"^author[s]*[=\s:]+(.*)$", re.IGNORECASE), r'author:"%s"'),
        (re.compile(r"^[doi]?.*(10\..*)$", re.IGNORECASE), r'doi:"%s"'),
        (re.compile(r"^year.*([12][089]\d\d-[12][089]\d\d)$", re.IGNORECASE), r'year:%s'),
        (re.compile(r"^year.*([12][089]\d\d)$", re.IGNORECASE), r'year:%s'),
        (re.compile(r"^([12][089]\d\d)$", re.IGNORECASE), r'year:%s'),
        (re.compile(r"^(.*)$", re.IGNORECASE), r'%s'),
    ])

    def translate_qsearch(self, args):
        """qsearch: the single-field form (bibcode, title, author, DOI, year, or free text)"""
        value = args.pop('qsearch', None)
        if value:
            qsearch = ''
            for i, key in enumerate(self.REGEX_UNFIELDED_MATCH):
                match = key.search(value)
                if match:
                    qsearch = self.REGEX_UNFIELDED_MATCH[key] % (match.group(1 if i > 1 else 2))
                    break
            if len(qsearch) > 0:
                self.translation.search.append(quote_plus(qsearch))

    # -- sort, ignored and weight parameters --------------------------------

    def translate_sort(self, args):
        dict_sort = {'SCORE': 'score desc',
                     'AUTHOR': 'first_author desc',
                     'NDATE': 'date desc',
                     'ODATE': 'date asc',
                     'BIBCODE': 'bibcode desc',
                     'RBIBCODE': 'bibcode asc',
                     'ENTRY': 'entry_date desc',
                     'CITATIONS': 'citation_count desc',
                     'AUTHOR_CNT': 'author_count desc',
                     'SBIBCODE': 'bibcode desc',
                     'READS': 'read_count desc',
                     'AR_SCORE': 'read_count desc',
                     'NORMCITATIONS': 'citation_count_norm desc',
                     'NORMSCORE': '',
                     'NONE': '',
                     'PAGE': 'bibcode asc',
                     'RPAGE': 'bibcode desc'}
        value = args.pop('sort', None)
        if value is None:
            self.translation.sort = quote('date desc, bibcode desc')
        elif value in dict_sort:
            self.translation.sort = quote(dict_sort[value])
        else:
            self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
            self.translation.unprocessed_fields.append('sort')

    def translate_to_ignore(self, args):
        """drop the parameters that are ignored, noting the ones that mattered"""
        ignored = ['sim_query', 'ned_query', 'min_score', 'mail_link', 'data_type',
                   'lpi_query', 'iau_query', 'gpndb_obj', 'adsobj_query',
                   'aff_logic', 'aff_req', 'aff_sco', 'aff_syn', 'aff_wgt', 'aff_wt',
                   'kwd_logic', 'kwd_req', 'kwd_sco', 'kwd_wgt', 'kwd_wt',
                   'full_logic', 'full_req', 'full_sco', 'full_syn', 'full_wgt', 'full_wt',
                   'qform']
        for key in ignored:
            set_key = args.pop(key, None)
            if key == 'sim_query' or key == 'ned_query':
                if set_key is not None:
                    continue
                # no message if no object search was entered
                # (called before the object is translated, so it is still in args)
                if 'object' in args and len(args['object']) == 0:
                    continue
            if key == 'min_score' and set_key == '':
                continue
            if key == 'mail_link' and set_key is None:
                continue
            if key == 'data_type' and set_key == 'SHORT':
                self.translation.params += '&format=' + set_key
                continue
            if set_key is None:
                continue
            if key not in self.translation.unprocessed_fields:
                self.translation.unprocessed_fields.append(key)

    def translate_weights(self, args):
        """weights must be the defaults; otherwise note that they were ignored"""
        dict_weights_default = {'aut_syn': 'YES', 'ttl_syn': 'YES', 'txt_syn': 'YES',
                                'aut_wt': '1.0', 'obj_wt': '1.0', 'ttl_wt': '0.3', 'txt_wt': '3.0',
                                'aut_wgt': 'YES', 'obj_wgt': 'YES', 'ttl_wgt': 'YES', 'txt_wgt': 'YES',
                                'ttl_sco': 'YES', 'txt_sco': 'YES', 'aut_sco': 'NO',
                                'aut_req': 'NO', 'obj_req': 'NO', 'ttl_req': 'NO', 'txt_req': 'NO'}
        dict_weights_of_type = {'syn': 'Synonym Replacement', 'wt': 'Relative Weights',
                                'wgt': 'Use For Weighting', 'sco': 'Weighted Scoring',
                                'req': 'Require Field for Selection'}
        one_weight_present = False
        not_default = []
        for key, value in dict_weights_default.items():
            if key in args:
                one_weight_present = True
                if args.pop(key, None) != value:
                    kind = dict_weights_of_type[key.split('_')[1]]
                    if kind not in not_default:
                        not_default.append(kind)
            elif value != 'NO':
                kind = dict_weights_of_type[key.split('_')[1]]
                if kind not in not_default:
                    not_default.append(kind)
        if len(not_default) > 0 and one_weight_present:
            if args.get('qsearch', None) is not None:
                self.translation.unprocessed_fields.append(quote('One or more weighted parameter(s)'))
            else:
                for err in not_default:
                    self.translation.unprocessed_fields.append(quote(err))

    # -- arXiv classes, bibstems, journal/volume/page -----------------------

    DICT_ARXIV = {'astro-ph': 'Astrophysics',
                  'cond-mat': 'Condensed Matter',
                  'cs': 'Computer Science',
                  'gr-qc': 'General Relativity and Quantum Cosmology',
                  'hep-ex': 'High Energy Physics - Experiment',
                  'hep-lat': 'High Energy Physics - Lattice',
                  'hep-ph': 'High Energy Physics - Phenomenology',
                  'hep-th': 'High Energy Physics - Theory',
                  'math': 'Mathematics',
                  'math-ph': 'Mathematical Physics',
                  'nlin': 'Nonlinear Sciences',
                  'nucl-ex': 'Nuclear Experiment',
                  'nucl-th': 'Nuclear Theory',
                  'physics': 'Physics',
                  'quant-ph': 'Quantum Physics',
                  'q-bio': 'Quantitative Biology'}

    def validate_arxiv_sel(self, arxiv_sel):
        if len(arxiv_sel) == 0:
            return False
        return all(e in self.DICT_ARXIV for e in arxiv_sel.split(','))

    def translate_arxiv_sel(self, args):
        value = args.pop('arxiv_sel', None)
        if value is None:
            return
        # arXiv classes count only if the astronomy/physics databases are not selected
        selected = urllib.parse.unquote(''.join(self.translation.filter))
        if 'database:"astronomy"' in selected or 'database:"physics"' in selected:
            return
        if self.validate_arxiv_sel(value):
            entry = value.split(',')
            if len(entry) == len(self.DICT_ARXIV):
                self.translation.search.append('property:(' + quote("EPRINT_OPENACCESS") + ')')
            else:
                arxiv_sel = ' OR '.join('"' + self.DICT_ARXIV[e].lower() + '"' for e in entry)
                self.translation.search.append('keyword:(' + quote(arxiv_sel) + ')')
        else:
            self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
            self.translation.unprocessed_fields.append('arxiv_sel')

    def parse_bibstem(self, value):
        """'ApJ..,-AJ...' -> bibstem:("ApJ..") AND -bibstem:("AJ...")"""
        bibstem = ''
        match = re.findall('([-+]*[A-Za-z&.0-9]{2,9})', value)
        if match:
            positive = []
            negative = []
            for e in match:
                if e.startswith('-'):
                    negative.append(quote('"' + e[1:] + '"'))
                elif e.startswith('+'):
                    positive.append(quote('"' + e[1:] + '"'))
                else:
                    positive.append(quote('"' + e + '"'))
            ref_stems_positive = ' OR '.join(positive)
            ref_stems_negative = ' OR '.join(negative)
            if positive and negative:
                bibstem = 'bibstem:(' + ref_stems_positive + ') AND ' + '-bibstem:(' + ref_stems_negative + ')'
            elif positive:
                bibstem = 'bibstem:(' + ref_stems_positive + ')'
            elif negative:
                bibstem = '-bibstem:(' + ref_stems_negative + ')'
        else:
            self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
            self.translation.unprocessed_fields.append(value)
        return bibstem

    def translate_ref_stems(self, args):
        """ref_stems="ApJ..,AJ..." -> bibstem:(ApJ.. OR AJ..)"""
        value = args.pop('ref_stems', None)
        if value:
            self.translation.search.append(self.parse_bibstem(value))

    def translate_search_docs(self, args):
        """bibstem, year (2019 or 2019-2020), volume and page"""
        search = ''
        value = args.pop('bibstem', None)
        if value:
            search = self.parse_bibstem(value)

        value = args.pop('year', None)
        if value:
            match = re.search(r'^([12][089]\d\d-[12][089]\d\d|[12][089]\d\d)$', value)
            if match:
                parts = value.split('-')
                year = '[' + parts[0] + ' TO ' + parts[1] + ']' if len(parts) == 2 else parts[0]
                search += quote(' AND ' if len(search) > 0 else '') + 'year:' + year
            else:
                self.translation.error_message.append('UNRECOGNIZABLE_VALUE')
                self.translation.unprocessed_fields.append(value)

        value = args.pop('page', None)
        if value:
            search += quote(' AND ' if len(search) > 0 else '') + 'page:' + quote('"' + value + '"')

        value = args.pop('volume', None)
        if value:
            search += quote(' AND ' if len(search) > 0 else '') + 'volume:' + quote('"' + value + '"')

        if len(search) > 0:
            self.translation.search.append(search)

    # -- classic field parsing ----------------------------------------------

    @staticmethod
    def _classic_terms(value):
        """split on ';' or newlines; returns [(negate, term)] with whitespace stripped"""
        value = urllib.parse.unquote(value)
        value = value.replace('\r\n', ';')
        out = []
        for v in value.split(';'):
            v = re.sub(r"^\s+", "", v)
            negate = False
            if v.startswith('+') or v.startswith('-'):
                negate = v.startswith('-')
                v = v[1:]
            v = re.sub(r"^\s+|\s+$", "", v)
            if v:
                out.append((negate, v))
        return out

    @classmethod
    def classic_field_to_array(cls, value):
        """'Huchra, J; -Geller' -> ['"Huchra, J"', '-"Geller"']"""
        values = []
        for negate, v in cls._classic_terms(value):
            if not (v.startswith('"') and v.endswith('"')):
                v = ('-' if negate else '') + '"' + v + '"'
            values.append(v)
        return values

    @classmethod
    def classic_field_to_string(cls, value):
        """'dark matter; -halo' -> ['dark matter -halo']"""
        return [' '.join(('-' if negate else '') + v for negate, v in cls._classic_terms(value))]


# ---------------------------------------------------------------------------

def translate(multi):
    """{name: [values]} -> Translation"""
    return Translator().translate(classic_args(multi))


def query_pairs(query):
    """Split tugboat's partially encoded query string into decoded
    (name, value) pairs -- what SciX does with a /search/q=... URL."""
    pairs = []
    for part in query.replace('+', ' ').split('&'):
        if not part:
            continue
        k, _, v = part.partition('=')
        pairs.append((urllib.parse.unquote(k), urllib.parse.unquote(v)))
    return pairs


# characters left unencoded in query values: the RFC 3986 characters that
# are allowed in a query and have no special meaning to SciX's parser
# ('&', ';', '+', '#', '%' and anything outside RFC 3986 are encoded)
_SAFE = ":/@!$'()*,="


def search_url(base, multi):
    """{name: [values]} -> (SciX search URL, list of translation notes)"""
    t = translate(multi)
    qs = '&'.join(f"{quote(k, safe='')}={quote(v, safe=_SAFE)}" for k, v in query_pairs(t.query))
    return f"{base}/search?{qs}", t.messages()
