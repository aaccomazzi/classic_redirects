#!/usr/bin/perl
#
# A replacement handler for all classic CGI scripts.
# See: https://httpd.apache.org/docs/2.4/handler.html
#

my $prod = 'https://ui.adsabs.harvard.edu';
my $dev = 'https://dev.adsabs.harvard.edu';
my $bumblebee = $prod;
my $classic = "$bumblebee/classic-form/";

my $HOMEPAGE = $bumblebee;
my $MODERN = { 'url' => $bumblebee, 'map' => nopath };
my $CLASSIC = { 'url' => $classic, 'map' => nopath };
my $PAPER = { 'url' => "$bumblebee/paper-form/", 'map' => nopath };
my $ABS = { 'url' => "$bumblebee/abs", 'map' => bibpath };

my $REDIRECT_MAP = {
    'abs_connect' => {
	'url' => "$bumblebee/tugboat/classicSearchRedirect",
	'noparams' => $classic,
    },
    'basic_connect' => {
	'url' => "$bumblebee/tugboat/classicSearchRedirect",
	'noparams' => $bumblebee,
    },
    'bib_query' => { 
	'url' => "$bumblebee/abs",
	'map' => bib2abspath,
    },
    'data_query' => {
	'url' => "$bumblebee/link_gateway",
	'map' => data2resolver,
    },
    'ref_query' => {
	'url' => "$bumblebee/abs",
	'map' => ref2abspath,
    },
    # ex: /cgi-bin/nph-ref_history?refs=AR&bibcode=1976ApJ...203..297S
    'ref_history' => {
	'url' => "$bumblebee/abs",
	'map' => refhist2abspath,
    },
    
    # must also handle http://adsabs.harvard.edu/abstract_service.html/legacy
    'abstract_service.html' => $CLASSIC,
    'physics_service.html' => $CLASSIC,
    'preprint_service.html' => $CLASSIC,
    'general_service.html' => $CLASSIC,
    'education_service.html' => $CLASSIC,
    'default_service.html' => $CLASSIC,
    'mighty_search.html' => $CLASSIC,

    'basic_search.html' => $MODERN,
    'basic_service.html' => $MODERN,
    'quick_service.html' => $MODERN,
    'fulltext_service.html' => $MODERN,
    'advanced_fulltext_service.html' => $MODERN,
    'index.html' => $MODERN,

    'ast_bib.html' => $PAPER,
    'pre_bib.html' => $PAPER,
    'gen_bib.html' => $PAPER,
    'phy_bib.html' => $PAPER,
    'pre_bib.html' => $PAPER,
    'custom_bib.html' => $PAPER,
    'bib_abs.html' => $PAPER,

    'abs' => $ABS,
    'doi' => $ABS,
    'arXiv' => $ABS,

    ''           => $MODERN,
    'index.html' => $MODERN,
};

# scripts and parameters that are handled locally
# (execute rather than redirect)
my $HANDLE_MAP = {
    'abs_connect' => ['library'],
};

# data types that are handled locally (execute)
my $HANDLE_DATATYPE = {
    'XML' => 1,
    'RSS' => 1,
    'VOTABLE' => 1,
    'REFMAN' => 1,
    'PORTABLE' => 1, # for paper-arxiv matching
    'Custom' => 1    # for wrf
};


fix_env();
my $params = &ReadParse(*in);
my $debug = delete($params->{debug});
debug_env($params) if ($debug);

