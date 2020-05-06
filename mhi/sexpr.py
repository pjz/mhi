"""
$ProjectHeader: sexprmodule 0.2.1 Wed, 05 Apr 2000 23:33:53 -0600 nas $
originally from: http://arctrix.com/nas/python/
modified to understand \-escaped quotes instead of "" escaping  - pj 20060809
"""
import string

# tokens
[T_EOF, T_ERROR, T_SYMBOL, T_STRING,
 T_INTEGER, T_FLOAT, T_OPEN, T_CLOSE] = range(8)
# states
[S_START, S_SYMBOL, S_STRING, S_NUMBER] = range(4)

class SexprError(Exception): pass


class SexprParser:
    """An S-expression parser"""
    def __init__(self, input):
        self.line_no = 1
        self.input = input
        self.char = None

    def getc(self):
        if self.char is None:
            c = self.input.read(1)
            if c == '\n':
                self.line_no = self.line_no + 1
            return c
        t = self.char
        self.char = None
        return t

    def ungetc(self, c):
        self.char = c

    def convert_number(self, token):
        try:
            if '.' in token:
                return (T_FLOAT, float(token))
            else:
                return (T_INTEGER, int(token))
        except ValueError:
            return (T_ERROR, f"{self.line_no}: invalid number '{token}'")

    def get_token(self):
        token = []
        state = S_START
        while 1:
            c = self.getc()
            if state == S_START:
                # EOF
                if not c:
                    return (T_EOF, None)
                # whitespace
                elif c in ' \t\n':
                    continue
                # comments
                elif c == ';':
                    while c and (c != '\n'):
                        c = self.getc()
                elif c == '(':
                    return (T_OPEN, None)
                elif c == ')':
                    return (T_CLOSE, None)
                elif c == '"':
                    state = S_STRING
                elif c in '-0123456789.':
                    state = S_NUMBER
                    token.append(c)
                else:
                    state = S_SYMBOL
                    token.append(c)
            elif state == S_SYMBOL:
                if not c:
                    return (T_SYMBOL, ''.join(token))
                if c in ' \t\n;()':
                    self.ungetc(c)
                    return (T_SYMBOL, ''.join(token))
                else:
                    token.append(c)
            elif state == S_STRING:
                if not c:
                    return (T_ERROR, f'{self.line_no}: unexpected EOF inside string')
                elif c == '\\':
                    c = self.getc()
                    if c == '"':
                        token.append('"')
                    else:
                        self.ungetc(c)
                        token.append('\\')
                elif c == '"':
                    return (T_STRING, ''.join(token))
                else:
                    token.append(c)
            elif state == S_NUMBER:
                if not c:
                    return self.convert_number(''.join(token))
                if c in ' \t\n;()':
                    self.ungetc(c)
                    return self.convert_number(''.join(token))
                elif c in '0123456789.eE-':
                    token.append(c)
                else:
                    return (T_ERROR, f'{self.line_no}: invalid character "{c}" while reading integer' )

    def parse(self, t=None):
        if not t:
            (t, v) = self.get_token()
        if t == T_OPEN:
            l = []
            while 1:
                (t, v) = self.get_token()
                if t == T_CLOSE:
                    return l
                elif t == T_OPEN:
                    v = self.parse(t)
                    if v == None:
                        raise SexprError('%d: unexpected EOF' % self.line_no)
                elif t == T_ERROR:
                    raise SexprError(v)
                elif t == T_EOF:
                    raise SexprError('%d: EOF while inside list' % self.line_no)
                l.append(v)
        elif t == T_CLOSE:
            raise SexprError('%d: unexpected )' % self.line_no)
        elif t == T_EOF:
            return None
        elif t == T_ERROR:
            raise SexprError(v)
        else:
            return v

if __name__ == '__main__':
    import sys
    #import profile
    p = SexprParser(sys.stdin)
    #profile.run('p.parse()')
    while 1:
        e = p.parse()
        print(e)
        if not e:
            break
