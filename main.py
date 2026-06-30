import os
from time import perf_counter, time
from fastapi import FastAPI, HTTPException

BOOT = time()

app = FastAPI()

@app.get("/")
def ping():
    return {
        "booted_at": BOOT,
    }

@app.get("/imports")
def imports():
    import sklearn
    import PIL
    import pandas
    import spacy
    import xgboost

    return {
        "sklearn": sklearn.__version__,
        "PIL": PIL.__version__,
        "pandas": pandas.__version__,
        "spacy": spacy.__version__,
        "xgboost": xgboost.__version__,
    }

@app.get("/blob")
def read_blob():
    BLOB_FILENAME = "blob.bin"
    READ_CHUNK_SIZE = 8 * 1024 * 1024 # 8 MiB
    def _resolve_blob_path() -> str:
        # On Vercel the runtime working directory is the project base, but be
        # robust and also look next to this file. Fall back to the first candidate
        # so the error message below is useful when nothing is found.
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), BLOB_FILENAME),
            os.path.join(os.getcwd(), BLOB_FILENAME),
            BLOB_FILENAME,
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    path = _resolve_blob_path()
    if not os.path.exists(path):
        raise HTTPException(
            status_code=500,
            detail=f"blob not found; looked for {BLOB_FILENAME} (resolved to {path})",
        )

    size = os.path.getsize(path)
    bytes_read = 0
    start = perf_counter()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(READ_CHUNK_SIZE)
            if not chunk:
                break
            bytes_read += len(chunk)
    elapsed = perf_counter() - start

    mib_read = bytes_read / (1024 * 1024)
    return {
        "path": path,
        "size_bytes": size,
        "bytes_read": bytes_read,
        "elapsed_seconds": elapsed,
        "throughput_mib_per_s": (mib_read / elapsed) if elapsed > 0 else None,
        "chunk_size_bytes": READ_CHUNK_SIZE,
    }
