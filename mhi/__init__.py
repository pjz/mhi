#!/usr/bin/env python
#
# Goal: MH-ish commands that will talk to an IMAP server
#
# Commands that work: folder, folders, scan, rmm, rmf, pick/search, help,
#                     debug, refile, show, next, prev, mr
#
# Commands to make work: sort, comp, repl, dist, forw, anno
#
# * sort should just store a sort order to apply to output instead of
#   actually touching the mailboxes.  This will affect the working of
#   anything that takes a msgset as well as scan, next, prev, and pick
#
# handy aliases:
#    mailchk - folders with new messages - mhi folders |grep -v " 0$"
#    nn - show new messages in a folder- mhi scan `mhi pick \Unseen`
#
# minor bits of code taken from http://www.w3.org/2000/04/maillog2rdf/imap_sort.py
# everything else Copyright Paul Jimenez, released under the GPL
# canonical copy at http://www.place.org/~pj/software/mhi

import os
import sys
import time
import email
import shutil
import string
import imaplib
import smtplib
import subprocess
from functools import wraps
from io import StringIO
from pathlib import Path
from urllib import parse as urlparse

from configobj import ConfigObj

cfgdir = os.environ.get('HOME', '')
config = ConfigObj(infile=f"{cfgdir}/.mhirc", create_empty=True)
state = ConfigObj(infile=f"{cfgdir}/.mhistate", create_empty=True)
Debug = 0


def _debug_noop(*args):
    pass


def _debug_stdout(arg):
    f = arg
    if not callable(arg):
        f = lambda: arg
    print("DEBUG: ", f())


_debug = _debug_noop


def sexpr_readsexpr(s):
    from .sexpr import SexprParser
    return SexprParser(StringIO(s)).parse()


def readlisp_readsexpr(s):
    from .readlisp import readlisp
    return readlisp(tostr(s))


readsexpr = readlisp_readsexpr


PickDocs = """ From RFC2060:
      When multiple keys are specified, the result is the intersection
      (AND function) of all the messages that match those keys.  For
      example, the criteria DELETED FROM "SMITH" SINCE 1-Feb-1994 refers
      to all deleted messages from Smith that were placed in the mailbox
      since February 1, 1994.  A search key can also be a parenthesized
      list of one or more search keys (e.g. for use with the OR and NOT
      keys).

      In all search keys that use strings, a message matches the key if
      the string is a substring of the field.  The matching is case-
      insensitive.

      The defined search keys are as follows.  Refer to the Formal
      Syntax section for the precise syntactic definitions of the
      arguments.

      <message set>  Messages with message sequence numbers
                     corresponding to the specified message sequence
                     number set

      ALL            All messages in the mailbox; the default initial
                     key for ANDing.

      ANSWERED       Messages with the \\Answered flag set.

      BCC <string>   Messages that contain the specified string in the
                     envelope structure's BCC field.

      BEFORE <date>  Messages whose internal date is earlier than the
                     specified date.

      BODY <string>  Messages that contain the specified string in the
                     body of the message.

      CC <string>    Messages that contain the specified string in the
                     envelope structure's CC field.

      DELETED        Messages with the \\Deleted flag set.

      DRAFT          Messages with the \\Draft flag set.

      FLAGGED        Messages with the \\Flagged flag set.

      FROM <string>  Messages that contain the specified string in the
                     envelope structure's FROM field.

      HEADER <field-name> <string>
                     Messages that have a header with the specified
                     field-name (as defined in [RFC-822]) and that
                     contains the specified string in the [RFC-822]
                     field-body.

      KEYWORD <flag> Messages with the specified keyword set.

      LARGER <n>     Messages with an [RFC-822] size larger than the
                     specified number of octets.

      NEW            Messages that have the \\Recent flag set but not the
                     \\Seen flag.  This is functionally equivalent to
                     "(RECENT UNSEEN)".

      NOT <search-key>
                     Messages that do not match the specified search
                     key.

      OLD            Messages that do not have the \\Recent flag set.
                     This is functionally equivalent to "NOT RECENT" (as
                     opposed to "NOT NEW").

      ON <date>      Messages whose internal date is within the
                     specified date.

      OR <search-key1> <search-key2>
                     Messages that match either search key.

      RECENT         Messages that have the \\Recent flag set.

      SEEN           Messages that have the \\Seen flag set.

      SENTBEFORE <date>
                     Messages whose [RFC-822] Date: header is earlier
                     than the specified date.

      SENTON <date>  Messages whose [RFC-822] Date: header is within the
                     specified date.

      SENTSINCE <date>
                     Messages whose [RFC-822] Date: header is within or
                     later than the specified date.

      SINCE <date>   Messages whose internal date is within or later
                     than the specified date.

      SMALLER <n>    Messages with an [RFC-822] size smaller than the
                     specified number of octets.

      SUBJECT <string>
                     Messages that contain the specified string in the
                     envelope structure's SUBJECT field.

      TEXT <string>  Messages that contain the specified string in the
                     header or body of the message.

      TO <string>    Messages that contain the specified string in the
                     envelope structure's TO field.

      UID <message set>
                     Messages with unique identifiers corresponding to
                     the specified unique identifier set.

      UNANSWERED     Messages that do not have the \\Answered flag set.

      UNDELETED      Messages that do not have the \\Deleted flag set.

      UNDRAFT        Messages that do not have the \\Draft flag set.

      UNFLAGGED      Messages that do not have the \\Flagged flag set.

      UNKEYWORD <flag>
                     Messages that do not have the specified keyword
                     set.

      UNSEEN         Messages that do not have the \\Seen flag set.

"""


