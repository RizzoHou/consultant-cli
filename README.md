# consultant

A small CLI for asking a stronger model for advice. Built so an autonomous agent (Claude Code, a custom harness, etc.) can shell out to a high-effort reasoning model when it needs a second opinion — without inheriting Claude Code's hard-coded Opus advisor.

Designed around three properties:

- **Per-call control** of model and reasoning effort. Not a session-wide env var.
- **File and image input** — both as explicit `--file` / `--image` flags and as `@path` references inline in the prompt.
- **Pipe-friendly by default** — the answer goes to stdout, reasoning stays out of the way.

The first supported provider is **DeepSeek V4 Pro** (effort `high` or `max`). Adding another OpenAI-compatible provider is a single new file under `src/providers/`.

## Layout

```
consultant/
├── consultant              # executable entrypoint
├── src/
│   ├── cli.py              # argparse + main loop
│   ├── inputs.py           # @path resolution, file/image attachments
│   ├── outputs.py          # stdout/stderr/file sinks
│   └── providers/
│       ├── __init__.py     # provider registry
│       └── deepseek.py     # DeepSeek V4 Pro client (raw urllib + SSE)
├── secrets/                # gitignored — drop API keys here
│   └── deepseek.key
├── prompts/                # optional reusable system prompts
├── examples/
└── .venv/                  # gitignored
```

## Setup

```bash
# venv (no third-party deps; created for project hygiene)
python3 -m venv .venv

# put your DeepSeek key in secrets/deepseek.key (already done if you ran setup)
echo 'sk-...' > secrets/deepseek.key
chmod 600 secrets/deepseek.key
```

The CLI loads keys in this order: `--key-file PATH` → `$DEEPSEEK_API_KEY` → `secrets/deepseek.key`.

## Usage

### Basics

```bash
# inline question
./consultant "what's the difference between WAL and shadow paging?"

# from stdin
cat question.md | ./consultant

# pick effort
./consultant -e high  "quick check on this idea: ..."
./consultant -e max   "deep review: ..."          # default
```

### Attaching files

Two equivalent ways. Use whichever reads better.

```bash
# explicit flag (repeatable, script-friendly)
./consultant -f src/auth.py -f src/db.py \
  "is this safe under concurrent writes?"

# inline @path (escape with backslash if you want a literal @)
./consultant "compare @src/auth.py with @src/auth_v2.py"
./consultant "literal: \\@notafile stays as text"
```

`@path` only triggers attachment when the path actually resolves to a file — `user@example.com` and similar are left alone. Trailing punctuation (`.,;:!?)]}`) is stripped.

### Images

```bash
./consultant -i diagram.png "explain this architecture"
```

DeepSeek V4 Pro is text-only, so this currently errors. The plumbing is in place for future multimodal providers — each provider declares `supports_images` and the CLI rejects images cleanly when the provider can't handle them.

### Where the output goes

```bash
# default: stream answer to stdout
./consultant "..."

# write answer to a file (created on first byte; never an empty file on error)
./consultant -o review.md "..."

# show reasoning on stderr while it streams
./consultant --show-thinking "..."

# capture reasoning to its own file
./consultant --thinking-output reasoning.log -o answer.md "..."

# JSON for programmatic consumers
./consultant --json "..."
# => {"content": "...", "reasoning_content": "...", "model": "...", "usage": {...}}
```

### System prompt

```bash
# inline
./consultant -s "Be terse. Cite line numbers." "..."

# from a file
./consultant -s prompts/reviewer.md "..."
```

## Adding a provider

Drop a class in `src/providers/<name>.py` exposing:

```python
class MyProvider:
    name = "myprovider"
    default_model = "..."
    default_effort = "..."
    valid_efforts = (...,)
    supports_images: bool = ...
    key_env = "..."
    key_file = "secrets/myprovider.key"

    def __init__(self, api_key: str): ...

    def stream(self, messages, model=None, effort=None):
        # yield {"type": "content"|"reasoning"|"usage"|"done", ...}
        ...
```

Then register it in `src/providers/__init__.py`. The CLI does the rest.

## Notes on the DeepSeek API

Two body fields are both required for thinking mode:

```json
{"reasoning_effort": "max", "thinking": {"type": "enabled"}}
```

Sending only one silently runs in non-thinking mode. (See [DeepSeek docs](https://api-docs.deepseek.com/guides/thinking_mode); a related LiteLLM bug strips `reasoning_effort` from this path — we call the API directly with `urllib` to avoid it.)

The response splits chain-of-thought from the final answer:

- `choices[0].delta.reasoning_content` → `--show-thinking` / `--thinking-output`
- `choices[0].delta.content`           → stdout / `-o`
