#!/usr/bin/python
#
# Goal: MH-ish commands that will talk to an IMAP server
#
# Commands that work: folder, folders, scan, rmm, pick/search, rmf
#
# Commands to make work: sort, comp, repl, dist, forw, anno
#
# * sort should just store a sort order to apply to output instead of
#   actually touching the mailboxes.  This will affect the working of
#   anything that takes a msgset as well as scan, next, prev, and pick
#
# minor bits of code taken from http://www.w3.org/2000/04/maillog2rdf/imap_sort.py
#

import os
import sys
import time
import string
import imaplib
from configobj import ConfigObj
from readlisp import readlisp

cfgdir=os.environ.get('HOME','')
config = ConfigObj("%s/.mhirc" % cfgdir,create_empty=True )
state = ConfigObj("%s/.mhistate" % cfgdir,create_empty=True )
Debug = 0

def _debug(dstr):
    if Debug > 0:
        print "DEBUG: %s" % dstr


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


'''
   parse the args into a folder-spec (denoted by a leading +, last of
   which is used if multiple are listed), and the rest of the args
'''
def _argFolder(args):
    folder = None
    outargs = []
    for a in args:
        if a[0] == '+' and len(a) > 1:
	    folder = a[1:]
	else:
	    outargs.append(a)
    return folder, outargs

''' Convenience connection creation function
    FIXME: handle IMAP-SSL
    FIXME: parse a url-ish imap[s]://server:port/ for the server/port/ssl spec
'''
def _connect():
    session = imaplib.IMAP4(config['server'],int(config['port']))
    session.debug = Debug
    session.login(config['user'], config['password'])
    return session

''' Convenience exit-on-error wrapper '''
def _check_result(result, data, msgstr):
    if result != 'OK':
        print msgstr+' %s' % data
	sys.exit(1)

def _fixupMsgset(msgset, last):
    # s/cur/$cur/, s/last/$last/, s/prev/$prev/, s/next/$next/
    cur= state[state['folder']+'.cur']
    msgset = msgset.replace('cur', cur)
    msgset = msgset.replace('last', last)
    # XXX: bounds-check these?
    msgset = msgset.replace('next', str(int(cur)+1))
    msgset = msgset.replace('prev', str(int(cur)-1))
    return msgset 

'''Stub to check that a specified string has the grammar of a msgset'''
def _checkMsgset(msgset):
    ## FIXME: need a better check that msgset is a valid imap messageset string
    # msgset = int | int:int | int,msgset
    # '1', '1:5', '1,2,3', '1,3:5' are all valid
    if len(msgset.strip('1234567890,:*')) != 0:
        print "%s isn't a valid messageset. Try again." % msgset
	sys.exit(1)

def _crlf_terminate(msgfile):
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

''' internal common code for comp/repl/dist/medit '''
def _edit(msgfile):
    env = os.environ
    editor = env.get('VISUAL',env.get('EDITOR', 'editor'))
    fin = os.system("%s %s" % (editor, msgfile))
    _crlf_terminate(msgfile)
    return fin

def _SMTPsend(msgfile):
    import smtplib
    import email
    ret = {'Unknown', 'SMTP problem'}
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

''' Work function: compose a new message '''
def comp(args):
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
    tmpfile = os.tempnam(None,'mhi-repl-')
    # put quoted contents of current message into tmpfile
    ret = _edit(tmpfile)
    if ret == 0:
        # edit succeeded, wasn't aborted or anything 
        _SMTPsend(tmpfile)
    else:
        # 'abort - throw away session, keep - save it for later'
	pass



''' Work function: changer folders / show current folder'''
def folder(args):
    folder, arglist = _argFolder(args)
    if not folder:
        folder = state['folder']
    if arglist:
        print "Usage:  folder +<foldername>"
	sys.exit(1)
    S = _connect()
    result, data = S.select(folder)
    _debug(" Result: %s, %s " % (result, data))
    if result != 'OK':
        print "Folder '%s' doesn't exist.  Create it? " % folder,
	answer = sys.stdin.readline().strip().lower()
	if len(answer) > 0 and answer[0] == 'y':
	    result, data = S.create(folder)
	    _check_result(result, data, "Problem creating folder:")
            result, data = S.select(folder)
    S.close()
    S.logout()
    if result == 'OK':
        state['folder'] = folder
	# inbox+ has 64 messages  (1-64); cur=63; (others).
	cur = state[folder+'.cur']
	if cur is None:
	   cur = 'unset'
        print "Folder %s has %s messages, cur is %s." % (folder, data[0], cur)
    else:
        print "Failed to set folder to '%s': %s" % (folder, data)


