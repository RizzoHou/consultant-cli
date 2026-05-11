# consultant

A small CLI for asking a stronger model for advice. Built so an autonomous agent (Claude Code, a custom harness, etc.) can shell out to a high-effort reasoning model when it needs a second opinion — without inheriting Claude Code's hard-coded Opus advisor.

Designed around four properties:

- **Per-call control** of model and reasoning effort. Not a session-wide env var.
- **Capability tags** so callers address *what they need* (`-t reasoning`, `-t chinese`, `-t vision`) rather than a specific provider+model pair.
- **File and image input** — both as explicit `--file` / `--image` flags and as `@path` references inline in the prompt.
- **Pipe-friendly by default** — the answer goes to stdout, reasoning stays out of the way.

Supported providers today:

- **OpenRouter** — default. The `reasoning` and `vision` tags route here, currently targeting `openai/gpt-5.5` (effort `minimal | low | medium | high | xhigh`; default `xhigh` on the reasoning tag).
- **DeepSeek V4 Pro** — the `chinese` tag. Strong native-Chinese generation (effort `high | max`; default `max`).

Adding another OpenAI-compatible provider is a single new file under `src/providers/`.

## Layout

```
consultant/
├── consultant              # executable entrypoint
├── src/
│   ├── cli.py              # argparse + main loop
│   ├── tags.py             # capability tag table (reasoning / vision / chinese)
│   ├── inputs.py           # @path resolution, file/image attachments
│   ├── outputs.py          # stdout/stderr/file sinks
│   ├── sessions.py         # multi-round session persistence (--session)
│   └── providers/
│       ├── __init__.py     # provider registry
│       ├── deepseek.py     # DeepSeek V4 Pro client (raw urllib + SSE)
│       └── openrouter.py   # OpenRouter client (raw urllib + SSE)
├── secrets/                # gitignored — drop API keys here
│   ├── deepseek.key
│   └── openrouter.key
├── prompts/                # optional reusable system prompts
├── examples/
├── skills/                 # Claude Code skill templates that drive `consultant`
│   ├── consult-reasoning/  # routes hard reasoning through the `reasoning` tag
│   ├── consult-vision/     # routes image / diagram / art analysis through the `vision` tag
│   └── consult-zh/         # routes Chinese-language work through the `chinese` tag
├── sessions/               # gitignored — runtime --session state
└── .venv/                  # gitignored
```

## Setup

```bash
# venv (no third-party deps; created for project hygiene)
python3 -m venv .venv

# OpenRouter key (powers the default `reasoning` and `vision` tags)
echo 'sk-or-v1-...' > secrets/openrouter.key
chmod 600 secrets/openrouter.key

# DeepSeek key (powers the `chinese` tag) — optional if you only use OpenRouter
echo 'sk-...' > secrets/deepseek.key
chmod 600 secrets/deepseek.key
```

The CLI loads each provider's key in this order: `--key-file PATH` → `$<PROVIDER>_API_KEY` env var (`$OPENROUTER_API_KEY` or `$DEEPSEEK_API_KEY`) → `secrets/<provider>.key`.

## Usage

### Tags

Tags bundle `(provider, model, effort)` so callers address a capability instead of a specific API. The mapping lives in `src/tags.py` — retargeting a tag is a one-line edit and skills/scripts that use it keep working.

| Tag | Provider | Model | Default effort |
|---|---|---|---|
| `reasoning` *(default)* | openrouter | `openai/gpt-5.5` | `xhigh` |
| `vision` | openrouter | `openai/gpt-5.5` | `high` |
| `chinese` | deepseek | `deepseek-v4-pro` | `max` |

```bash
# default tag (`reasoning`) — no flag needed
./consultant "what's the difference between WAL and shadow paging?"

# pick a tag
./consultant -t chinese  "翻译：The cat sat on the mat."
./consultant -t vision -i diagram.png  "explain this architecture"

# explicit -p/-m/-e override individual tag fields, in any combo
./consultant -t reasoning -e high   "ping"   # gpt-5.5 but effort=high
./consultant -t chinese   -e high   "..."    # DeepSeek but effort=high
./consultant -p deepseek            "..."    # tag-less; provider defaults apply
```

Unknown tag → clear error listing what's available.

### Basics

```bash
# inline question
./consultant "what's the difference between WAL and shadow paging?"

# from stdin
cat question.md | ./consultant

# pick effort
./consultant -e high   "quick check on this idea: ..."
./consultant -e xhigh  "deep review: ..."          # OpenRouter / gpt-5.5
./consultant -t chinese -e max "深度审稿：..."      # DeepSeek max-effort
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
./consultant -i diagram.png "explain this architecture"            # default tag handles vision
./consultant -t vision -i screenshot.png "what's broken here?"     # same, explicit
```

The default `reasoning` tag (and the dedicated `vision` tag) point at `openai/gpt-5.5`, which accepts images. Routing through `-t chinese` will reject images because DeepSeek V4 Pro is text-only — each provider declares `supports_images` and the CLI errors cleanly when the chosen provider can't handle them.

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

### Multi-round sessions

