import os
import sys
from setuptools import setup, find_packages

if os.name == 'nt':
    share_dir = os.getenv('LOCALAPPDATA')
else:
    share_dir = os.getenv("SHAREDIR", "/usr/share")

if not share_dir:
    print('Failed to identify SHAREDIR, exiting.')
    sys.exit(1)

def read_readme() -> str:
    with open('README.md', 'r', encoding='utf-8') as f:
        return f.read()


setup(
    name='picpro',
    version='0.3.0',
    packages=find_packages(exclude=['tests', 'tests.*']),
    package_data={'picpro': ['py.typed']},
    install_requires=[
        'pyserial',
        'docopt',
        'intelhex'
    ],
    tests_require=[
        'tox'
    ],
    url='https://github.com/Salamek/picpro',
    license='LGPL-3.0 ',
    author='Adam Schubert',
    author_email='adam.schubert@sg1-game.net',
    description='picpro a kitsrus PIC CLI programmer',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    test_suite='tests',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Software Development',
    ],
    python_requires='>=3.6',
    project_urls={
        'Release notes': 'https://github.com/Salamek/picpro/releases',
    },
    entry_points={
        'console_scripts': [
            'picpro = picpro.__main__:main',
        ],
    },
    data_files=[
        (os.path.join(share_dir, 'picpro'), [
            'usr/share/picpro/chipdata.cid'
        ])
    ]
)