''' Work function: show all folder'''
def folders(args):
    S = _connect()
    result, data = S.list()
    flist = data
    _debug(" flist: %s " % repr(flist))
    stats = {}
    for fline in flist:
        f = str(readlisp('('+fline+')')[2])
        _debug(" f: %s " % repr(f))
        stats[f] = readlisp('('+S.status(f, '(MESSAGES RECENT UNSEEN)')[1][0]+')')[1]
    S.logout()
    stats["FOLDER"] = [0, "# MESSAGES", 0, "RECENT", 0, "UNSEEN"]
    folderlist = [ key for key in stats.keys() if key != 'FOLDER' ]
    folderlist.sort()
    totalmsgs, totalnew = 0, 0
    for folder in ['FOLDER']+folderlist:
        _debug(" folder: %s " % repr(folder))
	iscur = ' '
	if folder == state['folder']: iscur = '*'
        foo = stats[folder]
        _debug("  Stats: %s " % repr(foo))
        #_debug("Statsrl: %s " % repr(readlisp(foo)))
        messages, recent, unseen = foo[1], foo[3], foo[5]
	cur = state.get(folder+'.cur', None)
	if cur is None:
	    if folder == 'FOLDER': cur = 'CUR'
	    else: cur = '-'
        print "%s%-20s %7s %7s %7s %7s" % (iscur, folder, cur, messages, recent, unseen)
	if folder != 'FOLDER':
            totalmsgs += int(messages)
	    totalnew += int(unseen)
    print "TOTAL: %d messages (%d new) in %d folders" % (totalmsgs, totalnew, len(folderlist))

'''Work function: return a message-set that matches the search criteria.
   Criteria are based on the IMAP-spec search string.
'''
def pick(args):
    if not args:
        print "Usage: pick <search criteria>"
	print "    returns a message-set that matches search criteria"
        print PickDocs
        sys.exit(1)
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    searchstr = '('+' '.join(arglist)+')'
    S = _connect()
    result, data = S.select(state['folder'])
    _check_result(result, data, "Problem changing to folder:")
    result, data = S.search(None, searchstr)
    _check_result(result, data, "Problem with search criteria:")
    S.close()
    S.logout()
    msglist = []
    for m in data:
        msglist += m.split()
    print ','.join(msglist)


'''Work function:  moves a set of messages from the current folder to a new one.'''
def refile(args):
    if not args:
        print "Usage: refile <messageset> +<folder>"
	print "    moves a set of messages from the current folder to a new one."
        sys.exit(1)
    destfolder, arglist = _argFolder(args)
    if not destfolder:
        print "Destination folder must be specified."
	sys.exit(1)
    msgset = ' '.join(arglist)
    if not msgset:
        try:
            msgset = state[folder+".cur"]
	except KeyError:
	    print "No current message selected."
	    sys.exit(1)
    _checkMsgset(msgset)
    S = _connect()
    result, data = S.select(destfolder)
    if result != 'OK':
        print "Folder '%s' doesn't exist.  Create it? " % destfolder,
	answer = sys.stdin.readline().strip().lower()
	if len(answer) > 0 and answer[0] == 'y':
	    result, data = S.create(destfolder)
    if result == 'OK':
        result, data = S.select(state['folder'])
        _check_result(result, data, "Problem changing folders:")
        result, data = S.copy(msgset, destfolder)
        _check_result(result, data, "Problem with copy:")
        result, data = S.search(None, msgset)
        _check_result(result, data, "Problem with search:")
	print "Refiling... ",
	msgnums = data[0].split()
        for num in msgnums:
            S.store(num, '+FLAGS', '\\Deleted')
	    print ".", 
        S.expunge()
	print "%d messages refiled to '%s'." % (len(msgnums), destfolder)
        S.close()
    else:
        print "Aborting refile: %s" % data
    S.logout()
    print "Done."

'''Work function: remove a folder'''
def rmf(args):
    if len(args) == 1:
        folder = args[0][1:]
    else:
        print "Usage:  rmf +<foldername>"
	sys.exit(1)
    S = _connect()
    result, data = S.select(folder)
    _debug(" Result: %s, %s " % (result, data))
    if result != 'OK':
        print "Folder '%s' doesn't exist."
    else:
        result, data = S.delete(folder)
	_check_result(result, data, "Problem with delete: ")
    S.close()
    S.logout()
    if result == 'OK':
        state['folder'] = folder
        print "Current folder is now %s (%s messages)" % (folder, data[0])
    else:
        print "Failed to set folder to '%s': %s" % (folder, data)

