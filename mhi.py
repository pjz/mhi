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
import string
import os.path
import imaplib
import StringIO
from configobj import ConfigObj

cfgdir = os.environ.get('HOME','')
config = ConfigObj(infile="%s/.mhirc" % cfgdir, create_empty=True)
state = ConfigObj(infile="%s/.mhistate" % cfgdir, create_empty=True)
Debug = 0

def _debug_noop(*args):
    pass

def _debug_stdout(arg):
    f = arg
    if type(arg) == type(''):
        f = lambda : arg
    print("DEBUG: ", f())

_debug = _debug_noop

def sexpr_readsexpr(s):
    import sexpr
    return sexpr.SexprParser(StringIO.StringIO(s)).parse()    

def readlisp_readsexpr(s):
    import readlisp
    return readlisp.readlisp(s)

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

      ANSWERED       Messages with the \Answered flag set.

      BCC <string>   Messages that contain the specified string in the
                     envelope structure's BCC field.

      BEFORE <date>  Messages whose internal date is earlier than the
                     specified date.

      BODY <string>  Messages that contain the specified string in the
                     body of the message.

      CC <string>    Messages that contain the specified string in the
                     envelope structure's CC field.

      DELETED        Messages with the \Deleted flag set.

      DRAFT          Messages with the \Draft flag set.

      FLAGGED        Messages with the \Flagged flag set.

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

      NEW            Messages that have the \Recent flag set but not the
                     \Seen flag.  This is functionally equivalent to
                     "(RECENT UNSEEN)".

      NOT <search-key>
                     Messages that do not match the specified search
                     key.

      OLD            Messages that do not have the \Recent flag set.
                     This is functionally equivalent to "NOT RECENT" (as
                     opposed to "NOT NEW").

      ON <date>      Messages whose internal date is within the
                     specified date.

      OR <search-key1> <search-key2>
                     Messages that match either search key.

      RECENT         Messages that have the \Recent flag set.

      SEEN           Messages that have the \Seen flag set.

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

      UNANSWERED     Messages that do not have the \Answered flag set.

      UNDELETED      Messages that do not have the \Deleted flag set.

      UNDRAFT        Messages that do not have the \Draft flag set.

      UNFLAGGED      Messages that do not have the \Flagged flag set.

      UNKEYWORD <flag>
                     Messages that do not have the specified keyword
                     set.

      UNSEEN         Messages that do not have the \Seen flag set.

