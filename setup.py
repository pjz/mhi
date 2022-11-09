# bootstrap if we need to
try:
    import setuptools  # noqa
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()

from setuptools import setup, find_packages


def read_reqs(filename):
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                yield line


req_dev_packages = list(read_reqs("reqs/dev-requirements.in"))
req_packages = list(read_reqs("reqs/requirements.in"))

classifiers = [ 'Development Status :: 5 - Production/Stable'
              , 'Environment :: Console'
              , 'Intended Audience :: Developers'
              , 'Intended Audience :: End Users/Desktop'
              , 'Intended Audience :: System Administrators'
              , 'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)'
              , 'Natural Language :: English'
              , 'Operating System :: MacOS :: MacOS X'
              , 'Operating System :: Microsoft :: Windows'
              , 'Operating System :: POSIX'
              , 'Programming Language :: Python :: 3.8'
              , 'Programming Language :: Python :: Implementation :: CPython'
              , 'Topic :: Communications :: Email :: Email Clients (MUA)'
              ]

setup( author = 'Paul Jimenez'
     , author_email = 'pj@place.org'
     , classifiers = classifiers
     , description = 'MH for IMAP'
     , name = 'mhi'
     , url = 'http://github.com/pjz/mhi'
     , packages = find_packages()
     , entry_points = { 'console_scripts': [ 'mhi = mhi:main'
                                            ,'mhiWrap = mhi:cmd_main'
                                            ]}
     # there must be nothing on the following line after the = other than a string constant
     , version = '0.8.1'
     , install_requires = req_packages
     , zip_safe = False
     , extras_require = { 'dev': req_dev_packages }
      )