class UsageError(Exception):
    pass


def takesFolderArg(f):
    @wraps(f)
    def parseFolderArg(args):
        '''
        parse the args into a folder-spec (denoted by a leading +, last of
        which is used if multiple are listed), and the rest of the args
        '''
        folder = None
        outargs = []
        for a in args:
            if a.startswith('+') and len(a) > 1:
                folder = a[1:]
            else:
                outargs.append(a)

        if folder is None:
            # nothing specified, use the default folder
            folder = None
        elif folder.startswith('+'):
            # double leading + means ignore the folder prefix
            folder = folder[1:]
        else:
            prefix = config.get('folder_prefix', '')
            folder = prefix + folder

        return f(folder, outargs)
    return parseFolderArg


def cmd_result(cmd):
    result = subprocess.run(cmd, capture_output=True, shell=True, check=True)
    _debug(lambda: f'ran command: {cmd} got result: {result.stdout}')
    stdout = tostr(result.stdout).strip()
    return stdout


def tostr(s):
    '''
    decode s if it's bytes, return it if it's a str, else do str() on it
    '''
    if type(s) == str:
        return s
    elif type(s) == bytes:
        return s.decode()
    else:
        return str(s)


class Connection:
    """A wrapper around an IMAP connection"""

    def __init__(self, startfolder=None):

        schemes = {'imap': imaplib.IMAP4,
                   'imaps': imaplib.IMAP4_SSL,
                   'stream': imaplib.IMAP4_stream,
                  }
        scheme, netloc, path, _, _, _ = urlparse.urlparse(config['connection'])
        _debug(lambda: f'scheme: {scheme} netloc: {netloc} path: {path}')
        if netloc:
            if '@' in netloc:
                userpass, hostport = netloc.rsplit('@', 1)
            else:
                userpass, hostport = None, netloc
            if ':' in hostport:
                host, port = hostport.rsplit(':', 1)
            else:
                host = hostport
                port = "143"
                if scheme[-1] == 's':
                    port = "993"
            user = config.get('connection_user', os.environ.get('USER', ''))
            passwd = config.get('connection_passwd', os.environ.get('MHI_PASSWD', ''))
            if ':' in userpass:
                user, passwd = userpass.split(':', 1)
            elif userpass is not None:
                user = userpass
            if not passwd:
                print("No password provided. Set connnetion_password or put it in the url or in MHI_PASSWD environment var")
                sys.exit(1)
            if passwd.startswith('`') and passwd.endswith('`'):  # shell eval it
                cmd = passwd[1:-1]
                passwd = cmd_result(cmd)
            _debug(lambda: f"{scheme} connection to {user} : {passwd} @ {host}:{port}")
            session = schemes[scheme](host, int(port))
            session.login(user, passwd)
        else:
            session = schemes[scheme](path)
        session.debug = 0 if _debug == _debug_noop else 4
        self.session = session
        if startfolder is None:
            startfolder = state.get('folder', 'INBOX')
        self.select(startfolder)
        state['folder'] = startfolder

    def __enter__(self):
        return self

    def __exit__(self, *args):
        _debug(f'Exit args are: {args!r}')
        try:
            self.session.close()
            self.session.logout()
        except imaplib.IMAP4.error:
            pass

    def __getattr__(self, name):
        raw = False
        if name.startswith('raw_'):
            raw = True
            name = name[4:]
        result = getattr(self.session, name)
        if result is None:
            raise AttributeError
        if raw:
            return result
        return die_on_error(result)

    def select(self, folder, errmsg=None):
        errmsg = errmsg or f"Problem changing to folder {folder}:"
        return die_on_error(self.session.select)(folder, errmsg=errmsg)

    def folders(self):
        result, flist = self.raw_list()
        # check result
        folders = []
        _debug(lambda: f"flist: {flist!r} ")
        for fline in flist:
            fstr = tostr(fline)
            f = str(readsexpr(f'({fstr})')[2])
            _debug(lambda: f" f: {f!r}")
            folders.append(f)
        return folders

    def folderstatus(self, folder):
        result, data = self.raw_status(folder, '(MESSAGES RECENT UNSEEN)')
        if result != 'OK':
            return ()
        stats = readsexpr(f'({tostr(data[0])})')[1]
        msgs, recent, unseen = stats[1], stats[3], stats[5]
        return msgs, recent, unseen