"""

class UsageError:
    pass

def _argFolder(args, default=None):
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
        folder = default
    elif folder.startswith('+'):
        # double leading + means ignore the folder prefix
        folder = folder[1:]
    else:
        prefix = config.get('folder_prefix','')
        folder = prefix + folder

    return folder, outargs

def takesFolderArg(f):
    def parseFolderArg(args):
        folder, outargs = _argFolder(args)
        return f(folder, outargs)
    return parseFolderArg

class Connection:
    def __init__(self):
        import urlparse
        schemes = { 'imap' : imaplib.IMAP4, 
                    'imaps': imaplib.IMAP4_SSL, 
                    'stream': imaplib.IMAP4_stream }
        scheme, netloc, path, _, _, _ = urlparse.urlparse(config['connection'])
        _debug(lambda : 'scheme: %s netloc: %s path: %s' % (scheme, netloc, path))
        if netloc:
            if '@' in netloc:
                userpass, hostport = netloc.rsplit('@', 1)
            else:
                userpass, hostport = netloc, 'localhost'
            if ':' in hostport:
                host, port = hostport.rsplit(':', 1)
            else:
                host = hostport
                port = "143"
                if scheme[-1] == 's':
                    port = "993"
            if ':' in userpass:
                user, passwd = userpass.split(':', 1)
            else:
                user, passwd = os.environ.get('USER',''), userpass
            _debug(lambda : "%s connection to %s : %s @ %s : %s" % (scheme, user, passwd, host, port))
            session = schemes[scheme](host, int(port))
            session.login(user, passwd)
        else:
            session = schemes[scheme](path)
        session.debug = 0 if _debug == _debug_noop else 4
        self.session = session

        def __enter__(self):
            return self

        def __exit__(self):
            self.session.close()
            self.session.logout()

        def __getattr__(self, name):
            raw = False
            if name.startswith('raw_'):
                raw = True
                name = name[4:]
            result = getattr(self.session, name)
            if result is None: raise AttributeError
            if raw: return result
            return die_on_error(result)

def die_on_error(f):
    def _die_on_err_wrapper(*args, **kwargs):
        msgstr = kwargs.get('errmsg', 'There was a problem:')
        del kwargs['errmsg']
        result, data = f(*args, **kwargs)
        if result != 'OK':
            print msgstr + ' ' + str(data)
            sys.exit(1)
        return data
    return _die_on_err_wrapper

def enable_pager():
    if sys.stdout.isatty():
       pager = os.environ.get('PAGER', None)
       if pager is None:
           for p in [ '/usr/bin/less', '/bin/more' ]:
               if os.path.exists(p):
                   pager = p
                   break
       if pager is not None:
           sys.stdout = os.popen(pager, 'w')

def _fixupMsgset(msgset):
    ''' Change some common symbols into an IMAP-style msgset:
        'cur' -> remembered folder current msg
        'prev' -> remembered folder current msg - 1
        'next' -> remembered folder current msg + 1
        'last' -> '*'
        '$' -> '*'
        '-' -> ':'
    '''
    cur = state.get(state['folder']+'.cur', None)
    if cur == 'None': cur = None
    if cur is not None:
        _debug(lambda: "cur is " + repr(cur))
        _debug(lambda: "type(cur) is %s" % repr(type(cur)))
        msgset = msgset.replace('cur', cur)
        # XXX: bounds-check these?
        msgset = msgset.replace('next', str(int(cur)+1))
        msgset = msgset.replace('prev', str(int(cur)-1))
    else:
        if any(True for dep in ["cur", "prev", "next"] if dep in msgset):
            print "No current message, so '%s' makes no sense." % msgset
            sys.exit(1)
    msgset = msgset.replace('-', ':')
    msgset = msgset.replace(' ', ',')
    msgset = msgset.replace('last', "*")
    msgset = msgset.replace('$', "*")
    return msgset 

def _checkMsgset(msgset):
    '''Stub to check that a specified string has the grammar of a msgset'''
    ## FIXME: need a better check that msgset is a valid imap messageset string
    # msgset = int | int:int | msgset,msgset
    # '1', '1:5', '1,2,3', '1,3:5' are all valid
    if len(msgset.strip('1234567890,:*')) != 0:
        print "%s isn't a valid messageset. Try again." % msgset
        sys.exit(1)

def tempFileName(*args,**kwargs):
    import tempfile
    f = tempfile.NamedTemporaryFile(*args,**kwargs)
    name = f.name
    f.close()
    return name

def _crlf_terminate(msgfile):
    ''' convenience function to turn a \n terminated file into a \r\n terminated file '''
    tfile = tempFileName(prefix="mhi")
    os.rename(msgfile,tfile)
    inf = file(tfile,"r")
    outf = file(msgfile,"w")
    for line in inf:
        if not line.endswith('\r\n'):
           line = line[:-1] # strip existing \n (or \r?)
           line += '\r\n'   # add new lineending
        outf.write(line)
    inf.close()
    outf.close()

def _edit(msgfile):
    ''' internal common code for comp/repl/dist/medit '''
    env = os.environ
    editor = env.get('VISUAL',env.get('EDITOR', 'editor'))
    try:
        fin = os.system("%s %s" % (editor, msgfile))
        if os.path.exists(msgfile):
            _crlf_terminate(msgfile)
    except Exception:
        return 1
    return fin

def _SMTPsend(msgfile):
    import smtplib
    import email
    ret = {'Unknown':'SMTP problem'}
    msg = email.message_from_file(file(msgfile,"r"))
    fromaddr = msg.get('From','')
    toaddrs = msg.get_all('To',[])
    _debug(lambda: "composing message from %s to %s" % (repr(fromaddr), repr(toaddrs)))
    server = smtplib.SMTP('localhost')
    #server.set_debuglevel(1)
    try:
        ret = server.sendmail(fromaddr, toaddrs, msg.as_string())
    except smtplib.SMTPRecipientsRefused:
        print "No valid recipients. Try again."
    except smtplib.SMTPHeloError:
        print "Error talking to SMTP server (No HELO)."
    except smtplib.SMTPSenderRefused:
        print "Error talking to SMTP server (Unacceptable FROM address)."
    except smtplib.SMTPDataError:
        print "Error talking to SMTP server (Data Error)."
    server.quit()
    for k in ret.keys():
        print "SMTP Error: %s: %s" % (k, ret[k])
    return len(ret.keys())

def _get_Messages(folder, msgset):
    with Connection() as S:
        S.select(folder, errmsg = "Problem changing folders:")
        msglist = S.search(None, msgset, errmsg = "Problem with search:")
        messages = []
        for num in msglist[0].split():
            result, data = S.fetch(num, '(RFC822)')
            messages.append((num, data))
    return messages

def _get_curMessage():
    folder = state['folder'] 
    try:
        msgset = state[folder+'.cur']
    except KeyError:
        print "Error: No current message selected."
        raise UsageError()
    _checkMsgset(msgset)
    return _get_Messages(folder, msgset)[0][1]

def _quoted_current(data, msg):
    result = ""
    for part in msg.walk():
        _debug(lambda: "PART %s:" % part.get_content_type())
        for line in part.get_payload(decode=True).split("\n"):
            result += "> " + line + "\n"
    return result 

def __header(data, msg, header):
    if header in msg:
        return msg[header]
    else:
        return "[[Missing %s header]]" % header

def _header_from(data, msg): return __header(data, msg, 'from')
def _header_date(data, msg): return __header(data, msg, 'date')
def _header_subject(data, msg): return __header(data, msg, 'subject')

def _header_from_name(data, msg):
    full = _header_from(data, msg)
    left = full.find("<")
    right = full.find(">")
    if left > -1 and right > -1:
        return full[:left] + full[right+1:]
    else:
        return full

macros = { 
    '###QUOTED###': _quoted_current,
    '###:FROM###':_header_from,
    '###:DATE###':_header_date,
    '###:SUBJECT###':_header_subject,
    '###:FROM.NAME###':_header_from_name,
}

def _template_update(msgfile):
    import email
    template = open(msgfile, 'r')
    templatetext = template.readlines()
    outfile = open(msgfile, "w")
    curdata = _get_curMessage()
    curmsg = email.message_from_string(curdata[0][1])
    for line in templatetext:
        replacements = 1
    	while replacements:
            replacements = 0
            for macro, impl in macros.items():
                if macro in line:
	            line = line.replace(macro, impl(curdata, curmsg))
                    replacements += 1
        outfile.write(line)
    outfile.close()


def comp(args):
    '''Usage: comp
    
    Compose a new message
    '''
    tmpfile = tempFileName(prefix="mhi-comp-")
    if config.get('comp_template', None):
       import shutil
       shutil.copyfile(config['comp_template'], tmpfile) 
    ret = _edit(tmpfile)
    if ret == 0:
        # edit succeeded, wasn't aborted or anything 
        errcount = _SMTPsend(tmpfile)
        if not errcount:
            os.unlink(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
        print "Session aborted."
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
        import shutil
        shutil.copyfile(config['repl_template'], tmpfile)
        _template_update(tmpfile)
    # TODO: put quoted contents of current message into tmpfile
    # TODO: put the author of the current message in the 'To:' field
    # TODO: swipe MH's -cc, etc syntax for specifying who to copy
    ret = _edit(tmpfile)
    if ret == 0:
        # edit succeeded, wasn't aborted or anything 
        errcount = _SMTPsend(tmpfile)
        if not errcount:
            os.unlink(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
        print "Session aborted."
        os.unlink(tmpfile)

def _selectOrCreate(S, folder):
    result, data = S.raw_select(folder)
    _debug(lambda: " Result: %s, %s " % (result, data))
    if result != 'OK':
        print "Folder '%s' doesn't exist.  Create it? " % folder,
        answer = sys.stdin.readline().strip().lower()
        if answer.startswith('y'):
            S.create(folder, errmsg = "Problem creating folder:")
            S.select(folder, errmsg = "Problem selecting newly created folder:")
        else:
            print("Nothing done. exiting.")
            sys.exit(1)
    return data

def folder_name(folder):
    prefix = config.get('folder_prefix',None)
    if prefix and folder.startswith(prefix):
        return folder[len(prefix):]
    return folder

@takesFolderArg
def folder(folder, arglist):
    '''Usage: folder [+<foldername>]

    Change folders / show current folder
    '''
    if arglist: raise UsageError()
    if folder is None: folder = state['folder']
    with Connection() as S:
        data = _selectOrCreate(S, folder)
    state['folder'] = folder
    # inbox+ has 64 messages  (1-64); cur=63; (others).
    cur = state.get(folder+'.cur', 'unset')
    print "Folder %s has %s messages, cur is %s." % (folder_name(folder), data[0], cur)

def folders(args):
    '''Usage: folders
    
    Show all folders
    '''
    enable_pager()
    HEADER = "FOLDER"
    with Connection() as S:
        result, flist = S.raw_list()
        _debug(lambda: " flist: %s " % repr(flist))
        stats = {}
        for fline in flist:
            f = str(readsexpr('('+fline+')')[2])
            _debug(lambda: " f: %s " % repr(f))
            result, data = S.raw_status(f, '(MESSAGES RECENT UNSEEN)')
            if result == 'OK':
                stats[f] = readsexpr('('+data[0]+')')[1]
    stats[HEADER] = [0, "# MESSAGES", 0, "RECENT", 0, "UNSEEN"]
    folderlist = [ key for key in stats.keys() if key != 'FOLDER' ]
    folderlist.sort()
    totalmsgs, totalnew = 0, 0
    for folder in [HEADER]+folderlist:
        _debug(lambda: " folder: %s " % repr(folder))
        iscur = [' ', '*'][ folder == state['folder'] ]
        foo = stats[folder]
        _debug(lambda: "  Stats: %s " % repr(foo))
        messages, recent, unseen = foo[1], foo[3], foo[5]
        cur = state.get(folder+'.cur', ['-', 'CUR'][ folder == HEADER ])
        print "%s%-20s %7s %7s %7s %7s" % (iscur, folder_name(folder), cur, messages, recent, unseen)
        if folder != HEADER:
            totalmsgs += int(messages)
            totalnew += int(unseen)
    print "TOTAL: %d messages (%d new) in %d folders" % (totalmsgs, totalnew, len(folderlist))

@takesFolderArg
def pick(folder, arglist):
    '''Usage: pick <search criteria> [+folder]

    Return a message-set that matches the search criteria.
    Criteria are based on the IMAP spec search string.
    A summary of the IMAP spec is available by calling 'pick' with --help as its only option.
    '''
    if not arglist: raise UsageError()
    if len(arglist) == 1 and arglist[0] == "--help":
        print PickDocs
        sys.exit(1)
    if folder is not None: state['folder'] = folder
    searchstr = '('+' '.join(arglist)+')'
    with Connection() as S:
        S.select(state['folder'], errmsg = "Problem changing to folder:")
        data = S.search(None, searchstr, errmsg = "Problem with search criteria:")
        _debug(lambda: "data: %s" % repr(data))
    data = [d for d in data if d != '']
    if data:
        print ','.join( m.split() for m in data )
    else:
        print "0"

def _cur_msg(folder):
    try:
        return state[folder+".cur"]
    except KeyError:
        print "Error: No message(s) selected."
        raise UsageError()


@takesFolderArg
def refile(destfolder, arglist):
    '''Usage: refile <messageset> +<folder>

    Moves a set of messages from the current folder to a new one.
    '''
    if not arglist: raise UsageError()
    if destfolder is None:
        print "Error: Destination folder must be specified."
        raise UsageError()
    srcfolder = state["folder"]
    msgset = _fixupMsgset(' '.join(arglist)) or _cur_msg(srcfolder)
    _checkMsgset(msgset)
    with Connection() as S:
        _selectOrCreate(S, destfolder)
        S.select(srcfolder, errmsg = "Problem changing folders:")
        S.copy(msgset, destfolder, errmsg = "Problem with copy:")
        data = S.search(None, msgset, errmsg = "Problem with search:")
        print("Refiling... ",)
        msgnums = data[0].split()
        for num in msgnums:
            S.raw_store(num, '+FLAGS', '\\Deleted')
            print ".", 
        S.expunge()
        print "%d messages refiled to '%s'." % (len(msgnums), destfolder)
    print "Done."

@takesFolderArg
def rmf(folder, arglist):
    '''Usage:  rmf +<foldername>
    remove a folder
    '''
    if not folder: raise UsageError()
    with Connection() as S:
        result, data = S.raw_select(folder)
        _debug(lambda: " Result: %s, %s " % (result, data))
        if result != 'OK':
            print "Folder '%s' doesn't exist." % folder
        else:
            if state['folder'] == folder:
                state['folder'] = 'INBOX'
            S.select(state['folder'], errmsg = "Problem changing folders:")
            result, data = S.raw_delete(folder)
    if result == 'OK':
        print "Folder '%s' deleted." % folder
    else:
        print "Failed to delete folder '%s': %s" % (folder, data)

@takesFolderArg
def rmm(folder, arglist):
    '''Usage: rmm [+folder] <messageset>

    ie: rmm +INBOX 1
    ie: rmm 1:5

    Remove the specified messages (or the current message if unspecified)  
    from the specified folder (or the current folder if unspecified).
    '''
    folder = state['folder'] = folder or state['folder']
    msgset = _fixupMsgset(' '.join(arglist)) or _cur_msg(folder)
    _checkMsgset(msgset)
    with Connection() as S:
        S.select(folder, errmsg = "Problem changing folders:")
        data = S.search(None, msgset, errmsg = "Problem with search:")
        S.store(msgset, '+FLAGS', '\\Deleted', errmsg = "Problem setting deleted flag: ")
        S.expunge(errmsg = "Problem expunging deleted messages: ")
        print "Deleted."
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
    msgset = _fixupMsgset(' '.join(arglist)) or _cur_msg(folder)
    _checkMsgset(msgset)
    with Connection() as S:
        S.select(folder, errmsg = "Problem changing folders:")
        data = S.search(None, msgset, errmsg = "Problem with search:")
        _debug(lambda: "data: %s" % repr(data))
        S.store(msgset, '+FLAGS', '\\Seen', errmsg = "Problem setting read flag: ")
    if data[0]:
        first = data[0].split()[0]
        state[folder+'.cur'] = first


def _headers_from(msg):
    result = ""
    for line in msg.split("\r\n"):
        if line:
            result += line + "\n"
        else:
            return result
    return result

def _msg_output(folder, msgset, outputfunc):
    import email
    with Connection() as S:
        S.select(folder, errmsg = "Problem changing folders:")
        msglist = S.search(None, msgset, errmsg = "Problem with search:")
        last = None
        for num in msglist[0].split():
            result, data = S.raw_fetch(num, '(RFC822)')
            outputfunc("(Message %s:%s)\n" % (folder, num))
            outputfunc(_headers_from(data[0][1]))
            msg = email.message_from_string(data[0][1])
            for part in msg.walk():
                _debug(lambda: "PART %s:" % part.get_content_type())
                outputfunc(part.get_payload(decode=True))
            last = num
    return last

def _show(folder, msgset):
    '''common code for show/next/prev'''
    import email
    enable_pager()
    messages = _get_Messages(folder, msgset)
    for num, data in messages:
        print "(Message %s:%s)\n" % (folder, num)
        print _headers_from(data[0][1])
        msg = email.message_from_string(data[0][1])
        for part in msg.walk():
            _debug(lambda: "PART %s:" % part.get_content_type())
            print part.get_payload(decode=True)
    return messages[-1][0]

@takesFolderArg
def show(folder, arglist):
    '''Usage:  show [<messageset>]

    Show the specified messages, or the current message if none specified
    '''
    folder = state['folder'] = folder or state['folder']
    msgset = _fixupMsgset(' '.join(arglist)) or _cur_msg(folder)
    _checkMsgset(msgset)
    state[folder+'.cur'] = _show(folder, msgset)

# TODO: needs better bounds checking
@takesFolderArg
def next(folder, arglist):
    '''Usage: next [+<folder>]

    Show the next message in the specified folder, or the current folder if not specified
    '''
    folder = state['folder'] = folder or state['folder']
    try:
        cur = int(state[folder+'.cur']) + 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))

# TODO: needs better bounds checking
@takesFolderArg
def prev(folder, arglist):
    '''Usage: prev [+<folder>]
    Show the previous message in the specified folder, or the current folder if not specified
    '''
    folder = state['folder'] = folder or state['folder']
    try:
        cur = int(state[folder+'.cur']) - 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))

@takesFolderArg
def scan(folder, arglist):
    '''Usage: scan [+<folder>] [messageset]
    Show a list of the specified messages (or all if unspecified)
    in the specified folder, or the current folder if not specified
    '''

    def summarize_envelope(env_date, env_from, env_sender, flags):
        _debug(lambda: "env_date: %s" % repr(env_date))
        _debug(lambda: "env_from: %s" % repr(env_from))
        _debug(lambda: "env_sender: %s" % repr(env_sender))
        _debug(lambda: "flags: %s" % repr(flags))
        try:
            fmt = "%d %b %Y %H:%M:%S"
            if ',' in env_date:
                fmt = "%a, " + fmt
            env_date = ' '.join(str(env_date).split()[:len(fmt.split())])
            dt = time.strptime(env_date, fmt)
            outtime = time.strftime("%m/%d", dt)
        except Exception, e:
            _debug(lambda: "strptime exception: " + repr(e))
            outtime = "??/??"
        if type(env_from) == type([]):
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
        return '%4s %s %s %-18s '% (num, status, outtime, outfrom[:18])

    enable_pager()
    subjlen = 47
    if len(arglist) > 99:
        raise UsageError()
    # find any folder refs and put together the msgset string
    folder = state['folder'] = folder or state['folder']
    state['folder'] = folder
    msgset = _fixupMsgset(' '.join(arglist)) or "1:*"
    _checkMsgset(msgset)
    with Connection() as S:
        S.select(folder, errmsg = "Problem changing to folder:" )
        data = S.fetch(msgset, '(ENVELOPE FLAGS)', errmsg = "Problem with fetch:" )
        # take out fake/bad hits
        data = [ hit for hit in data if hit and ' ' in hit ]
        if data == [] or data[0] is None:
            print "No messages."
            sys.exit(0)
        try:
            cur = string.atoi(state[folder+'.cur'])
        except:
            cur = None
        for hit in data:
            _debug(lambda: 'Hit: %s' % (repr(hit)))
            num, e = hit.split(' ',1)
            num = string.atoi(num)
            _debug(lambda: "e: %s" % repr(e))
            e = readsexpr(e)
            env_date, env_subj, env_from, env_sender = e[1][:4]
            _debug(lambda: "env_subj: %s" % repr(env_subj))
            flags = [str(f) for f in e[3]]

            outenv = summarize_envelope(env_date, env_from, env_sender, flags)
            outsubj = str(env_subj) if str(env_subj) != "NIL" else "<no subject>"
            print outenv + outsubj[:subjlen]


def debug(args):
    global _debug
    _debug = _debug_stdout
    _dispatch([sys.argv[0]]+args) 

def help(args):
    '''Usage: help <command>
    Shows help on the specified command.
    '''

    def _sort(foo):
        bar = foo
        bar.sort()
        return bar

    if len(args) < 1:
        print help.__doc__
        print "Valid commands: %s " % (', '.join(_sort(Commands.keys())))
        sys.exit(0)
    else:
        cmd = args[0]
        cmdfunc = Commands.get(cmd, None)
        print "Help on %s:\n" % cmd
        print cmdfunc.__doc__


Commands = { 'folders': folders,
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
             'mr': mr
           }


def _dispatch(args):

    def _sort(foo):
        bar = foo
        bar.sort()
        return bar

    _debug(lambda: "args: %s" % repr(args))
    if len(args) > 1:
        cmd = args[1]
        _debug(lambda: "cmd: %s" % cmd)
        cmdargs = args[2:]
        _debug(lambda: "cmdargs: %s" % cmdargs)
        _debug(lambda: "commands: %s" % Commands)
        cmdfunc = Commands.get(cmd,None)
        if cmdfunc:
            _debug(lambda: "cmdfunc: %s" % cmdfunc)
            try:
                cmdfunc(cmdargs)
            except IOError: pass
            except UsageError:
                print cmdfunc.__doc__
                sys.exit(1)
            config.write()
            state.write()
        else:        
            print "Unknown command %s.  Valid ones: %s " % (sys.argv[1], ', '.join(_sort(Commands.keys())))
    else:
        print "Must specify a command.  Valid ones: %s " % ', '.join(_sort(Commands.keys()))



# main program

if __name__ == '__main__':
    try:
        _dispatch(sys.argv)
    except KeyboardInterrupt:
        print "Interrupted."

