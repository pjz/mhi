# -*- coding: utf-8 -*-


"""Imaplib IMAP4_SSL mocking class
from https://github.com/Gentux/imap-cli/
"""


from builtins import bytes

import mock


example_email_content_unicode = '\r\n'.join([
    'From: exampleFrom <example@from.org>',
    'Date: Tue, 03 Jan 1989 09:42:34 +0200',
    'Subject: Mocking IMAP Protocols',
    'To: exampleTo <example@to.org>',
    'MIME-Version: 1.0',
    'Content-Type: text/html;\r\n\tcharset="windows-1252"',
    'Content-Transfer-Encoding: quoted-printable',
    '',
    'EMAIL BODY CONTENT',
])
example_email_content = bytes(example_email_content_unicode, 'utf-8')


class ImapConnectionMock(mock.Mock):
    fail = False
    error = False
    state = None

    def fetch(self, mails_id_set, request):
        flag_str = ""
        if request.find('FLAG') >= 0:
            flag_str = 'FLAGS (\\Seen NonJunk) '
        uid_str = ""
        if self.error is True:
            uid_str = 'UD 1 '
        elif request.find('UID') >= 0:
            uid_str = 'UID 1 '

        imap_header = bytes(
            '1 ({uid_str}{flag_str}BODY[HEADER] {{1621}}'.format(
                flag_str=flag_str,
                uid_str=uid_str),
            'utf-8')
        return ('OK', [(imap_header, example_email_content, b')')])

    def store(self, mails_id_set, request, flags):
        flags = ['\\\\Answered', '\\\\Seen', 'NonJunk']
        if '+FLAGS' in request:
            flags.append('testFlag')
        return ('OK', ['1 (UID 1 FLAGS ({}))'.format(' '.join(flags))])

    def list(self, *args):
        wrong_chars_mailbox = bytes(
            ' '.join([
                '(\\HasNoChildren)',
                '"."',
                '"&A5Q-i&A8A-ect&API-r&AP8-_&APEA5A-m&AOk-"']),
            'utf-8')
        if self.fail is True:
            return ('OK', [
                wrong_chars_mailbox,
                bytes('(\\HasNoChildren) "." "INBOX"', 'utf-8')])
        return ('OK', [
            wrong_chars_mailbox,
            bytes('(\\HasNoChildren) "." "INBOX"', 'utf-8')])

    def login(self, *args):
        return ('OK', ['Logged in'])

    def logout(self, *args):
        self.state = 'LOGOUT'

    def select(self, folder, *args):
        if folder not in ['INBOX', 'Test', 'Δiπectòrÿ_ñämé']:
            self.state = 'LOGOUT'
            return ('NO', None)
        self.state = 'SELECTED'
        return ('OK', ['1'])

    def search(self, *args):
        return ('OK', [bytes('1', 'utf-8')])

    def status(self, *args):
        if self.fail is True:
            return ('NO', None)
        if self.error is True:
            return ('OK', [('"&A5Q-i&A8A-ect&API-r&AP8-_&APEA5A-m&AOk-" '
                            '((MESSAGES 1 RECENT 1 UNSEEN 0)')])
        return ('OK', [('"&A5Q-i&A8A-ect&API-r&AP8-_&APEA5A-m&AOk-" '
                        '(MESSAGES 1 RECENT 1 UNSEEN 0)')])

    def uid(self, command, *args):
        command_upper = command.upper()
        if command_upper == 'FETCH':
            return self.fetch(*args)
        if command_upper == 'SEARCH':
            return self.search(*args)
        if command_upper == 'STORE':
            return self.store(*args)
        if command_upper == 'THREAD':
            return self.thread(*args)

    def thread(self, *args):
        return ('OK', [b'((1)(2))(3 4)'])
