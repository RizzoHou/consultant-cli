"""Session persistence for multi-round consultant conversations.

Sessions live as one-message-per-line JSONL files under <project>/sessions/<name>.jsonl.
Atomic writes (tmp + rename) so a crash mid-write can't corrupt history; a corrupted
final line on read is silently skipped (cheap recovery from a killed mid-write process).
"""
import json
import os
import tempfile
from pathlib import Path


def session_path(sessions_dir: Path, name: str) -> Path:
    """Resolve a session name to a JSONL path, rejecting unsafe names."""
    if (
        not name
        or any(c in name for c in "/\\\x00")
        or name.startswith(".")
        or name == ".."
    ):
        raise ValueError(
            f"Invalid session name {name!r} "
            "(must be non-empty, no slashes or control chars, no leading dot)"
        )
    return sessions_dir / f"{name}.jsonl"


def load_session(path: Path) -> list[dict]:
    """Load a session's message history. Returns [] if the file doesn't exist."""
    if not path.is_file():
        return []
    msgs: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "role" in obj and "content" in obj:
                msgs.append(obj)
    return msgs


def save_session(path: Path, messages: list[dict]) -> None:
    """Atomically replace the session file with the full message list.

    One JSON object per line. Writes go to a tmp sibling and rename over the
    target so a crash mid-write can't leave a half-written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for m in messages:
                f.write(json.dumps(m, ensure_ascii=False))
                f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
