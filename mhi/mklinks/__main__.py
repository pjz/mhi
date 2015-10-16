"""A script to make convenience links for all the MHI commands
"""

import os
import sys
from distutils.spawn import find_executable as which

from .. import Commands


if len(sys.argv) < 2:
    print("""Usage: %s <destdir> [mhWrap path]
          destdir - required: a destination directory for the links
          mhiWrap path - optional: path to mhiWrap.  If unspecified, tries to find it on $PATH
""")
    sys.exit(1)

destdir = sys.argv[1]

if len(sys.argv) > 2:
    mhiWrap = sys.argv[2]
else:
    mhiWrap = which('mhiWrap')
    if mhiWrap == 'mhiWrap':
        print("Can't find mhiWrap on your path; you'll have to specify it.")
        sys.exit(1)

# make the dir if it doesn't exist ; remove regular files there if needed
if not os.path.isdir(destdir):
    if os.path.exists(destdir):
        os.remove(destdir)
    else:
        os.makedirs(destdir)

if not os.path.isdir(destdir):
    print("Problem making the directory %r" % destdir)
    sys.exit(1)

for name in Commands:
    fullname = os.path.join(destdir, name)
    os.symlink(mhiWrap, fullname)

