from time import perf_counter, time

from fastapi import FastAPI

BOOT_STARTED_AT = perf_counter()
BOOT_STARTED_AT_UNIX = time()

app = FastAPI()

@app.get("/")
def timings():
    return {
        "startup_seconds": STARTUP_SECONDS,
        "process_age_seconds": perf_counter() - BOOT_STARTED_AT,
        "boot_started_at_unix": BOOT_STARTED_AT_UNIX,
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


APP_READY_AT = perf_counter()
STARTUP_SECONDS = APP_READY_AT - BOOT_STARTED_AT
