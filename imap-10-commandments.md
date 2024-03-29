# Ten Commandments of How to Write an IMAP client
by Mark Crispin
(via [the web](https://web.archive.org/web/20061011003045/http://dovecot.org/client-commandments.txt))
(Markdown translation by Paul Jimenez)

I wrote this tongue-in-cheek, but there's a lot here that people who
build IMAP clients should take careful note. Most existing clients
violate at least one, generally several, of these commandments.
These are based on known user-visible problems that occur with various
commonly used clients. Put another way, behind each commandment is a
plethora of user (and server administrator) complaints caused by a
violator.

1. Thou shalt not assume that it is alright to open multiple IMAP
sessions selected on the same mailbox simultaneously, lest thou face
the righteous wrath of mail stores that doth not permit such access.
Instead, thou shalt labor mightily, even unto having to use thy brain
to thinketh the matter through, such that thy client use existing
sessions that are already open.

2. Thou shalt not abuse the STATUS command by using it to check for
new mail on a mailbox that you already have selected in an IMAP
session; for that session hath already told thou about new mail
without thy having to ask.

3. Thou shalt remember the 30 minute inactivity timeout, and remember
to speak to the IMAP server before that timeout expires. 
    * If thou useth the IDLE command, thou shalt send DONE from the IDLE before 29
minutes hath passed, and issue a new IDLE.
    * If thou maketh no use of IDLE, then thou shalt send NOOP every few minutes, and the server shalt tell you about new mail, and there will be much rejoicing in the land.

4. Thou shalt not assume that all names are both the name of a mailbox
and the name of a upper level of hierarchy that contains mailboxes;
lest thou face the righteous wrath of mail stores in which a mailbox
is a file and a level of hierarchy is a directory.
    * Thou shalt pay diligent attention to the \NoSelect and \NoInferiors flags, so that
your users may praise you with great praise.

5. Thou shalt learn and understand the unique features of IMAP, such
as the unsolicited data model, the strict ascending rule of UIDs, how
UIDs map to sequence numbers, the ENVELOPE and BODYSTRUCTURE
structures; so that thou may use the IMAP protocol effectively.
    * For a POP client hacked to babble IMAP protocol is still no more than a POP
client.

6. Thou shalt remember untagged data sent by the server, and when thou
needest data thou shalt consult your memory before asking the server.
For those who must analyze thy protocol transactions are weak of
stomach, and are likely to lose their recent meal should they see thou
repeatedly re-fetch static data.

7. Thou shalt labor with great effort to work within the IMAP
deleted/expunge model, even if thy own model is that of a trashcan;
for interoperability is paramount and a trashcan model can be done
entirely in the user interface.

8. Thou shalt not fear to open multiple IMAP sessions to the server;
but thou shalt use this technique with wisdom.
    * For verily it is true;
if thou doth desire to monitor continuously five mailboxes for new
mail, it is better to have five IMAP sessions continuously open on the
mailboxes.
    * It is generally not good to do a succession of five SELECT
or STATUS commands on a periodic basis; and it is truly wretched to
open and close five sessions to do a STATUS or SELECT on a periodic
basis.
    * The cost of opening and closing a session is great, especially
if that session is SSL/TLS protected; and the cost of a STATUS or
SELECT can also be great. By comparison, the cost of an open session
doing an IDLE or getting a NOOP every few minutes is small. Great
praise shall be given to thy wisdom in doing what is less costly
instead of "common sense."

9. Thou shalt not abuse subscriptions, for verily the LIST command is
the proper way to discover mailboxes on the server.
    * Thou shalt not
subscribe names to the user's subscription list without explicit
instructions from the user; nor shalt thou assume that only subscribed
names are valid.
    * Rather, thou shalt treat subscribed names as akin to
a bookmarks, or perhaps akin to how Windows shows the "My Documents"
folder -- a set of names that are separate from the hierarchy, for
they are such.

10. Thou shalt use the LIST "\*" wildcard only with great care.
    * If thou doth not fully comprehend the danger of "\*", thou shalt use only
"%" and forget about the existance of "\*".

Honor these commandments, and keep them holy in thy heart, so that thy
users shalt maximize their pleasure, and the server administrators
shalt sing thy praises and recommend thy work as a model for others to
emulate.


