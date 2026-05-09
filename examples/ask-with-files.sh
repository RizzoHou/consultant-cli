#!/usr/bin/env bash
# Example: hand the consultant two source files and ask for a review.
# The answer goes to stdout; the reasoning trace is written to a file.
set -euo pipefail
cd "$(dirname "$0")/.."

./consultant \
  --effort max \
  --thinking-output /tmp/consultant-reasoning.log \
  "Review @examples/sample.py — does the function name match its behaviour?"

echo
echo "(reasoning trace at /tmp/consultant-reasoning.log)"
