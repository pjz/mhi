"""readlisp 0.1.1
Python <-> Lisp data conversion tools

The module is not 'from readlisp import *' safe (yet).

This is alpha software. Anything may change at this point.

7. June 2001
Ole Martin Bjorndalen
olemb@stud.cs.uit.no
http://www.cs.uit.no/~olemb/
http://www.cs.uit.no/~olemb/software/readlisp/readlisp.py
"""

import shlex
import StringIO
import types
import string

#__all__ = ['readlisp', 'writelisp', 'LispIO']

class ClosingParenException(Exception):
    pass

class Symbol:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name
    
    def __str__(self):
        return self.name

class LispIO:
    """Reads and writes lisp expressions from a filelike object"""

    def __init__(self, file, symbols=Symbol):
        """Create a new LispIO instance"""
        self.file = file
	self.lex = shlex.shlex(file)
	self.lex.posix=1

        if callable(symbols):
            self.make_symbol = symbols
        else:
            self.make_symbol = symbols.get  # Assume it's a dict

	self.lex.commenters = ';'
	self.lex.quotes = '"'
	self.lex.wordchars = self.lex.wordchars+'#.e+_'

    def read(self):
	"""Read an expression and return the equivalent python object"""
	token = self.lex.get_token()  # See if we can get a token
	if token:
	    self.lex.push_token(token)
	    return self._expression()
	else:
	    raise EOFError

    def write(self, obj):
        """Write a python object to the lisp stream"""
        self.file.write(writelisp(obj))  # Add newline?

    def _atom(self, token):
	if token[0] == '"':
	    return token[1:-1]  # Unquote the string
	else:
	    for convert in (int, long, float):
		try:
		    return convert(token)
		except ValueError:
		    pass
	    return self.make_symbol(token)  # None of the above

    def _list(self):
	list = []
	try:
	    while 1:
		list.append(self._expression())
	except ClosingParenException:
	    pass
	return list

    def _expression(self):
	token = self.lex.get_token()

	if token == '(':
	    return self._list()
	elif token == ')':
	    raise ClosingParenException, \
                  'Unexpected closing paren' # self.lex.lineno 
	elif token == '#C':
	    return apply(complex, self._expression())
	elif token == '#':            # Experimental array support
	    return self._expression()
	elif token == 'nil':
	    return None
	elif token == '':
	    raise EOFError, 'Missing closing paren'
	else:
	    return self._atom(token)
    
def readlisp(str, symbols=Symbol):
    """Convert a lisp expression into an equivalent python object"""
    if type(str) != type(''):
        raise ValueError, 'The first argument to readlisp() must be a string'
    return LispIO(StringIO.StringIO(str), symbols=symbols).read()

def writelisp(obj):  # ?
    """Convert a python object into an equivalent lisp expression."""

    if type(obj) is types.ListType:
	return '(%s)' % string.join(map(writelisp, obj), ' ')
    elif type(obj) is types.StringType:
        print '!!!'
	return '"%s"' % obj
    elif type(obj) is types.LongType:
        l = repr(obj)
        if l[-1] == 'L':
            l = l[:-1]
	return l
    elif type(obj) is types.ComplexType:
	return '#C(%s %s)' % (obj.real, obj.imag)
    elif obj == None:
	return 'nil'
    else:
	return repr(obj)

def lisp_socket(socket):
    """Return a LispIO instance bound to the socket"""
    return LispIO(socket.makefile('r+'))

if __name__ == '__main__':
    print 'These number types are supported'
    print readlisp('(42 3.14 3.4e16 #C(1 2) 111222111222111222)')
    print writelisp([42, 3.14, 3.4e16, (1+2j), 111222111222111222L])

    print

    print readlisp('42')
    print writelisp(42)
    
    print

    print 'So are nil<->None and strings'
    print readlisp('(nil "Hello python!")')
    print writelisp([None, 'Hello lisp!'])

    print

    print "Here's what happens to symbols"
    print readlisp('(+ (some symbols) (some more))')

    print

    print "And to quoted strings:"
    print "%s should have two elements." % readlisp('("a \\"quoted\\" string" "example")')