my $orig = $ENV{SCRIPT_FILENAME};
my $dir = $orig; $dir =~ s:/[^/]*$::g;
my $script = $orig; $script =~ s:^.*/::g;
my $nph = ($script =~ s/^nph-//) ? 1 : 0;

if (not $orig) {
    # we didn't find a resource
    warn "legacy_handler: no original file found, bailing out via a redirect\n";
    redirect($HOMEPAGE);
    exit(0);
} 

warn "legacy_handler: original path is \"$orig\"\n";

# now decide if we should continue to execute the local program
if (-f $orig and -x $orig) {
    if ($HANDLE_DATATYPE->{$params->{data_type}}) {
	# the request is asking for output in machine readable format,
	# and we have no equivalent API output (RSS, XML, VOTABLE)
	execute($orig);
    } elsif (not $REDIRECT_MAP->{$script}) {
	# if there is no redirection in place for this script, execute original
	execute($orig);
    } elsif ($HANDLE_MAP->{$script}) {
	# see if this is a script with a parameter that requires
	# local handling
	foreach my $p (@{$HANDLE_MAP->{$script}}) {
	    if (defined($params->{$p})) {
		warn "legacy_handler: handling script \"$script\", param \"$p\"\n";
		execute($orig);
	    }
	}
    }
} elsif ($REDIRECT_MAP->{$script}) {
    # it's something that needs to be redirected, continue
    warn "legacy_handler: found endpoint \"$script\" in redirect map\n";
} elsif (-f $orig) {
    # it's a real file
    warn "legacy_handler: found original file \"$orig\"\n";
    insert_login($orig);
} elsif ($orig =~ m{/$}) {
    # looks like a directory
    warn "legacy_handler: found original dir \"$orig\"\n";
    insert_login($orig, 'index.html');
} else {
    warn "legacy_handler: no resource found, continuing...!\n";
}

# ok, if we got here it means that we can redirect
# let's figure out the URL to redirect to and the query path and string
my $redirect_url = $REDIRECT_MAP->{$script}->{url};
my $rewrite_func = $REDIRECT_MAP->{$script}->{'map'} || undef;
my $redirect_noparams = $REDIRECT_MAP->{$script}->{noparams} || undef;

my $qs = ($ENV{REQUEST_METHOD} eq 'POST') ? $in : $ENV{QUERY_STRING};
my $qp = $ENV{PATH_INFO};

if ($rewrite_func) {
    ($qp,$qs) = &{$rewrite_func}($qp,$qs,$params);
}

my $urlpath = $qp . ($qs ? "?$qs" : '');
my $url = $redirect_url . $urlpath;

if ($redirect_noparams and not $urlpath) {
    $url = $redirect_noparams;
    warn "legacy_handler: no parameters found, redirecting to \"$url\"\n";
}

redirect($url,$params,$debug);


###############

sub insert_login {
    my $path = shift;
    my $append = shift || '';
    my $script = $ENV{DOCUMENT_ROOT} . "/insert_login";

    $ENV{PATH_INFO} = $ENV{ORIG_PATH_INFO};
    $ENV{SCRIPT_NAME} = '/insert_login';
    $ENV{SCRIPT_FILENAME} = $ENV{ORIG_SCRIPT_FILENAME};

    if ($append) {
	$path .= $append;
	$ENV{PATH_INFO} .= $append;
	$ENV{SCRIPT_FILENAME} .= $append;
	$ENV{PATH_TRANSLATED} .= $append;
	$ENV{REDIRECT_URL} .= $append;
	warn "legacy_handler: resetting original path to be \"$path\"\n";
	warn "legacy_handler: resetting PATH_INFO to be \"$ENV{PATH_INFO}\"\n";
	warn "legacy_handler: resetting SCRIPT_NAME to be \"$ENV{SCRIPT_NAME}\"\n";
	warn "legacy_handler: resetting SCRIPT_FILENAME to be \"$ENV{SCRIPT_FILENAME}\"\n";
    }

    if ($script and -x $script) {
	warn "legacy_handler: delegating html content to $script\n";
	exec $script;
    } else {
	warn "legacy_handler: cannot locate executable $script\n";
    }
    redirect($HOMEPAGE);
}

sub execute {
    my $orig = shift;

    if ($ENV{REQUEST_METHOD} eq 'POST') {
	# we have read stdin already, just turn this into a get
	# and hope for the best
	warn "legacy_handler: resetting method from POST to GET with QUERY_STRING=$in\n";
	$ENV{REQUEST_METHOD} = 'GET';
	$ENV{QUERY_STRING} = $in;
    }
    
    if ($orig and -x $orig) {
	warn "legacy_handler: executing \"$orig\" with QUERY_STRING=$ENV{QUERY_STRING}\n";
	exec $orig;
    } elsif (not $orig) {
	warn "legacy_handler: no original script found, redirecting home\n";
    } elsif (not -x $orig) {
	warn "legacy_handler: no executable script found for \"$orig\", redirecting home\n";
    } else {
	warn "legacy_handler: unexpected condition found, redirecting home\n";
    }
    redirect($HOMEPAGE);
}


sub redirect {
    my ($url,$params,$debug) = @_;

    # XXX check for nph?
    warn "legacy_handler: redirecting to $url\n";
    print "Status: 301 Document Moved\r\nLocation: $url\r\n\r\n";
    exit(0) if ($ENV{REQUEST_METHOD} eq 'HEAD');

    print "<html><head><title>Found</title></head><body><h1>Document Found</h1><p>The document is available at <a href=\"$url\">$url</a></p>\r\n";

    if ($debug) {
	my ($env,$input) = debug_env($params, 1);
	print "The search parameters were:\r\n<PRE>\r\n$input\r\n</PRE>\r\n";
    }
    print "</body></html>\r\n";
}


# translates links provided by data_query to link_gateway
sub data2resolver {
    my ($b, $params) = bib_extract(@_);
    my %typemap = (
	abstract   => 'abstract',
	citations  => 'citations',
	data       => 'data',
	ejournal   => 'pub_html',
	article    => 'article',
	gif        => 'ads_scan',
	spires     => 'inspire',
	library    => 'librarycatalog',
	video      => 'presentation',
        ned        => 'ned',
        associated => 'associated',
	pds        => 'pds',
	references => 'references',
        simbad     => 'simbad',
        toc        => 'toc',
        ar         => 'coreads',
        preprint   => 'eprint_html'
	);
        
    my $type = $typemap{lc($params->{link_type})} || '';
    my $qp = '';
    if ($b) {
	$qp = '/'. escape($b);
	$qp .= '/'. $type if ($type);
    }
    # ignore qs
    return ($qp,'');
}

# returns no path or query string, to allow a plain redirection
# to a fixed url
sub nopath {
    return ('','');
}

# returns just the query path; ideally we should validate the
# input, but it's hard to do this right by pruning things because
# the path could contain '/' in DOIs and arXiv ids
sub bibpath {
    my $qp = shift;
    # deal with badly formatted URIs such as
    # http://adsabs.harvard.edu/abs/2013A&amp;A...549A..39A
    $qp =~ s/\&amp\;/&/g;
    $qp .= '/abstract' unless (substr($qp,1) =~ /\//);
    return ($qp,'');
}

# translates links to bib_query to links to /abs
sub bib2abspath {
    my ($b, $params) = bib_extract(@_);
    # XXX should we append query parameters?
    my $qp = "/" . escape($b) if ($b);
    my $qs = qsencode($params);
    return($qp,$qs);
}

# translates links to ref_query to links to /abs/<bibcode>/(references|citations|coreads)
sub ref2abspath {
    my ($b, $params) = bib_extract(@_);
    my %TYPEMAP = (citations  => 'citations',
		   references => 'references',
		   ar         => 'coreads');
    my $type = $TYPEMAP{lc($params->{refs})} || 'citations';
    my $qp = '';
    if ($b) {
	$qp = "/" . escape($b) . "/" . $type;
    }
    return($qp,'');
}

# ref history, e.g. http://adsabs.harvard.edu/cgi-bin/nph-ref_history?refs=AR&bibcode=1976ApJ...203..297S
sub refhist2abspath {
    my ($b, $params) = bib_extract(@_);
    my $qp = '';
    if ($b) {
	$qp = "/" . escape($b) . "/metrics";
    }
    return($qp,'');
}
    
# extracts a bibcode from the parsed search parameters
# handle the following cases for params:
#    /cgi-bin/script?<bibcode>&param1=val1&param2=val2...
#    /cgi-bin/script?bibcode=<bibcode>&param1=val1&param2=val2...
sub bib_extract {
    my ($path,$query,$params) = @_;
    my $bibcode = '';
    if ($params->{bibcode}) {
	$bibcode = delete($params->{bibcode});
    } else {
	foreach my $k (keys %{$params}) {
	    if ($params->{$k} eq '') {
		$bibcode = $k;
		delete($params->{$k});
		last;
	    }
	}
    }
    return wantarray ? ($bibcode, $params) : $bibcode;
}

sub debug_env {
    my $params = shift;
    my $dont_print = shift;

    my $env = join("\n", map { "$_=$ENV{$_}" } keys %ENV);
    my $input = join("\n", map { "$_=".$params->{$_} } keys %{$params});

    unless ($dont_print) {
	print  <<"EOF";
Content-type: text/html

<HTML>
<HEAD>
<TITLE>ADS Query Environment</TITLE>
</HEAD>
<BODY BGCOLOR="#ffffff">
<BIG>
<CENTER>
<H1>ADS Query Environment</H1>
</CENTER>
<P>
<BLOCKQUOTE>
<PRE>
$input
<hr>
$env
</PRE>
</BLOCKQUOTE>
</BODY>
</HTML>
EOF
    }

    return ($env, $input);
}

sub fix_env {

    $ENV{ORIG_PATH_TRANSLATED} = $ENV{PATH_TRANSLATED};
    my $orig = $ENV{PATH_TRANSLATED};
    $ENV{SCRIPT_FILENAME} = $orig;

    # Figure out what the original SCRIPT_NAME, SCRIPT_FILENAME and PATH_INFO 
    # should be.
    # When this handler intercepts the request, the environment is set this way:
    #    SCRIPT_NAME=/legacy_handler
    #    PATH_INFO=/cgi-bin/showme/yyy
    #    SCRIPT_FILENAME=/adsx1/adsabs/cgi/bin/showme/yyy
    # whereas when the script is executed directluy we have this environment:
    #    SCRIPT_NAME=/cgi-bin/showme
    #    PATH_INFO=/yyy
    #    SCRIPT_FILENAME=/adsx1/adsabs/cgi/bin/showme
    $ENV{ORIG_PATH_INFO} = $ENV{PATH_INFO};
    $ENV{ORIG_SCRIPT_NAME} = $ENV{SCRIPT_NAME};
    $ENV{ORIG_SCRIPT_FILENAME} = $ENV{SCRIPT_FILENAME};

    my $path_info = '';
    my $script_name = $ENV{PATH_INFO};
    my $script_filename = $ENV{SCRIPT_FILENAME};
    while (not -e $script_filename) {
	last unless ($script_filename =~ s{(/[^/]*?$)}{});
	my $fragment = $1;
	$path_info = "$fragment$path_info";
	$script_name =~ s/\Q$fragment\E$//;
    }

    # remove the "nph-" prefix to the script since we won't be
    # generating raw headers from this script
    $ENV{REQUEST_URI} =~ s{/nph-(\w+)}{/$1};
    $script_name =~ s{/nph-(\w+)}{/$1};
    $script_filename =~ s{/nph-(\w+)}{/$1};

    # an empty PATH_INFO env variable may confuse downsream scripts
    if ($path_info) {
	$ENV{PATH_INFO} = $path_info;
    } else {
	delete($ENV{PATH_INFO});
    }
    $ENV{SCRIPT_NAME} = $script_name;
    $ENV{SCRIPT_FILENAME} = $script_filename;
}

# URL-decodes a string
sub unescape {
    my ($url) = @_;
    $url =~ s/%([\dA-Fa-f][\dA-Fa-f])/pack("C",hex($1))/ge;
    return $url;
}

# URL-encodes a string
sub escape {
    my $str = shift;
    my $pat = shift || '[\x00-\x20"#%/;<>?\x7F-\xFF]';

    $str =~ s/($pat)/sprintf("%%%02lx",unpack('C',$1))/ge;
    return($str);
}

sub qsencode {
    my $params = shift;
    my $qs = '';
    foreach my $k (keys %{$params}) {
	$qs .= escape($k) ."=". escape($params->{$k}) ."&";
    }
    chop($qs);
    return $qs;
}

my %BasicEntities = (
    '"' => "&quot;",
    ">" => "&gt;",
    "<" => "&lt;",
    "'" => "&apos;",
    "&" => "&amp;",
    );

# escapes the HTML reserved characters in the input string
sub HtmlEscape {
    my $str = shift or return undef;
    my $default = shift;
    $default ||= join('',keys(%BasicEntities));
    
    $str =~ s/([$default])/$BasicEntities{$1}/g;
    return $str;
}

sub ReadParse {
    local (*in) = @_ if @_;
    local ($i, $key, $val);

    # Read in text
    if ($ENV{'REQUEST_METHOD'} eq "GET" or $ENV{REQUEST_METHOD} eq 'HEAD') {
	$in = $ENV{'QUERY_STRING'};
	# deal with non-properly encoded bibcodes in URL, e.g. 
        # http://adsabs.harvard.edu/cgi-bin/nph-data_query?bibcode=2016A&A...590A.124R&link_type=ARTICLE&d_key=AST#page=2
	# for now we won't be too aggressive and just do this for the "bibcode" URL parameter
	$in =~ s/\b(bibcode=\d{4}\w{1,3})\&/$1%26/;
    } elsif ($ENV{'REQUEST_METHOD'} eq "POST") {
	read(STDIN,$in,$ENV{'CONTENT_LENGTH'});
    }

    @in = split(/&(?:amp\;)?/,$in);
    
    foreach $i (0 .. $#in) {
	# Convert plus's to spaces
	$in[$i] =~ s/\+/ /g;
	
	# Split into key and value.  
	($key, $val) = split(/=/,$in[$i],2); # splits on the first =.
	
	# Convert %XX from hex numbers to alphanumeric
	$key =~ s/%(..)/pack("c",hex($1))/ge;
	$val =~ s/%(..)/pack("c",hex($1))/ge;
	
	# Associate key and value
	$in{$key} .= "\0" if (defined($in{$key})); # \0 is the multiple separator
	$in{$key} .= $val;
	
    }
    
    return \%in;
}
