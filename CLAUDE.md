# CLAUDE.md

## What this project is

A small CLI for agents to consult a stronger reasoning model with per-call control of model + effort. Full usage and architecture are in README.md — don't restate them here.

Public on GitHub at `RizzoHou/consultant-cli`, MIT-licensed. Treat README as user-facing; keep the public surface (CLI flags, provider interface) stable across changes.

## Editing invariants

- **Stdlib only.** No `openai`, `requests`, `litellm`, etc. Reasons: zero install friction; LiteLLM strips DeepSeek's `reasoning_effort` (BerriAI/litellm#27439). If you add a provider, use `urllib`.
- **DeepSeek thinking mode needs BOTH fields:** `reasoning_effort` AND `thinking: {type: "enabled"}` in the request body. One alone silently runs in non-thinking mode.
- **OpenRouter reasoning shape is different.** OpenRouter uses a unified `reasoning: {effort: ..., enabled: true}` object — *not* `reasoning_effort` + `thinking`. Effort values for `openai/gpt-5.5`: `minimal | low | medium | high | xhigh`. Streamed reasoning arrives as either `delta.reasoning` (string passthrough) or `delta.reasoning_details[]` (array of `{type: "reasoning.text", text, ...}`). The provider in `src/providers/openrouter.py` handles both; don't drop either branch. Note: `openai/gpt-5.5` bills reasoning tokens but does not surface raw CoT text, so `--show-thinking` is typically empty for that model — that's expected, not a bug.
- **Tags are the canonical addressing layer.** `src/tags.py` maps capability tags (`reasoning`, `vision`, `chinese`) to `(provider, model, effort)`. Skills and examples should prefer `-t TAG` over `-p`/`-m`/`-e`. When retargeting a tag, edit `src/tags.py` only — don't chase skill files unless the retarget changes a capability (e.g. dropping image support, switching language).
- **`src/` is not a package.** The `consultant` shim prepends `src/` to `sys.path`, so modules import each other as `from inputs import …` (or `from tags import …`), not `from src.inputs import …`. `src/providers/` IS a package (has `__init__.py`).
- **Secrets:** `secrets/*` is gitignored except `.gitkeep`. Never commit keys.
- **Symlink-safe shim.** The `consultant` entrypoint uses `os.path.realpath(__file__)` to find `src/`, so the binary works when symlinked onto `$PATH` (e.g. `~/.local/bin/consultant`). Don't change this back to `abspath`.
- **Sessions are project-relative.** `--session NAME` stores JSONL at `<project>/sessions/<NAME>.jsonl` regardless of cwd. Gitignored. The system prompt is locked from turn 1 — passing `-s` on a continuing session is an error.
- **Skill templates track the CLI.** `skills/<name>/SKILL.md` are the canonical Claude Code skill definitions for this project. When the CLI surface changes (flags, defaults, output shape, new provider, effort levels) reconcile the affected skill in the same task. *Tag retargets* are a special case: if `src/tags.py` retargets `chinese` to a different DeepSeek model, the skill is fine; if it retargets to a non-Chinese provider, fix the skill. Note that installed skill copies under `~/.claude/skills/<name>/` are separate files (not symlinks) — update both.

## Adding a provider

See README → "Adding a provider". One file in `src/providers/<name>.py`, register in `src/providers/__init__.py`. The class needs `name`, `default_model`, `default_effort`, `valid_efforts`, `supports_images`, `key_env`, `key_file`, and a `stream(messages, model, effort)` generator yielding events of type `content` / `reasoning` / `usage` / `done`.

## Smoke test after edits

```bash
# default tag (`reasoning`) → OpenRouter / openai/gpt-5.5 / xhigh
./consultant "Reply with exactly: PONG"

# DeepSeek path (separate provider, separate key file)
./consultant -t chinese -e high "Reply with exactly: PONG"
```

Expect `PONG` from each. Confirms key loading, request shape, tag resolution, and SSE parsing for both providers.