def die_on_error(f):
    def _die_on_err_wrapper(*args, **kwargs):
        msgstr = kwargs.get('errmsg', 'There was a problem:')
        if 'errmsg' in kwargs:
            del kwargs['errmsg']
        try:
            result, data = f(*args, **kwargs)
        except imaplib.IMAP4.error as e:
            result = "IMAP error"
            data = str(e)
        if result != 'OK':
            print(f'{msgstr} {result}: {data}')
            sys.exit(1)
        return data
    return _die_on_err_wrapper


def enable_pager():
    if sys.stdout.isatty():
        pager = os.environ.get('PAGER', None)
        if pager is None:
            for p in ['/usr/bin/less', '/bin/more']:
                if Path(p).exists():
                    pager = p
                    break
        if pager is not None:
            sys.stdout = os.popen(pager, 'w')


def msgset_from(arglist):
    ''' turn a list of numbers into a valid msgset:
        Change some common symbols into an IMAP-style msgset:
        'cur' -> remembered folder current msg
        'prev' -> remembered folder current msg - 1
        'next' -> remembered folder current msg + 1
        'last' -> '*'
        '$' -> '*'
        '-' -> ':'
    '''
    msgset = ' '.join(arglist)
    cur = state.get(state['folder']+'.cur', None)
    _debug(lambda: f"cur is {cur!r}")
    _debug(lambda: f"type(cur) is {type(cur)!r}")
    if cur not in ('None', None):
        msgset = msgset.replace('cur', cur)
        # XXX: bounds-check these?
        msgset = msgset.replace('next', str(int(cur)+1))
        msgset = msgset.replace('prev', str(int(cur)-1))
    elif any(True for dep in ["cur", "prev", "next"] if dep in msgset):
        print(f"No current message, so '{msgset}' makes no sense.")
        sys.exit(1)
    msgset = msgset.replace('-', ':')
    msgset = msgset.replace(' ', ',')
    msgset = msgset.replace('last', "*")
    msgset = msgset.replace('$', "*")
    return msgset


def _checkMsgset(msgset):
    '''Check that a specified string has the grammar of a msgset'''
    # msgset = int | int:int | msgset,msgset
    # '1', '1:5', '1,2,3', '1,3:5' are all valid
    def fail():
        print(f"{msgset} isn't a valid messageset. Try again.")
        sys.exit(1)

    if len(msgset.strip('1234567890,:*')) != 0:
        fail()

    prev = msgset[0]
    if prev in (':', ','):
        fail()

    digits = set(str(i) for i in range(10))

    def is_valid(r):
        rcount = r.count(':')
        if rcount == 0 and all(c in digits for c in r):
            return True
        if rcount != 1:
            return False
        start, end = r.split(':')
        if any(c not in digits for c in start):
            return False
        return end == '*' or all(c in digits for c in end)

    if any(not is_valid(r) for r in msgset.split(',')):
        fail()


