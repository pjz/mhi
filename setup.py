# bootstrap if we need to
try:
        import setuptools  # noqa
except ImportError:
        from ez_setup import use_setuptools
        use_setuptools()

from setuptools import setup

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
              , 'Programming Language :: Python :: 2.7'
              , 'Programming Language :: Python :: Implementation :: CPython'
              , 'Topic :: Communications :: Email :: Email Clients (MUA)'
              ]

setup( author = 'Paul Jimenez'
     , author_email = 'pj@place.org'
     , classifiers = classifiers
     , description = 'MH for IMAP'
     , name = 'mhi'
     , url = 'http://github.com/pjz/mhi'
     , py_modules = [ 'distribute_setup', 'mhi' ]
     , entry_points = { 'console_scripts': [ 'mhi = mhi:main' ]}
     # there must be nothing on the following line after the = other than a string constant
     , version = '0.6'
     , zip_safe = False
      )

