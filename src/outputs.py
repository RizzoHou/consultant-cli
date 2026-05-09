"""Output sinks: stream content/reasoning to stdout/stderr or files.

A Sink owns one destination. We open files lazily so that --output never
creates an empty file when the API errors before any tokens arrive.
"""
import sys
from pathlib import Path
from typing import TextIO


class Sink:
    def __init__(self, path: str | None, fallback: TextIO | None):
        """If path is set, write to that file (created on first byte).
        Otherwise write to fallback stream. If both are None, the sink
        silently discards (used for reasoning when --show-thinking is off
        and --thinking-output is not set)."""
        self.path = path
        self.fallback = fallback
        self._fh: TextIO | None = None
        self._wrote_anything = False

    def write(self, text: str) -> None:
        if not text:
            return
        self._wrote_anything = True
        if self.path:
            if self._fh is None:
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self._fh = open(self.path, "w", encoding="utf-8")
            self._fh.write(text)
            self._fh.flush()
        elif self.fallback is not None:
            self.fallback.write(text)
            self.fallback.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    @property
    def used(self) -> bool:
        return self._wrote_anything


def make_content_sink(output_path: str | None, *, stream_to_stdout: bool = True) -> Sink:
    fallback = sys.stdout if stream_to_stdout else None
    return Sink(output_path, fallback)


def make_reasoning_sink(thinking_output: str | None, show_thinking: bool) -> Sink:
    if thinking_output:
        return Sink(thinking_output, None)
    if show_thinking:
        return Sink(None, sys.stderr)
    return Sink(None, None)
