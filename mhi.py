#!/usr/bin/python2.4
#
# Goal: MH-ish commands that will talk to an IMAP server
#
# Commands that work: folder, folders, scan, rmm, rmf, pick/search, help,
#                     debug, refile, show, next, prev
#
# Commands to make work: sort, comp, repl, dist, forw, anno, mr
#
# * sort should just store a sort order to apply to output instead of
#   actually touching the mailboxes.  This will affect the working of
#   anything that takes a msgset as well as scan, next, prev, and pick
#
# * mr should do a 'mark all read' on the current (or specified) folder
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

def _debug(dstr):
    if Debug > 0:
        print "DEBUG: %s" % dstr

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
        folder = default
    else:
        prefix = config.get('folder_prefix','')
        folder = prefix + folder
    return folder, outargs

def _connect():
    ''' Convenience connection creation function '''
    import urlparse
    schemes = { 'imap' : imaplib.IMAP4, 
                'imaps': imaplib.IMAP4_SSL, 
                'stream': imaplib.IMAP4_stream }
    scheme, netloc, path, _, _, _ = urlparse.urlparse(config['connection'])
    _debug('scheme: %s netloc: %s path: %s' % (scheme, netloc, path))
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
        _debug("%s connection to %s : %s @ %s : %s" % (scheme, user, passwd, host, port))
        session = schemes[scheme](host, int(port))
        session.login(user, passwd)
    else:
        session = schemes[scheme](path)
    session.debug = Debug
    return session

''' Convenience exit-on-error wrapper '''
def do_or_die(func, msgstr):
    result, data = func
    if result != 'OK':
        print msgstr+' ' + str(data)
        sys.exit(1)
    return data

''' Change some common symbols into an IMAP-style msgset '''
def _fixupMsgset(msgset):
    # s/cur/$cur/, s/last/$last/, s/prev/$prev/, s/next/$next/
    cur = state.get(state['folder']+'.cur', None)
    if cur == 'None': cur = None
    if cur is not None:
    	#print "DEBUG: cur is %s" % repr(cur)
    	#print "DEBUG: type(cur) is %s" % repr(type(cur))
        msgset = msgset.replace('cur', cur)
        # XXX: bounds-check these?
        msgset = msgset.replace('next', str(int(cur)+1))
        msgset = msgset.replace('prev', str(int(cur)-1))
    else:
        requiresCur = False
	for dep in ["cur", "prev", "next"]:
	    requiresCur = requiresCur or dep in msgset
        if requiresCur:
	    print "No current message, so '%s' makes no sense." % msgset
	    sys.exit(1)
    msgset = msgset.replace('-', ':')
    msgset = msgset.replace(' ', ',')
    msgset = msgset.replace('last', "*")
    msgset = msgset.replace('$', "*")
    return msgset 

'''Stub to check that a specified string has the grammar of a msgset'''
def _checkMsgset(msgset):
    ## FIXME: need a better check that msgset is a valid imap messageset string
    # msgset = int | int:int | msgset,msgset
    # '1', '1:5', '1,2,3', '1,3:5' are all valid
    if len(msgset.strip('1234567890,:*')) != 0:
        print "%s isn't a valid messageset. Try again." % msgset
        sys.exit(1)

def _crlf_terminate(msgfile):
    ''' convenience function to turn a \n terminated file into a \r\n terminated file '''
    tfile = os.tempnam()
    os.rename(msgfile,tfile)
    inf = file(tfile,"r")
    outf = file(msgfile,"w")
    for line in inf:
        if len(line) >= 2 and line[-2] != '\r' and line[-1] == '\n':
           line = line[:-1]+'\r\n'
           outf.write(line)
    inf.close()
    outf.close()

def _edit(msgfile):
    ''' internal common code for comp/repl/dist/medit '''
    env = os.environ
    editor = env.get('VISUAL',env.get('EDITOR', 'editor'))
    fin = os.system("%s %s" % (editor, msgfile))
    _crlf_terminate(msgfile)
    return fin

def _SMTPsend(msgfile):
    import smtplib
    import email
    ret = {'Unknown':'SMTP problem'}
    msg = email.message_from_file(file(msgfile,"r"))
    fromaddr = msg.get('From','')
    toaddrs = msg.get_all('To',[])
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


