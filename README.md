MHI
---

mhi is a commandline style mailreader in the tradition of mh and nmh,
but mutated to support IMAP.

[![Build Status](https://travis-ci.org/pjz/mhi.svg?branch=master)](https://travis-ci.org/pjz/mhi)

Why?

One thing that IMAP provides is the ability for multiple clients to
access the same mail store. Graphical clients are all well and good,
but sometimes a reversion to the commandline is necessary. Neither mh
nor nmh will talk to an IMAP server, so I had to write my own client.
Python's imaplib made this easy.

Version history:
----------------

0.6.5 Make it a python package available from PyPI, etc.
      Incorporate the wrapper script and mkLinks functionality; try:

      python -m mhi.mklinks <destdir>


0.5 Inital release because I'm losing inspiration and should share what
    I've managed so far.

TODO:
-----

 * use getopt
 * more help - should be self-documenting ala svn/cvs

Licensing information is in the LICENSE file. (short version: GPLv3 or CCBYSA)

