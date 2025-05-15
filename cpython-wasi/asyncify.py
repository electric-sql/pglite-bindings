#!/usr/bin/env python3
import os
import sys
import time
import asyncio
import traceback

import code
import ast
import types

from pathlib import Path

aic = code.InteractiveConsole()
aic.compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT

if sys.orig_argv[-1].endswith('asyncify.py') or len(sys.orig_argv) < 3 or not os.path.isfile(sys.orig_argv[2]):
    print(f"""Usage:
    {sys.executable} asyncify.py async_script_name.py

""")
    raise SystemExit

print(f"""
{ sys.orig_argv = }
{ sys.argv = }
""")

sys.orig_argv[2] = os.path.realpath(sys.orig_argv[2])
aic.file = Path(sys.orig_argv[2])

sys.argv.pop(0)
sys.argv[0] = str(aic.file)

print(f"""
{ sys.orig_argv = }
{ sys.argv = }
""")


os.chdir(aic.file.parent)
print(f"changing to dir : {os.getcwd()}")
sys.path.insert(0, str(aic.file.parent))

with open(aic.file, 'r') as source:
    asyncified_codeobj  = aic.compile( source.read(), filename=aic.file.as_posix(), symbol="exec")

def print_exception(e, out=sys.stderr, **kw):
    kw.setdefault("file", out)
    traceback.print_exc(**kw)

sys.print_exception = print_exception
del print_exception, aic
asyncio.run( types.FunctionType(asyncified_codeobj, globals())())