def comp(args):
    '''Usage: comp
    
    Compose a new message
    '''
    tmpfile = os.tempnam(None,'mhi-comp-')
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


def repl(args):
    '''Usage: repl
    
    Reply to the current message, quoting it
    '''
    tmpfile = os.tempnam(None,'mhi-repl-')
    # TODO: put quoted contents of current message into tmpfile
    ret = _edit(tmpfile)
    if ret == 0:
        # edit succeeded, wasn't aborted or anything 
        _SMTPsend(tmpfile)
        if not errcount:
            os.unlink(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
        print "Session aborted."
        os.unlink(tmpfile)

def _selectOrCreate(S, folder):
    result, data = S.select(folder)
    _debug(" Result: %s, %s " % (result, data))
    if result != 'OK':
        print "Folder '%s' doesn't exist.  Create it? " % folder,
        answer = sys.stdin.readline().strip().lower()
        if answer.startswith('y'):
	    do_or_die(S.create(folder), "Problem creating folder:")
            do_or_die(S.select(folder), "Problem selecting newly created folder:")
        else:
	    do_or_die(('',''), "Nothing done. exiting.")
    return data

def folder_name(folder):
    prefix = config.get('folder_prefix',None)
    if prefix and folder.startswith(prefix):
        return folder[len(prefix):]
    return folder

def folder(args):
    '''Usage: folder [+<foldername>]

    Change folders / show current folder
    '''
    folder, arglist = _argFolder(args, state['folder'])
    if arglist:
    	raise UsageError()
    S = _connect()
    data = _selectOrCreate(S, folder)
    S.close()
    S.logout()
    state['folder'] = folder
    # inbox+ has 64 messages  (1-64); cur=63; (others).
    cur = state.get(folder+'.cur', 'unset')
    print "Folder %s has %s messages, cur is %s." % (folder_name(folder), data[0], cur)

def folders(args):
    '''Usage: folders
    
    Show all folders
    '''
    HEADER = "FOLDER"
    S = _connect()
    result, flist = S.list()
    _debug(" flist: %s " % repr(flist))
    stats = {}
    for fline in flist:
        f = str(readsexpr('('+fline+')')[2])
        _debug(" f: %s " % repr(f))
	result, data = S.status(f, '(MESSAGES RECENT UNSEEN)')
	if result == 'OK':
            stats[f] = readsexpr('('+data[0]+')')[1]
    S.logout()
    stats[HEADER] = [0, "# MESSAGES", 0, "RECENT", 0, "UNSEEN"]
    folderlist = [ key for key in stats.keys() if key != 'FOLDER' ]
    folderlist.sort()
    totalmsgs, totalnew = 0, 0
    for folder in [HEADER]+folderlist:
        _debug(" folder: %s " % repr(folder))
        iscur = [' ', '*'][ folder == state['folder'] ]
        foo = stats[folder]
        _debug("  Stats: %s " % repr(foo))
        messages, recent, unseen = foo[1], foo[3], foo[5]
        cur = state.get(folder+'.cur', ['-', 'CUR'][ folder == HEADER ])
        print "%s%-20s %7s %7s %7s %7s" % (iscur, folder_name(folder), cur, messages, recent, unseen)
        if folder != HEADER:
            totalmsgs += int(messages)
            totalnew += int(unseen)
    print "TOTAL: %d messages (%d new) in %d folders" % (totalmsgs, totalnew, len(folderlist))


def pick(args):
    '''Usage: pick <search criteria> [+folder]

    Return a message-set that matches the search criteria.
    Criteria are based on the IMAP spec search string.
    A summary of the IMAP spec is available by calling 'pick' with --help as its only option.
    '''
    if not args:
    	raise UsageError()
    if len(args) == 1 and args[0] == "--help":
        print PickDocs
        sys.exit(1)
    state['folder'], arglist = _argFolder(args, state['folder'])
    searchstr = '('+' '.join(arglist)+')'
    S = _connect()
    do_or_die(S.select(state['folder']), "Problem changing to folder:")
    data = do_or_die(S.search(None, searchstr), "Problem with search criteria:")
    _debug("data: %s" % repr(data))
    S.close()
    S.logout()
    data = [d for d in data if d != '']
    if data:
        msglist = []
        for m in data:
            msglist += m.split()
        print ','.join(msglist)
    else:
        print "0"


def refile(args):
    '''Usage: refile <messageset> +<folder>

    Moves a set of messages from the current folder to a new one.
    '''
    if not args:
    	raise UsageError()
    destfolder, arglist = _argFolder(args)
    if destfolder is None:
        print "Error: Destination folder must be specified."
    	raise UsageError()
    srcfolder = state["folder"]
    msgset = _fixupMsgset(' '.join(arglist))
    if not msgset:
        try:
            msgset = state[srcfolder+".cur"]
        except KeyError:
            print "Error: No message(s) selected."
            raise UsageError()
    _checkMsgset(msgset)
    S = _connect()
    _selectOrCreate(S, destfolder)
    do_or_die(S.select(srcfolder), "Problem changing folders:")
    do_or_die(S.copy(msgset, destfolder), "Problem with copy:")
    data = do_or_die(S.search(None, msgset), "Problem with search:")
    print "Refiling... ",
    msgnums = data[0].split()
    for num in msgnums:
        S.store(num, '+FLAGS', '\\Deleted')
        print ".", 
    S.expunge()
    print "%d messages refiled to '%s'." % (len(msgnums), destfolder)
    S.close()
    S.logout()
    print "Done."

def rmf(args):
    '''Usage:  rmf +<foldername>
    remove a folder
    '''
    folder, arglist = _argFolder(args)
    if not folder:
    	raise UsageError()
    S = _connect()
    result, data = S.select(folder)
    _debug(" Result: %s, %s " % (result, data))
    if result != 'OK':
        print "Folder '%s' doesn't exist." % folder
    else:
    	if state['folder'] == folder:
	    state['folder'] = 'INBOX'
        do_or_die(S.select(state['folder']), "Problem changing folders:")
        result, data = S.delete(folder)
    S.close()
    S.logout()
    if result == 'OK':
        print "Folder '%s' deleted." % folder
    else:
        print "Failed to delete folder '%s': %s" % (folder, data)

def rmm(args):
    '''Usage: rmm [+folder] <messageset>

    ie: rmm +INBOX 1
    ie: rmm 1:5

    Remove the specified messages (or the current message if unspecified)  
    from the specified folder (or the current folder if unspecified).
    '''
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    msgset = _fixupMsgset(' '.join(arglist))
    if not msgset:
        try:
            msgset = state[folder+'.cur']
        except KeyError:
            print "Error: No current message selected."
            raise UsageError()
    _checkMsgset(msgset)
    S = _connect()
    do_or_die(S.select(folder), "Problem changing folders:")
    data = do_or_die(S.search(None, msgset), "Problem with search:")
    do_or_die(S.store(msgset, '+FLAGS', '\\Deleted'), "Problem setting deleted flag: ")
    do_or_die(S.expunge(), "Problem expunging deleted messages: ")
    print "Deleted."
    S.close()
    S.logout()
    first = data[0].split()[0]
    state[folder+'.cur'] = first

def mr(args):
    '''Usage: mr [+folder] <messageset>

    Mark the specified messages (or the current message if unspecified)
    from the specified folder (or the current folder if unspecified) as read.
    '''
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    msgset = _fixupMsgset(' '.join(arglist))
    if not msgset:
        try:
            msgset = state[folder+'.cur']
        except KeyError:
            print "Error: No current message selected."
            raise UsageError()
    _checkMsgset(msgset)
    S = _connect()
    do_or_die(S.select(folder), "Problem changing folders:")
    data = do_or_die(S.search(None, msgset), "Problem with search:")
    do_or_die(S.store(msgset, '+FLAGS', '\\Seen'), "Problem setting read flag: ")
    S.close()
    S.logout()
    first = data[0].split()[0]
    state[folder+'.cur'] = first



def _show(folder, msgset):
    '''common code for show/next/prev'''
    S = _connect()
    do_or_die(S.select(folder), "Problem changing folders:")
    data = do_or_die(S.search(None, msgset), "Problem with search:")
    last = None
    for num in data[0].split():
        result, data = S.fetch(num, '(RFC822)')
        print "(Message %s:%s)\n%s\n" % (folder, num, data[0][1])
        last = num
    S.close()
    S.logout()
    return last

def show(args):
    '''Usage:  show [<messageset>]

    Show the specified messages, or the current message if none specified
    '''
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    msgset = _fixupMsgset(' '.join(arglist))
    if not msgset:
        try:
            msgset = state[folder+'.cur']
        except KeyError:
            print "Error: No current message selected."
            raise UsageError()
    _checkMsgset(msgset)
    state[folder+'.cur'] = _show(folder, msgset)

# TODO: needs better bounds checking
def next(args):
    '''Usage: next [+<folder>]

    Show the next message in the specified folder, or the current folder if not specified
    '''
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    try:
        cur = int(state[folder+'.cur']) + 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))

