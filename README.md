MHI
===

mhi is a commandline style mailreader in the tradition of mh and nmh,
but mutated to support IMAP.

[![Build Status](https://github.com/pjz/mhi/actions/workflows/python-test.yml/badge.svg)](https://github.com/pjz/mhi/actions/workflows/python-test.yml)

Why?
----

One thing that IMAP provides is the ability for multiple clients to
access the same mail store. Graphical clients are all well and good,
but sometimes a reversion to the commandline is necessary. Neither mh
nor nmh will talk to an IMAP server (mh's original semantics, which
nmh duplicates, rely on messages not auto-renumbering, as they do in
IMAP folders), so I had to write my own client.  Python's imaplib made this easy.

How?
----

As of v0.6.5 MHI is available as a PyPI package (`pipx install mhi`)
The same version also incorporates the old mkLinks wrapper-script functionality
via:

      python -m mhi.mklinks <destdir>

.mhirc
------

.mhirc is an ini-style config file (parsed with configobj).  Useful keys:

 * `connection` - an imap[s]://[username[:password]]@host[:port]/path url string that
 specifies how to connect to the imap server

 * `connection_passwd` - the password to use when connection. To avoid putting the
 password in plaintext in this file, if the string is surrounded by backticks
 (`), it will be executed as a shell script whose stdout will be used as the
 password.

 * `folder_prefix` - the prefix to add to your IMAP folders

 * `comp_template` - the template put into your editor when you use `comp` to write new mail

 * `repl_template` - the template put into your editor when you `repl`y to a message



TODO:
-----

 * use click - but would require new commands?
 * more help - should be self-documenting

Licensing information is in the LICENSE file. (short version: GPLv3 or CCBYSA)

