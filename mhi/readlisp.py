"""
Ole Martin Bjorndalen <olemb@stud.cs.uit.no>
2006-08-12
"""

import types
from io import StringIO

EOF = ''
END_PAREN = ')'


class CharFile:
    def __init__(self, file):
        self.file = file
        self.c = ''

    def getchar(self):
        if self.c:
            c = self.c
            self.c = ''
            return c
        else:
            self.c = ''
            c = self.file.read(1)
            # print [c]
            return c

    def ungetchar(self, c):
        self.c = c


class LispSymbol:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'LispSymbol(%s)' % repr(self.name)

    def __str__(self):
        return self.name


class LispReader:
    def __init__(self, file):
        self.file = CharFile(file)
        self.whitespace = ' \r\n\t'
        self.atom_end = self.whitespace + '()"|;'

    def _skip_whitespace(self):
        """Read until next non-whitespace or EOF"""
        while 1:
            c = self.file.getchar()
            if c == EOF or c not in self.whitespace:
                self.file.ungetchar(c)
                return

    def _skip_comment(self):
        """Read until EOL or EOF"""
        while 1:
            c = self.file.getchar()
            if c == '\n' or c == EOF:
                return

    def _parse_atom(self, atom):
        """Parse an atom and return and integer, a float or a symbol"""
        try:
            return int(atom)
        except ValueError:
            try:
                return float(atom)
            except ValueError:
                return LispSymbol(atom)

    def _read_atom(self):
        """Read a symbol or number"""
        atom = ''

        while 1:
            c = self.file.getchar()
            if c in self.atom_end or c == EOF:
                self.file.ungetchar(c)
                break
            atom += c

        return self._parse_atom(atom)

    def _read_string(self):
        string = ''

        while 1:
            c = self.file.getchar()

            if c == '':
                raise EOFError('Missing end quote for string')
            elif c == '"':
                return string
            elif c == '\\':
                c = self.file.getchar()
                if c == '':
                    raise EOFError('EOF after escape sequence')
                else:
                    string += c
            else:
                string += c

    def _read_list(self):
        items = []
        while 1:
            item = self._read_expr()
            if item is END_PAREN:
                break
            else:
                items.append(item)
        return items

    def _read_expr(self):
        while 1:
            self._skip_whitespace()

            c = self.file.getchar()

            if c == EOF:
                raise EOFError('End of LISP stream')
            elif c == ';':
                self._skip_comment()
            elif c == '(':
                return self._read_list()
            elif c == ')':
                return END_PAREN
            elif c == '"':
                return self._read_string()
            # elif c == '|':
            #    return self.read_quoted_symbol()
            else:
                self.file.ungetchar(c)
                return self._read_atom()

    def __iter__(self):
        while 1:
            try:
                yield self._read_expr()
            except EOFError:
                return


def writelisp(obj):
    """Convert a python object into an equivalent lisp expression."""

    if isinstance(obj, list):
        return '(%s)' % ' '.join(map(writelisp, obj))
    elif isinstance(obj, str):
        out = '"'
        for c in obj:
            if c in '\\"':
                out += '\\'
            out += c
        out += '"'
        return out
    elif isinstance(obj, int):
        return str(obj)
    elif isinstance(obj, complex):
        return '#C(%s %s)' % (obj.real, obj.imag)
    elif obj is None:
        return 'nil'
    else:
        return repr(obj)


def readlisp(text):
    """Read the first lisp expression in the string"""
    return LispReader(StringIO(text))._read_expr()


if __name__ == '__main__':
    p = LispReader(open('test.lisp'))
    print(repr(p._read_expr()))
