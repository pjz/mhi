#!/usr/bin/python
#
# Goal: MH-ish commands that will talk to an IMAP server
#
# Commands that work: folder, folders, scan, rmm, pick/search, rmf
#
# Commands to make work: show, next, prev, sort, comp, forw 
#
#   sort may just store a sort order to apply to output instead of
#   actually touching the mailboxes.
#
# some code taken from http://www.w3.org/2000/04/maillog2rdf/imap_sort.py
#

import os
import sys
import time
import string
import imaplib
from configobj import ConfigObj
from readlisp import readlisp

config = ConfigObj("/home/pj/.mhirc",create_empty=True )
state = ConfigObj("/home/pj/.mhistate",create_empty=True )
Debug = 0

def _debug(dstr):
    if Debug > 0:
        print "DEBUG: %s" % dstr

def _argFolder(args):
    folder = None
    outargs = []
    for a in args:
        if a[0] == '+' and len(a) > 1:
	    folder = a[1:]
	else:
	    outargs.append(a)
    return folder, outargs

def _connect():
    session = imaplib.IMAP4(config['server'],int(config['port']))
    session.debug = Debug
    session.login(config['user'], config['password'])
    return session

def _check_result(result, data, msgstr):
    if result != 'OK':
        print msgstr+' %s' % data
	sys.exit(1)

def _validMsgset(msgset):
    ## FIXME: check that msgset is a valid imap messageset string
    # '1', '1:5', '1,2,3', '1,3:5' are all valid
    return True


def folder(args):
    if not args:
        folder = state['folder']
    elif len(args) == 1:
        folder = args[0][1:]
    else:
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
        print "Current folder is now %s (%s messages)" % (folder, data[0])
    else:
        print "Failed to set folder to '%s': %s" % (folder, data)


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
        print "%s%-10s %10s %6s %6s" % (iscur, folder, messages, recent, unseen)
	if folder != 'FOLDER':
            totalmsgs += int(messages)
	    totalnew += int(unseen)
    print "TOTAL: %d messages (%d new) in %d folders" % (totalmsgs, totalnew, len(folderlist))


def pick(args):
    if not args:
        print "Usage: pick <search criteria>"
	print "    returns a message-set that matches search criteria"
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


def refile(args):
    if not args:
        print "Usage: refile <messageset> +<folder>"
	print "    returns a message-set that matches search criteria"
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
    if not _validMsgset(msgset):
        print "%s isn't a valid messageset. Try again." % msgset
	sys.exit(1)
    S = _connect()
    result, data = S.select(destfolder)
    if result != 'OK':
        print "Folder '%s' doesn't exist.  Create it? ",
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
        for num in data[0].split():
            S.store(num, '+FLAGS', '\\Deleted')
        S.expunge()
    else:
        print "Aborting refile: %s" % data
    S.close()
    S.logout()
    print "Done."


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


def rmm(args):
    if len(args) < 1:
        print "Usage: rmm [+folder] <messageset>"
	print "   ie: rmm +INBOX 1"
	print "   ie: rmm 1:5"
	sys.exit(1)
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    msgset = ' '.join(args)
    if not msgset:
        try:
            msgset = state[state['folder']+'.cur']
	except KeyError:
	    print "No current message selected."
	    sys.exit(1)
    if not _validMsgset(msgset):
        print "%s isn't a valid messageset. Try again." % msgset
	sys.exit(1)
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


def show(args):
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    msgset = ' '.join(args)
    if not msgset:
        try:
            msgset = state[state['folder']+'.cur']
	except KeyError:
	    print "No current message selected."
	    sys.exit(1)
    if not _validMsgset(msgset):
        print "%s isn't a valid messageset. Try again." % msgset
	sys.exit(1)
    S = _connect()
    result, data = S.select(state['folder'])
    _check_result(result, data, "Problem changing folders:")
    result, data = S.search(None, msgset)
    _check_result(result, data, "Problem with search:")
    last = None
    for num in data[0].split():
        result, data = S.fetch(num, '(RFC822)')
	print "(Message %s:%s)\n%s\n" % (state['folder'], num, data[0][1])
        last = num
    S.close()
    S.logout()
    state[state['folder']+'.cur'] = last


def scan(args):
    subjlen = 50
    if len(args) > 99:
        print "Usage: scan [+folder] [range]"
	sys.exit(1)
    # find any folder refs and put together the msgset string
    folder, arglist = _argFolder(args)
    if folder:
        state['folder'] = folder
    msgset = ' '.join(arglist)
    if not msgset:
        msgset = "1:*"
    if not _validMsgset(msgset):
        print "%s isn't a valid messageset. Try again." % msgset
	sys.exit(1)
    S = _connect()
    result, data = S.select(state['folder'])
    _check_result(result, data, "Problem changing to folder:" )
    # FIXME: check here that we changed into the folder correctly
    result, data = S.fetch(msgset, 'ENVELOPE')
    _debug('result: %s' % repr(result))
    _debug('data: %s' % repr(data))
    _check_result(result, data, "Problem with fetch:" )
    if data[0] is None:
        print "No messages."
	sys.exit(0)
    try:
        cur = string.atoi(state[state['folder']+'.cur'])
    except:
        cur = None
    for hit in data:
	_debug('Hit: %s' % (repr(hit)))
        num, e = hit.split(' ',1)
        num = string.atoi(num)
	e = readlisp(e)
        env_date, env_subject, env_from, env_sender = e[1][:4]
	_debug("env_date: %s" % repr(env_date))
	_debug("env_subject: %s" % repr(env_subject))
	_debug("env_from: %s" % repr(env_from))
	_debug("env_sender: %s" % repr(env_sender))
	try:
	    dt = time.strptime(' '.join(str(env_date).split()[:5]), "%a, %d %b %Y %H:%M:%S ")
	    outtime = time.strftime("%m/%d", dt)
	except:
	    outtime = "??/??"
        outfrom = str(env_from[0][0])
	if outfrom == 'NIL':
	    outfrom = "%s@%s" % (env_from[0][2], env_from[0][3])
	if len(outfrom) > 18: outfrom = outfrom[:18]
	outsubj = str(env_subject)
	if outsubj == 'NIL':
	    outsubj = "<no subject>"
	if len(outsubj) > subjlen:
	    outsubj = outsubj[:subjlen]
        if cur == num:
	    status = '+'
	else:
	    status = ' '
        outline = '%4s%s %s %-18s '% (num, status, outtime, outfrom)
	print outline + outsubj
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
           }


def _dispatch(args):

    def _sort(foo):
        bar = foo
        bar.sort()
        return bar

    try:
        _debug("args: %s" % repr(args))
        cmd = args[1]
        _debug("cmd: %s" % cmd)
        cmdargs = args[2:]
        _debug("cmdargs: %s" % cmdargs)
        _debug("commands: %s" % Commands)
        cmdfunc = Commands[cmd]
        _debug("cmdfunc: %s" % cmdfunc)
        cmdfunc(cmdargs)
        config.write()
        state.write()
    except IndexError:
        print "Must specify a command.  Valid ones: %s " % ', '.join(_sort(Commands.keys()))
    except KeyError:
        print "Unknown command %s.  Valid ones: %s " % (sys.argv[1], ', '.join(_sort(Commands.keys())))

# main program

_dispatch(sys.argv)