For iterative work — drafting then revising, or following up on an earlier answer — pass `--session NAME` to keep the conversation alive across calls. History persists as JSONL at `sessions/<NAME>.jsonl` (gitignored).

```bash
# turn 1: starts a new session, sets the system prompt
./consultant --session draft1 -s prompts/reviewer.md \
  -o draft.md "draft a 七律 about autumn rain"

# turn 2: continues — system prompt is locked from turn 1, so don't pass -s again
./consultant --session draft1 \
  "the third couplet's parallelism feels forced — try again"

# turn 3: more iterations as needed
./consultant --session draft1 -o final.md \
  "good, now expand the imagery in lines 5–6"
```

A few invariants:

- The session file is at `<project>/sessions/<NAME>.jsonl` regardless of cwd — it's resolved relative to the binary's project root, so it works the same whether you call `./consultant` from the project dir or a symlinked `consultant` from anywhere on `$PATH`.
- Sessions persist *messages*, not *tag/provider*. Pass `-t TAG` consistently across turns or you'll silently switch backends mid-conversation (e.g. starting a session with `-t chinese` and continuing without it will route the next turn through the default `reasoning` tag instead).
- The system prompt is locked from turn 1. Passing `-s` on a continuing session is a clear error; to use a different system prompt, start a new session name.
- Writes are atomic (tmp + rename), so a killed mid-write process can't corrupt history. A truncated final line on read is silently skipped.
- There is no auto-pick of "the most recent session" — name selection is always explicit. To start fresh, just use a new name.

## Claude Code skills

This repo ships skill templates under `skills/` that teach Claude Code *when* and *how* to call `consultant`. Skills are how Claude Code decides to delegate — without one, it has no reason to reach for this CLI on its own.

Currently bundled — one skill per capability tag:

- **`skills/consult-reasoning/`** — routes hard reasoning (architectural tradeoffs, stuck debugging, spec interpretation, math/proof, safety reviews) through the `reasoning` tag. Distinguishes itself from Claude Code's built-in `advisor()` (advisor sees your transcript; this skill briefs a fresh reasoner on a problem you scope).
- **`skills/consult-vision/`** — routes image-heavy interpretation (dense diagrams, charts, art / visual analysis) through the `vision` tag. The bar for triggering is higher than the other two because Claude is itself multimodal — the skill spells out when delegating actually helps.
- **`skills/consult-zh/`** — routes native Chinese-language work (translation, original prose, 诗词/文言文, idiomatic critique) through DeepSeek in a draft+critique flow.

Read each skill's frontmatter `description` for the precise trigger and anti-trigger conditions.

To install one (or all) into your Claude Code:

```bash
# symlink so updates to the repo template flow through automatically
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/consult-reasoning" ~/.claude/skills/consult-reasoning
ln -s "$(pwd)/skills/consult-vision"    ~/.claude/skills/consult-vision
ln -s "$(pwd)/skills/consult-zh"        ~/.claude/skills/consult-zh

# or copy if you want to diverge locally
cp -r skills/consult-reasoning skills/consult-vision skills/consult-zh ~/.claude/skills/
```

The template assumes the `consultant` binary is on `$PATH` (see Setup). If you change the CLI surface (flags, defaults, output shape), update the skill template in the same change — see `CLAUDE.md`.

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

Then register it in `src/providers/__init__.py`. If you want the new provider addressable by capability, add an entry to `TAGS` in `src/tags.py`. The CLI does the rest.

## Notes on the DeepSeek API

Two body fields are both required for thinking mode:

```json
{"reasoning_effort": "max", "thinking": {"type": "enabled"}}
```

Sending only one silently runs in non-thinking mode. (See [DeepSeek docs](https://api-docs.deepseek.com/guides/thinking_mode); a related LiteLLM bug strips `reasoning_effort` from this path — we call the API directly with `urllib` to avoid it.)

The response splits chain-of-thought from the final answer:

- `choices[0].delta.reasoning_content` → `--show-thinking` / `--thinking-output`
- `choices[0].delta.content`           → stdout / `-o`

## Notes on the OpenRouter API

OpenRouter uses the unified `reasoning` object (not DeepSeek's `reasoning_effort` + `thinking` pair):

```json
{"reasoning": {"effort": "xhigh", "enabled": true}}
```

Valid effort values for `openai/gpt-5.5`: `minimal | low | medium | high | xhigh`. The `reasoning` tag defaults to `xhigh`; the `vision` tag defaults to `high` (vision queries rarely need maximum reasoning, and high is significantly cheaper).

Reasoning tokens on the wire arrive in one of two shapes — the provider handles both:

- `choices[].delta.reasoning` — string passthrough (OpenAI / Anthropic routes).
- `choices[].delta.reasoning_details[]` — structured array of `{type: "reasoning.text", text, ...}` (the gpt-5.x default via OpenRouter's unified API).

Note: for `openai/gpt-5.5`, OpenAI bills reasoning *tokens* but does not surface raw chain-of-thought text; expect `--show-thinking` to be empty even when `usage.completion_tokens_details.reasoning_tokens > 0`.