# TODO: needs better bounds checking
def prev(args):
    '''Usage: prev [+<folder>]
    Show the previous message in the specified folder, or the current folder if not specified
    '''
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    try:
        cur = int(state[folder+'.cur']) - 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))

def scan(args):
    '''Usage: scan [+<folder>] [messageset]
    Show a list of the specified messages (or all if unspecified)
    in the specified folder, or the current folder if not specified
    '''
    subjlen = 47
    if len(args) > 99:
    	raise UsageError()
    # find any folder refs and put together the msgset string
    folder, arglist = _argFolder(args, state['folder'])
    state['folder'] = folder
    msgset = _fixupMsgset(' '.join(arglist))
    if not msgset:
        msgset = "1:*"
    _checkMsgset(msgset)
    S = _connect()
    do_or_die(S.select(folder), "Problem changing to folder:" )
    try:
        result, data = S.fetch(msgset, '(ENVELOPE FLAGS)')
    except: pass
    _debug('result: %s' % repr(result))
    _debug('data: %s' % repr(data))
    do_or_die([result, data], "Problem with fetch:" )
    # take out fake/ba hits
    data = [ hit for hit in data if hit and ' ' in hit ]
    if data == [] or data[0] is None:
        print "No messages."
        sys.exit(0)
    try:
        cur = string.atoi(state[folder+'.cur'])
    except:
        cur = None
    for hit in data:
        _debug('Hit: %s' % (repr(hit)))
        num, e = hit.split(' ',1)
        num = string.atoi(num)
        _debug("e: %s" % repr(e))
        e = readsexpr(e)
        env_date, env_subject, env_from, env_sender = e[1][:4]
        flags = [str(f) for f in e[3]]
        _debug("env_date: %s" % repr(env_date))
        _debug("env_subject: %s" % repr(env_subject))
        _debug("env_from: %s" % repr(env_from))
        _debug("env_sender: %s" % repr(env_sender))
        _debug("flags: %s" % repr(flags))
        try:
            dt = time.strptime(' '.join(str(env_date).split()[:5]), "%a, %d %b %Y %H:%M:%S ")
            outtime = time.strftime("%m/%d", dt)
        except:
            outtime = "??/??"
	if type(env_from) == type([]):
            outfrom = str(env_from[0][0])
            if outfrom == 'NIL':
                outfrom = "%s@%s" % (env_from[0][2], env_from[0][3])
	else:
	    outfrom = "<Unknown>"
        outsubj = str(env_subject)
        if outsubj == 'NIL':
            outsubj = "<no subject>"
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
        outline = '%4s %s %s %-18s '% (num, status, outtime, outfrom[:18])
        print outline + outsubj[:subjlen]
    S.close()
    S.logout()


def debug(args):
    global Debug
    Debug = 4    
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

    _debug("args: %s" % repr(args))
    if len(args) > 1:
        cmd = args[1]
        _debug("cmd: %s" % cmd)
        cmdargs = args[2:]
        _debug("cmdargs: %s" % cmdargs)
        _debug("commands: %s" % Commands)
        cmdfunc = Commands.get(cmd,None)
        if cmdfunc:
            _debug("cmdfunc: %s" % cmdfunc)
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
    if sys.stdout.isatty():
       pager = os.environ.get('PAGER', None)
       if pager is None:
           for p in [ '/usr/bin/less', '/bin/more' ]:
               if os.path.exists(p):
	           pager = p
		   break
       if pager is not None:
           sys.stdout = os.popen(pager, 'w')
    try:
        _dispatch(sys.argv)
    except KeyboardInterrupt:
        print "Interrupted."

