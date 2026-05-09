# CLAUDE.md

## What this project is

A small CLI for agents to consult a stronger reasoning model with per-call control of model + effort. Full usage and architecture are in README.md — don't restate them here.

Public on GitHub at `RizzoHou/consultant-cli`, MIT-licensed. Treat README as user-facing; keep the public surface (CLI flags, provider interface) stable across changes.

## Editing invariants

- **Stdlib only.** No `openai`, `requests`, `litellm`, etc. Reasons: zero install friction; LiteLLM strips DeepSeek's `reasoning_effort` (BerriAI/litellm#27439). If you add a provider, use `urllib`.
- **DeepSeek thinking mode needs BOTH fields:** `reasoning_effort` AND `thinking: {type: "enabled"}` in the request body. One alone silently runs in non-thinking mode.
- **`src/` is not a package.** The `consultant` shim prepends `src/` to `sys.path`, so modules import each other as `from inputs import …`, not `from src.inputs import …`. `src/providers/` IS a package (has `__init__.py`).
- **Secrets:** `secrets/*` is gitignored except `.gitkeep`. Never commit keys.
- **Symlink-safe shim.** The `consultant` entrypoint uses `os.path.realpath(__file__)` to find `src/`, so the binary works when symlinked onto `$PATH` (e.g. `~/.local/bin/consultant`). Don't change this back to `abspath`.
- **Sessions are project-relative.** `--session NAME` stores JSONL at `<project>/sessions/<NAME>.jsonl` regardless of cwd. Gitignored. The system prompt is locked from turn 1 — passing `-s` on a continuing session is an error.

## Adding a provider

See README → "Adding a provider". One file in `src/providers/<name>.py`, register in `src/providers/__init__.py`. The class needs `name`, `default_model`, `default_effort`, `valid_efforts`, `supports_images`, `key_env`, `key_file`, and a `stream(messages, model, effort)` generator yielding events of type `content` / `reasoning` / `usage` / `done`.

## Smoke test after edits

```bash
./consultant -e high "Reply with exactly: PONG"
```

Expect `PONG` in ~2s. Confirms key loading, request shape, and SSE parsing.