def tempFileName(*args, **kwargs):
    import tempfile
    f = tempfile.NamedTemporaryFile(*args, **kwargs)
    name = f.name
    f.close()
    return name


def _crlf_terminate(msgfile):
    '''convenience function to turn a \n terminated file into a \r\n terminated file'''
    tfile = tempFileName(prefix="mhi")
    os.rename(msgfile, tfile)
    with open(tfile, 'r') as infile:
        with open(msgfile, 'w') as outfile:
            for line in infile:
                if not line.endswith('\r\n'):
                    line = line[:-1]  # strip existing \n (or \r?)
                    line += '\r\n'    # add new lineending
                outfile.write(line)


def _edit(msgfile):
    ''' internal common code for comp/repl/dist/medit '''
    env = os.environ
    editor = env.get('VISUAL', env.get('EDITOR', 'editor'))
    try:
        fin = os.system(f"{editor} {msgfile}")
        if Path(msgfile).exists():
            _crlf_terminate(msgfile)
    except Exception as e:
        _debug(lambda: f"editor exception: {e!r}")
        return False
    _debug(lambda: f"editor result code: {fin}")
    return fin == 0


def _SMTPsend(msgfile):
    ret = {'Unknown': 'SMTP problem'}
    msg = email.message_from_file(open(msgfile, "r"))
    fromaddr = msg.get('From', '')
    toaddrs = msg.get_all('To', [])
    _debug(lambda: f"composing message from {fromaddr!r} to {toaddrs!r}")
    server = smtplib.SMTP('localhost')
    # server.set_debuglevel(1)
    try:
        ret = server.sendmail(fromaddr, toaddrs, msg.as_string())
    except smtplib.SMTPRecipientsRefused:
        print("No valid recipients. Try again.")
    except smtplib.SMTPHeloError:
        print("Error talking to SMTP server (No HELO).")
    except smtplib.SMTPSenderRefused:
        print("Error talking to SMTP server (Unacceptable FROM address).")
    except smtplib.SMTPDataError:
        print("Error talking to SMTP server (Data Error).")
    server.quit()
    for k in ret:
        print(f"SMTP Error: {k}: {ret[k]}")
    return len(ret.keys())


def _get_messages(folder, msgset):
    with Connection(folder) as S:
        msglist = S.search(None, msgset, errmsg="Problem with search:")
        messages = []
        for num in msglist[0].split():
            result, data = S.fetch(num, '(RFC822)', errmsg=f"Problem fetching msg {num}: ")
            _debug(lambda: f"Data from message {num!r} : {data!r}")
            messages.append((num, data))
    return messages


def _get_curMessage():
    folder = state['folder']
    try:
        msgset = state[folder + '.cur']
    except KeyError:
        print("Error: No current message selected.")
        raise UsageError()
    _checkMsgset(msgset)
    return _get_messages(folder, msgset)[0][1]


def _template_update(msgfile):

    def _quoted_current(_, msg):
        result = ""
        for part in msg.walk():
            _debug(lambda: f"PART {part.get_content_type()}:")
            for line in part.get_payload(decode=True).split("\n"):
                result += "> " + line + "\n"
        return result

    def __header(_, msg, header):
        if header in msg:
            return msg[header]
        return f"[[Missing {header} header]]"

    def _header_from(data, msg): return __header(data, msg, 'from')
    def _header_date(data, msg): return __header(data, msg, 'date')
    def _header_subject(data, msg): return __header(data, msg, 'subject')

    def _header_from_name(data, msg):
        full = _header_from(data, msg)
        left = full.find("<")
        right = full.find(">")
        if left > -1 and right > -1:
            return full[:left] + full[right+1:]
        return full

    macros = {
        '###QUOTED###': _quoted_current,
        '###:FROM###': _header_from,
        '###:DATE###': _header_date,
        '###:SUBJECT###': _header_subject,
        '###:FROM.NAME###': _header_from_name,
    }

    template = open(msgfile, 'r')
    templatetext = template.readlines()
    outfile = open(msgfile, "w")
    curdata = _get_curMessage()
    curmsg = email.message_from_string(curdata[0][1])
    for line in templatetext:
        changed = True
        while changed:
            changed = False
            for macro, impl in macros.items():
                if macro in line:
                    line = line.replace(macro, impl(curdata, curmsg))
                    changed = True
        outfile.write(line)
    outfile.close()


