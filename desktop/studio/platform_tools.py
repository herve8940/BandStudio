"""Executable paths shared by the native Mac host and the portable Windows build."""
import os
from pathlib import Path
import sys


def executable(engine,name):
    return Path(engine)/'import-tools'/(name+('.exe' if os.name=='nt' else ''))


def python_for(engine,environment='.venv'):
    engine=Path(engine)
    target=engine/environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if target.is_file():return target
    bundled=engine/'python/python.exe'
    if os.name=='nt' and environment in ('.venv','.venv-import') and bundled.is_file():return bundled
    return target


def creation_flags():
    return 0x08000000 if os.name=='nt' else 0
