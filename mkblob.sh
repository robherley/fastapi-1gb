#!/usr/bin/env bash
# Generate a binary blob of random data.
#
# The blob (default 500 MiB) is read back by the `/blob` route in main.py to
# measure disk read throughput on Vercel. This script runs during the Vercel
# build (see "buildCommand" in vercel.json) so the blob is generated fresh on
# every deploy and bundled into the function via "includeFiles". The blob is
# git-ignored (too big for GitHub's 100 MB file limit) and never committed.
#
# Usage (also runs locally for `vercel dev` / testing):
#   ./mkblob.sh [size_mib] [output_path]
set -euo pipefail

size_mib="${1:-500}"
out="${2:-blob.bin}"
bytes=$(( size_mib * 1024 * 1024 ))

# head -c keeps reading until it has exactly $bytes, so this is portable across
# macOS/BSD and Linux/GNU (unlike `dd`, which can short-read /dev/urandom).
head -c "$bytes" /dev/urandom > "$out"

echo "wrote ${bytes} bytes (${size_mib} MiB) to ${out}"
