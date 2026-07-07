"""Precompile site-packages bytecode into a pycache-prefix tree.

The Vercel bundler vendors site-packages to /var/task/_vendor but strips
__pycache__ dirs, and /var/task is read-only so CPython can't write them back.
Instead we build the tree CPython expects when sys.pycache_prefix is set:

    {prefix}/var/task/_vendor/<pkg>/<mod>.{cache_tag}.pyc

main.py sets sys.pycache_prefix = "/var/task/pycache" at runtime.

UNCHECKED_HASH invalidation makes the runtime trust the .pyc blindly (no
source mtime/size validation), which is correct for an immutable deployment.

Run with the deployment venv's python so cache_tag/bytecode match the runtime.
"""

import glob
import os
import py_compile
import sys

VENDOR_RUNTIME = "/var/task/_vendor"  # where the builder vendors site-packages

sites = glob.glob(".vercel/python/.venv/lib/python3.*/site-packages")
if not sites:
    sys.exit("mkpyc: no site-packages found under .vercel/python/.venv")
site = sites[0]

tag = sys.implementation.cache_tag  # e.g. cpython-312
dest_root = os.path.join("pycache", VENDOR_RUNTIME.lstrip(os.sep))

written = failed = 0
for root, dirs, files in os.walk(site):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for name in files:
        if not name.endswith(".py"):
            continue
        src = os.path.join(root, name)
        rel = os.path.relpath(src, site)
        cfile = os.path.join(dest_root, os.path.splitext(rel)[0] + f".{tag}.pyc")
        os.makedirs(os.path.dirname(cfile), exist_ok=True)
        try:
            py_compile.compile(
                src,
                cfile=cfile,
                quiet=2,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            written += 1
        except Exception:
            failed += 1  # some vendored files intentionally don't compile

print(f"mkpyc: wrote {written} pyc files to {dest_root} (tag={tag}, {failed} skipped)")
