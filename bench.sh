#!/usr/bin/env bash
#
# Cold-boot + demand-paging benchmark.
#
# The deployment's backing storage faults data in from disk on demand, so:
#   "/"        -> baseline: just runtime init (cold) vs nothing (warm)
#   "/imports" -> first hit faults in sklearn/PIL/pandas/spacy/xgboost from disk,
#                 second hit is served from sys.modules (memory)
#   "/blob"    -> first hit faults in blob.bin pages from disk,
#                 second hit is (potentially) served from page cache
#
# Each run exercises "/" (cold + warm) then ONE heavy route, so the long
# /imports call can't trigger scale-out that pollutes the /blob measurements
# (and vice versa).
#
# In blob mode, /blob is hit BLOB_HITS times (default 6) and results are
# grouped by instance (X-Booted-At), so same-instance repeats reveal whether
# the page cache is actually retaining the blob between requests.
#
# Usage: ./bench.sh <base-url> <imports|blob>
#        SLEEP=0 ./bench.sh <base-url> blob        # skip the cold-boot wait
#        BLOB_HITS=10 ./bench.sh <base-url> blob   # more repeat reads

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-}}"
MODE="${2:-}"
SLEEP="${SLEEP:-45}"

usage() {
  echo "usage: $0 <base-url> <imports|blob>   (e.g. $0 https://fastapi-1gb.vercel.app blob)" >&2
  exit 1
}

if [[ -z "$BASE_URL" ]]; then
  usage
fi
case "$MODE" in
  imports|blob) ;;
  *) usage ;;
esac
BASE_URL="${BASE_URL%/}"

pretty() {
  if command -v jq >/dev/null 2>&1; then jq -c . 2>/dev/null || cat; else cat; fi
}

RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

hit() {
  local label="$1" path="$2"
  local body_file headers_file http_code time_total booted_at throughput
  body_file="$(mktemp)"
  headers_file="$(mktemp)"

  read -r http_code time_total < <(
    curl -sS -o "$body_file" -D "$headers_file" -w '%{http_code} %{time_total}\n' "$BASE_URL$path"
  )
  booted_at="$(awk 'tolower($1) == "x-booted-at:" { print $2 }' "$headers_file" | tr -d '\r')"
  throughput="$(python3 -c '
import json, sys
try:
    t = json.load(open(sys.argv[1])).get("throughput_mib_per_s")
    print(f"{t:.0f}" if t else "")
except Exception:
    print("")
' "$body_file")"

  printf '%-22s %-10s status=%s  client_total=%7.3fs  booted_at=%s\n' \
    "$label" "$path" "$http_code" "$time_total" "${booted_at:-<missing>}"
  printf '  body: %s\n' "$(pretty < "$body_file")"

  printf '%s\t%s\t%s\t%s\n' "$label" "${booted_at:-?}" "$time_total" "${throughput:-}" >> "$RESULTS_FILE"
  rm -f "$body_file" "$headers_file"
}

summarize_by_instance() {
  python3 - "$RESULTS_FILE" <<'EOF'
import sys
from collections import OrderedDict

groups = OrderedDict()  # booted_at -> list of (label, client_s, thpt)
for line in open(sys.argv[1]):
    label, boot, client, thpt = line.rstrip("\n").split("\t")
    groups.setdefault(boot, []).append((label, float(client), thpt))

print("--- summary by instance ---")
for n, (boot, rows) in enumerate(groups.items(), 1):
    print(f"instance #{n} (booted_at={boot}):")
    for label, client, thpt in rows:
        extra = f"  server={thpt} MiB/s" if thpt else ""
        print(f"  {label:<24} client={client:7.3f}s{extra}")
EOF
}

echo "target: $BASE_URL (mode: $MODE)"
if (( SLEEP > 0 )); then
  echo "sleeping ${SLEEP}s to let the function scale to zero (cold boot)..."
  sleep "$SLEEP"
fi
echo

echo "--- baseline: runtime init only ---"
hit '"/" cold'  /
hit '"/" warm'  /
echo

if [[ "$MODE" == "imports" ]]; then
  echo "--- imports: python modules faulted in from disk on first use ---"
  hit '"/imports" 1st (fault)' /imports
  hit '"/imports" 2nd (cached)' /imports
else
  BLOB_HITS="${BLOB_HITS:-6}"
  echo "--- blob: ${BLOB_HITS} reads of 500MiB file; repeats on the same instance test the page cache ---"
  for ((i = 1; i <= BLOB_HITS; i++)); do
    hit "\"/blob\" hit $i" /blob
  done
fi
echo

summarize_by_instance