def comp(args):
    '''Usage: comp

    Compose a new message
    '''
    tmpfile = tempFileName(prefix="mhi-comp-")
    if config.get('comp_template', None):
        shutil.copyfile(config['comp_template'], tmpfile)
    if _edit(tmpfile):
        # edit succeeded, wasn't aborted or anything
        errcount = _SMTPsend(tmpfile)
        if not errcount:
            os.unlink(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
        print("Session aborted.")
        try:
            os.unlink(tmpfile)
        except:
            pass


def repl(args):
    '''Usage: repl

    Reply to the current message, quoting it
    '''
    tmpfile = tempFileName(prefix="mhi-repl-")
    if config.get('repl_template', None):
        shutil.copyfile(config['repl_template'], tmpfile)
        _template_update(tmpfile)
    # TODO: put quoted contents of current message into tmpfile
    # TODO: put the author of the current message in the 'To:' field
    # TODO: swipe MH's -cc, etc syntax for specifying who to copy
    if _edit(tmpfile):
        # edit succeeded, wasn't aborted or anything
        errcount = _SMTPsend(tmpfile)
        if not errcount:
            os.unlink(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
        print("Session aborted.")
        os.unlink(tmpfile)


def _selectOrCreate(S, folder):
    msgcount = '0'
    result, data = S.raw_select(folder)
    _debug(lambda: f" Result: {result}, {data} ")
    if result != 'OK':
        print(f"Folder '{folder}' doesn't exist.  Create it? ")
        answer = sys.stdin.readline().strip().lower()
        if answer.startswith('y'):
            S.create(folder, errmsg="Problem creating folder:")
            S.select(folder, errmsg="Problem selecting newly created folder:")
        else:
            print("Nothing done. exiting.")
            sys.exit(1)
    else:
        msgcount = data[0].decode()
    return msgcount


def folder_name(folder):
    prefix = config.get('folder_prefix', None)
    if prefix and folder.startswith(prefix):
        return folder[len(prefix):]
    return folder


@takesFolderArg
def folder(folder, arglist):
    '''Usage: folder [+<foldername>]

    Change folders / show current folder
    '''
    if arglist:
        raise UsageError()
    if folder is None:
        folder = state.get('folder')
    if folder is None:
        print("No current folder selected. Use 'folders' to get a list.")
    with Connection() as S:
        msgcount = _selectOrCreate(S, folder)
    state['folder'] = folder
    # inbox+ has 64 messages  (1-64); cur=63; (others).
    cur = state.get(folder+'.cur', 'unset')
    print(f"Folder {folder_name(folder)} has {msgcount} messages, cur is {cur}.")


def folders(args):
    '''Usage: folders

    Show all folders
    '''
    enable_pager()
    HEADER = "FOLDER"
    with Connection() as S:
        stats = {}
        for f in S.folders():
            status = S.folderstatus(f)
            stats[f] = status or (0, 0, 0)
    stats[HEADER] = ["# MESSAGES", "RECENT", "UNSEEN"]
    folderlist = sorted(key for key in stats if key != HEADER)
    totalmsgs, totalnew = 0, 0
    for folder in [HEADER]+folderlist:
        _debug(lambda: f" folder: {folder!r}")
        iscur = '*' if folder == state['folder'] else ' '
        messages, recent, unseen = stats[folder]
        cur = state.get(f'{folder}.cur', ['-', 'CUR'][folder == HEADER])
        foldr = folder_name(folder)
        print(f"{iscur}{foldr:>20} {cur:7} {messages:7} {recent:7} {unseen:7}")
        if folder != HEADER:
            totalmsgs += int(messages)
            totalnew += int(unseen)
    print(f"TOTAL: {totalmsgs} messages ({totalnew} new) in {len(folderlist)} folders")


def _consolidate(data):
    '''data is a comma-separated list of numbers; this function adds ranges with a dash'''
    from itertools import groupby
    from operator import itemgetter

    _debug(lambda: f"consolidate in: {data!r}")

    str_list = []
    for k, g in groupby(enumerate(data), lambda v: v[0]-v[1]):
        ilist = list(map(itemgetter(1), g))
        _debug(lambda: f"_consolidating: {ilist!r}")
        if len(ilist) > 1:
            str_list.append(f'{ilist[0]}-{ilist[-1]}')
        else:
            str_list.append(f'{ilist[0]}')
    result = ','.join(str_list)
    _debug(lambda: f"consolidate out: {result}")
    return result


@takesFolderArg
def pick(folder, arglist):
    '''Usage: pick <search criteria> [+folder]

    Return a message-set that matches the search criteria.
    Criteria are based on the IMAP spec search string.
    A summary of the IMAP spec is available by calling 'pick' with --help as its only option.
    '''
    if not arglist:
        raise UsageError()
    if len(arglist) == 1 and arglist[0] == "--help":
        print(PickDocs)
        sys.exit(1)
    folder = state['folder'] = folder or state['folder']
    searchstr = '('+' '.join(arglist)+')'
    with Connection(folder) as S:
        data = S.search(None, searchstr, errmsg="Problem with search criteria:")
        _debug(lambda: f"data: {data!r}")
    data = [d for d in data if d != '']
    if data:
        msglist = []
        for m in data:
            msglist += [int(i) for i in m.split()]
        print(_consolidate(msglist))
    else:
        print("0")


def _cur_msg(folder):
    try:
        return state[folder+".cur"]
    except KeyError:
        print("Error: No message(s) selected.")
        raise UsageError()


@takesFolderArg
def refile(destfolder, arglist):
    '''Usage: refile <messageset> +<folder>

    Moves a set of messages from the current folder to a new one.
    Add -k to keep the originals (making this a 'copy' instead of a 'refile').
    '''
    if destfolder is None:
        print("Error: Destination folder must be specified.")
        raise UsageError()
    srcfolder = state["folder"]
    keep = '-k' in arglist
    if keep:
        arglist.remove('-k')

    msgset = msgset_from(arglist) or _cur_msg(srcfolder)
    _checkMsgset(msgset)
    with Connection() as S:
        _selectOrCreate(S, destfolder)
        S.select(srcfolder)
        S.copy(msgset, destfolder, errmsg="Problem with copy:")
        data = S.search(None, msgset, errmsg="Problem with search:")
        msgnums = data[0].split()
        if keep:
            action = 'copied'
        else:
            action = 'refiled'
            print("Refiling... ",)
            for num in msgnums:
                S.raw_store(num, '+FLAGS', '\\Deleted')
                print(".", )
            S.expunge()
        print(f"{len(msgnums)} messages {action} to '{destfolder}'.")
    print("Done.")


@takesFolderArg
def rmf(folder, arglist):
    '''Usage:  rmf +<foldername>
    remove a folder
    '''
    _debug(lambda: f"Folder is {folder!r}")
    if folder is None:
        raise UsageError()
    with Connection() as S:
        result, data = S.raw_select(folder)
        _debug(lambda: f" Result: {result}, {data}")
        if result != 'OK':
            print(f"Folder '{folder}' doesn't exist.")
        else:
            if state['folder'] == folder:
                state['folder'] = 'INBOX'
            S.select(state['folder'])
            result, data = S.raw_delete(folder)
    if result == 'OK':
        print(f"Folder '{folder}' deleted.")
    else:
        print(f"Failed to delete folder '{folder}': {data}")


@takesFolderArg
def rmm(folder, arglist):
    '''Usage: rmm [+folder] <messageset>

    ie: rmm +INBOX 1
    ie: rmm 1:5

    Remove the specified messages (or the current message if unspecified)
    from the specified folder (or the current folder if unspecified).
    '''
    folder = state['folder'] = folder or state['folder']
    msgset = msgset_from(arglist) or _cur_msg(folder)
    _checkMsgset(msgset)
    with Connection(folder) as S:
        data = S.search(None, msgset, errmsg="Problem with search:")
        _debug(lambda: f"data: {data!r}")
        S.store(msgset, '+FLAGS', '\\Deleted', errmsg="Problem setting deleted flag: ")
        S.expunge(errmsg="Problem expunging deleted messages: ")
        print("Deleted.")
    if data and data[0]:
        first = data[0].split()[0]
        # TODO: fix this
        state[folder+'.cur'] = first


@takesFolderArg
def mr(folder, arglist):
    '''Usage: mr [+folder] <messageset>

    Mark the specified messages (or the current message if unspecified)
    from the specified folder (or the current folder if unspecified) as read.
    '''
    folder = state['folder'] = folder or state['folder']
    msgset = msgset_from(arglist) or _cur_msg(folder)
    _checkMsgset(msgset)
    with Connection(folder) as S:
        data = S.search(None, msgset, errmsg="Problem with search:")
        _debug(lambda: f"data: {data!r}")
        S.store(msgset, '+FLAGS', '\\Seen', errmsg="Problem setting read flag: ")
    if data[0]:
        first = data[0].split()[0]
        state[folder+'.cur'] = first


def _headers_from(msg):
    """ lines until a blank one """
    # return '\n'.join(itertools.takewhile(lambda x: x, msg.split("\r\n"))) + "\n"
    result = ""
    for line in msg.split("\r\n"):
        if line:
            result += line + "\n"
        else:
            return result
    return result


def _show(folder, msgset):
    '''common code for show/next/prev
       return the number of the last message shown, or None
    '''
    import email
    from email.policy import default

    enable_pager()
    outputfunc = print
    with Connection(folder) as S:
        msglist = S.search(None, msgset, errmsg="Problem with search:")
        _debug(lambda: f"SEARCH returned: {msglist!r}")
        last = None
        nums = tostr(msglist[0])
        for num in nums.split():
            result, data = S.raw_fetch(num, '(RFC822)')
            _debug(lambda: f"data for {num!r} is: {msglist!r}")
            outputfunc(f"(Message {folder}:{num})\n")
            msgbytes = data[0][1]
            # outputfunc(_headers_from(msgbytes.decode()))
            msg = email.message_from_bytes(msgbytes, policy=default)
            outputfunc(msg.as_string(unixfrom=True))
            # outputfunc(msg.get_body(preferencelist=('related', 'plain', 'html')))
            # for part in msg.walk():
            #     _debug(lambda: "PART %s:" % part.get_content_type())
            #     msg = part.get_payload(0).decode()
            #     outputfunc(msg)
            last = int(num)
    return last


@takesFolderArg
def show(folder, arglist):
    '''Usage:  show [<messageset>]

    Show the specified messages, or the current message if none specified
    '''
    folder = state['folder'] = folder if folder else state['folder']
    msgset = msgset_from(arglist) or _cur_msg(folder)
    _checkMsgset(msgset)
    shown = _show(folder, msgset)
    if shown:
        state[folder+'.cur'] = shown


@takesFolderArg
def next(folder, arglist):
    '''Usage: next [+<folder>]

    Show the next message in the specified folder, or the current folder if not specified
    '''
    # TODO: needs better bounds checking
    folder = state['folder'] = folder or state['folder']
    try:
        cur = int(state[folder+'.cur']) + 1
    except KeyError:
        cur = 1
    shown = _show(folder, str(cur))
    if shown:
        state[folder+'.cur'] = shown


@takesFolderArg
def prev(folder, arglist):
    '''Usage: prev [+<folder>]
    Show the previous message in the specified folder, or the current folder if not specified
    '''
    # TODO: needs better bounds checking
    folder = state['folder'] = folder or state['folder']
    try:
        cur = int(state[folder+'.cur']) - 1
    except KeyError:
        cur = 1
    shown = _show(folder, str(cur))
    if shown:
        state[folder+'.cur'] = shown


@takesFolderArg
def scan(folder, arglist):
    '''Usage: scan [+<folder>] [messageset]
    Show a list of the specified messages (or all if unspecified)
    in the specified folder, or the current folder if not specified
    '''

    def summarize_envelope(env_date, env_from, env_sender, flags):
        _debug(lambda: f"env_date={env_date}\nenv_from={env_from}\nenv_sender={env_sender}\nflags={flags}")
        try:
            fmt = "%d %b %Y %H:%M:%S"
            if ',' in env_date:
                fmt = "%a, " + fmt
            env_date = ' '.join(str(env_date).split()[:len(fmt.split())])
            dt = time.strptime(env_date, fmt)
            outtime = time.strftime("%m/%d", dt)
        except Exception as e:
            _debug(lambda: f"strptime exception: {e!r}")
            outtime = "??/??"
        if isinstance(env_from, list):
            outfrom = str(env_from[0][0])
            if outfrom == 'NIL':
                outfrom = "%s@%s" % (env_from[0][2], env_from[0][3])
        else:
            outfrom = "<Unknown>"
        if cur == num:
            status = '>'
        elif 'Answered' in flags:
            status = 'r'
        elif 'Seen' in flags:
            status = ' '
        elif 'Recent' in flags:
            status = 'N'
        else:
            status = 'O'
        return f'{num:4} {status} {outtime} {outfrom[:18]:<18} '

    enable_pager()
    subjlen = 47
    if len(arglist) > 99:
        raise UsageError()
    # find any folder refs and put together the msgset string
    folder = state['folder'] = folder or state['folder']
    msgset = msgset_from(arglist) or "1:*"
    _checkMsgset(msgset)
    with Connection(folder) as S:
        data = S.fetch(msgset, '(ENVELOPE FLAGS)', errmsg="Problem with fetch:" )
        # take out fake/bad hits
        data = [tostr(hit) for hit in data if hit and b' ' in hit]
        if data == [] or data[0] is None:
            print("No messages.")
            sys.exit(0)
        try:
            cur = string.atoi(state[folder+'.cur'])
        except:
            cur = None
        for hit in data:
            _debug(lambda: f'hit={hit}')
            num, e = hit.split(' ', 1)
            num = int(num)
            _debug(lambda: f'e={e}')
            e = readsexpr(e)
            env_date, env_subj, env_from, env_sender = e[1][:4]
            _debug(lambda: f'env_subj={env_subj}')
            flags = [str(f) for f in e[3]]

            outenv = summarize_envelope(env_date, env_from, env_sender, flags)
            outsubj = "<no subject>" if str(env_subj) == "NIL" else str(env_subj)
            print(outenv + outsubj[:subjlen])


def debug(args):
    global _debug
    _debug = _debug_stdout
    _dispatch([sys.argv[0]]+args)


def help(args):
    '''Usage: help <command>
    Shows help on the specified command.
    '''

    if len(args) < 1:
        print(help.__doc__)
        print(f"Valid commands: {CommandList}")
        sys.exit(0)
    cmd = args[0]
    cmdfunc = Commands.get(cmd, None)
    print(f"Help on {cmd}:\n")
    print(cmdfunc.__doc__)


Commands = {'folders': folders,
            'folder': folder,
            'debug': debug,
            'pick': pick,
            'refile': refile,
            'rmf': rmf,
            'rmm': rmm,
            'scan': scan,
            'search': pick,
            'show': show,
            'next': next,
            'prev': prev,
            'comp': comp,
            'repl': repl,
            'help': help,
            'mr': mr,
           }

CommandList = ', '.join(sorted(Commands.keys()))


def _dispatch(args):

    _debug(lambda: f"args={args}")
    if len(args) <= 1:
        print(f"Must specify a command.  Valid ones: {CommandList}")
        return
    cmd = args[1]
    _debug(lambda: f"cmd={cmd}")
    cmdargs = args[2:]
    _debug(lambda: f"cmdargs={cmdargs}")
    _debug(lambda: f"Commands={Commands}")
    cmdfunc = Commands.get(cmd, None)
    if not cmdfunc:
        print(f"Unknown command {cmd}.  Valid ones: {CommandList}")
        return
    _debug(lambda: f"cmdfunc={cmdfunc}")
    try:
        cmdfunc(cmdargs)
    except IOError:
        pass
    except UsageError:
        print(cmdfunc.__doc__)
        sys.exit(1)
    config.write()
    state.write()


def cmd_main():
    # dispatch on program name instead of args[1]
    try:
        cmd = Path(sys.argv[0]).name
        args = ['mhi', cmd] + sys.argv[1:]
        _dispatch(args)
    except KeyboardInterrupt:
        print("Interrupted.")


def main():
    # main program
    try:
        _dispatch(sys.argv)
    except KeyboardInterrupt:
        print("Interrupted.")