'''Work function: remove messages from a folder'''
def rmm(args):
    if len(args) < 1:
        print "Usage: rmm [+folder] <messageset>"
	print "   ie: rmm +INBOX 1"
	print "   ie: rmm 1:5"
	sys.exit(1)
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    msgset = ' '.join(arglist)
    if not msgset:
        try:
            msgset = state[state['folder']+'.cur']
	except KeyError:
	    print "No current message selected."
	    sys.exit(1)
    _checkMsgset(msgset)
    S = _connect()
    result, data = S.select(state['folder'])
    _check_result(result, data, "Problem changing folders:")
    result, data = S.search(None, msgset)
    _check_result(result, data, "Problem with search:")
    first = None
    for num in data[0].split():
        if first is None: first = num
        S.store(num, '+FLAGS', '\\Deleted')
    S.expunge()
    print "Deleted."
    S.close()
    S.logout()
    state[state['folder']+'.cur'] = first

'''common code for show/next/prev'''
def _show(folder, msgset):
    S = _connect()
    result, data = S.select(folder)
    _check_result(result, data, "Problem changing folders:")
    result, data = S.search(None, msgset)
    _check_result(result, data, "Problem with search:")
    last = None
    for num in data[0].split():
        result, data = S.fetch(num, '(RFC822)')
	print "(Message %s:%s)\n%s\n" % (folder, num, data[0][1])
        last = num
    S.close()
    S.logout()
    return last


'''Work function: show the current message'''
def show(args):
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    folder = state['folder']
    msgset = ' '.join(arglist)
    if not msgset:
        try:
            msgset = state[folder+'.cur']
	except KeyError:
	    print "No current message selected."
	    sys.exit(1)
    _checkMsgset(msgset)
    state[folder+'.cur'] = _show(folder, msgset)

'''Work function: show the next message'''
# TODO: needs better bounds checking
def next(args):
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    folder = state['folder']
    try:
        cur = int(state[folder+'.cur']) + 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))


'''Work function: show the previous message'''
# TODO: needs better bounds checking
def prev(args):
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    folder = state['folder']
    try:
        cur = int(state[folder+'.cur']) - 1
    except KeyError:
        cur = 1
    state[folder+'.cur'] = _show(folder, str(cur))

'''Work function: show a list of messages'''
def scan(args):
    subjlen = 50
    if len(args) > 99:
        print "Usage: scan [+folder] [messageset]"
	sys.exit(1)
    # find any folder refs and put together the msgset string
    folder, arglist = _argFolder(args)
    if not folder:
        folder = state['folder']
    state['folder'] = folder
    msgset = ' '.join(arglist)
    if not msgset:
        msgset = "1:*"
    _checkMsgset(msgset)
    S = _connect()
    result, data = S.select(folder)
    _check_result(result, data, "Problem changing to folder:" )
    result, data = S.fetch(msgset, '(ENVELOPE FLAGS)')
    _debug('result: %s' % repr(result))
    _debug('data: %s' % repr(data))
    _check_result(result, data, "Problem with fetch:" )
    if data[0] is None:
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
	e = readlisp(e)
	#_debug("e: %s" % repr(e))
        env_date, env_subject, env_from, env_sender = e[1][:4]
	flags = [str(f) for f in e[3]]
	_debug("env_date: %s" % repr(env_date))
	_debug("env_subject: %s" % repr(env_subject))
	_debug("env_from: %s" % repr(env_from))
	_debug("env_sender: %s" % repr(env_sender))
	_debug("flags: %s" % repr(flags))
	#_debug("flags[0]: %s" % repr(flags[0]))
	try:
	    dt = time.strptime(' '.join(str(env_date).split()[:5]), "%a, %d %b %Y %H:%M:%S ")
	    outtime = time.strftime("%m/%d", dt)
	except:
	    outtime = "??/??"
        outfrom = str(env_from[0][0])
	if outfrom == 'NIL':
	    outfrom = "%s@%s" % (env_from[0][2], env_from[0][3])
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
            cmdfunc(cmdargs)
            config.write()
            state.write()
        else:        
            print "Unknown command %s.  Valid ones: %s " % (sys.argv[1], ', '.join(_sort(Commands.keys())))
    else:
        print "Must specify a command.  Valid ones: %s " % ', '.join(_sort(Commands.keys()))

# main program

_dispatch(sys.argv)
