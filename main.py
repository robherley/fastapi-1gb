import os
import sys

# Must be set before any _vendor imports (including fastapi below): tells
# CPython to look for bytecode in our shipped pycache tree instead of the
# stripped-out __pycache__ dirs. See mkpyc.py.
if os.path.isdir("/var/task/pycache"):
    sys.pycache_prefix = "/var/task/pycache"

import resource
from time import perf_counter, process_time, time
from fastapi import FastAPI, HTTPException

BOOT = time()
BLOB_FILENAME = "blob.bin"
READ_CHUNK_SIZE = 4 * 1024 * 1024 # 4 MiB

app = FastAPI()

@app.middleware("http")
async def add_booted_at_header(request, call_next):
    response = await call_next(request)
    response.headers["X-Booted-At"] = repr(BOOT)
    return response

@app.get("/")
def ping():
    return {
        "booted_at": BOOT,
    }

def _proc_io() -> dict:
    # /proc/self/io: actual bytes fetched from the block layer (Linux only).
    try:
        with open("/proc/self/io") as f:
            return {k.strip(): int(v) for k, v in (line.split(":") for line in f)}
    except OSError:
        return {}

@app.get("/imports")
def imports():
    ru0 = resource.getrusage(resource.RUSAGE_SELF)
    io0 = _proc_io()
    wall0 = perf_counter()
    cpu0 = process_time()

    import sklearn
    import PIL
    import pandas
    import spacy
    import xgboost

    cpu = process_time() - cpu0
    wall = perf_counter() - wall0
    io1 = _proc_io()
    ru1 = resource.getrusage(resource.RUSAGE_SELF)

    disk_read_bytes = io1.get("read_bytes", 0) - io0.get("read_bytes", 0) if io1 else None
    io_wait = wall - cpu
    cached = getattr(sklearn, "__cached__", None)
    return {
        "bytecode_cache": {
            "pycache_prefix": sys.pycache_prefix,
            "sklearn_file": sklearn.__file__,
            "sklearn_cached": cached,
            "sklearn_cached_exists": bool(cached) and os.path.exists(cached),
        },
        "versions": {
            "sklearn": sklearn.__version__,
            "PIL": PIL.__version__,
            "pandas": pandas.__version__,
            "spacy": spacy.__version__,
            "xgboost": xgboost.__version__,
        },
        "timing": {
            "wall_seconds": wall,
            "cpu_seconds": cpu,  # user+sys, excludes blocking
            "io_wait_seconds": io_wait,  # wall - cpu ~= blocked on page faults / disk
            "cpu_fraction": (cpu / wall) if wall > 0 else None,
        },
        "faults": {
            "major_page_faults": ru1.ru_majflt - ru0.ru_majflt,  # each required disk I/O
            "minor_page_faults": ru1.ru_minflt - ru0.ru_minflt,  # RAM-only
            "block_input_ops": ru1.ru_inblock - ru0.ru_inblock,
        },
        "disk": {
            "read_bytes": disk_read_bytes,
            "read_mib": (disk_read_bytes / (1024 * 1024)) if disk_read_bytes is not None else None,
            "fault_throughput_mib_per_s": (
                (disk_read_bytes / (1024 * 1024)) / io_wait
                if disk_read_bytes is not None and io_wait > 0
                else None
            ),
        },
    }

def read_file(filename: str, chunk_size: int) -> int:
    def _resolve_blob_path() -> str:
        # On Vercel the runtime working directory is the project base, but be
        # robust and also look next to this file. Fall back to the first candidate
        # so the error message below is useful when nothing is found.
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
            os.path.join(os.getcwd(), filename),
            filename,
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    path = _resolve_blob_path()
    if not os.path.exists(path):
        raise HTTPException(
            status_code=500,
            detail=f"blob not found; looked for {filename} (resolved to {path})",
        )

    bytes_read = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            bytes_read += len(chunk)
    return bytes_read

@app.get("/blob")
def read_blob():
    start = perf_counter()
    bytes_read = read_file(BLOB_FILENAME, READ_CHUNK_SIZE)
    elapsed = perf_counter() - start
    mib_read = bytes_read / (1024 * 1024)
    return {
        "path": BLOB_FILENAME,
        "bytes_read": bytes_read,
        "elapsed_seconds": elapsed,
        "throughput_mib_per_s": (mib_read / elapsed) if elapsed > 0 else None,
        "chunk_size_bytes": READ_CHUNK_SIZE,
    }
