#!/usr/bin/env bash
# Example: hand the consultant two source files and ask for a review.
# The answer goes to stdout; the reasoning trace is written to a file.
# Uses the default `reasoning` tag (OpenRouter / openai/gpt-5.5 / xhigh).
set -euo pipefail
cd "$(dirname "$0")/.."

./consultant \
  --thinking-output /tmp/consultant-reasoning.log \
  "Review @examples/sample.py — does the function name match its behaviour?"

echo
echo "(reasoning trace at /tmp/consultant-reasoning.log)"
