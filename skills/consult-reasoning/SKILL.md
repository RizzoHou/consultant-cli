---
name: consult-reasoning
description: Use when the task needs a strong independent reasoning pass — architectural tradeoffs, hard debugging that's stuck, spec / RFC / paper interpretation, math or proof sketches, "is this approach safe under X." Brings OpenRouter's `openai/gpt-5.5` (xhigh effort) into the loop via the `consultant` CLI's `reasoning` tag. Distinct from `advisor()` — advisor reviews YOUR transcript, this skill briefs a fresh reasoner on a problem you scope explicitly. Skip for lookups, simple code edits, and questions Claude already has full context to answer.
tools: Bash, Read, Edit, Write
---

# consult-reasoning

Route hard reasoning tasks to the `consultant` CLI's `reasoning` tag (today: OpenRouter / `openai/gpt-5.5` / `xhigh`). The point is to get an independent reasoning pass on a problem you've scoped — no Claude transcript, no shared assumptions — then decide what to keep.

The skill always passes `-t reasoning` explicitly so routing survives any future change to the CLI's default tag.

## How this differs from `advisor()`

Both reach a stronger model. They serve different needs:

| | `advisor()` | `consultant -t reasoning` |
|---|---|---|
| Sees your transcript? | Yes — full history | No — only what you brief |
| Best for | "Sanity check what I just did / why I'm stuck" | "Independent fresh reasoning on a problem I'll scope" |
| Iterative? | One call | `--session` for multi-round |
| Tunable effort? | No | Yes (`-e minimal..xhigh`) |
| File / image input? | No | Yes (`--file`, `--image`, `@path`) |

If the question is "is my current approach right?" → `advisor()`. If the question is "given this problem statement and these primary sources, what's the right answer?" → this skill.

## Prerequisites

- The `consultant` binary is on `$PATH` (typically symlinked from your local clone of [consultant-cli](https://github.com/RizzoHou/consultant-cli) — e.g. `ln -s /path/to/consultant-cli/consultant ~/.local/bin/consultant`).
- An OpenRouter API key per the repo README (`secrets/openrouter.key` or `$OPENROUTER_API_KEY`) — the `reasoning` tag targets OpenRouter.
- Sessions persist at `<consultant-project>/sessions/<NAME>.jsonl` regardless of cwd. To inspect: `cat "$(dirname "$(readlink -f "$(which consultant)")")"/sessions/<NAME>.jsonl`.

## When to trigger

- Architectural tradeoffs ("which of these data layouts is right under workload X").
- Debugging that's stuck — you've tried the obvious things, the symptoms don't fit the obvious causes.
- Spec / RFC / paper interpretation where the answer hinges on careful reading.
- Math, proof sketches, complexity analysis, invariant arguments.
- Safety / correctness review of an approach against constraints (concurrency, ordering, failure modes).
- Cross-cutting design decisions where you want a second mind on the tradeoffs.

Do NOT trigger for:

- Code Claude already has full context to write or fix.
- Lookups answerable by reading a file or running a command.
- Style / formatting / naming questions.
- Questions where you haven't yet read the primary source — read it first, then consult.

## Choosing your strategy: single-shot vs. multi-round

Two patterns. Pick based on how well-scoped the question is and whether you expect to iterate. Don't reflexively reach for `--session` — it costs context and money on every turn.

### Single-shot (default for well-scoped questions)

The question is concrete, self-contained, and you don't expect to iterate. Brief the consultant once, read the answer, integrate.

```bash
SLUG=reason-<short-name>     # e.g. reason-cache-invalidation, reason-merge-strategy
consultant -t reasoning \
  -o "/tmp/${SLUG}.md" \
  "<full problem brief — context, what you've tried, what you need>"
```

Then `Read /tmp/${SLUG}.md`, evaluate the reasoning (don't accept blindly), and act.

### Multi-round via `--session`

The problem is open-ended, you expect to iterate, or the first answer raised follow-up questions worth pursuing. Use a session so each turn keeps prior context.

```bash
SLUG=reason-<short-name>
# Turn 1
consultant -t reasoning --session "$SLUG" \
  -o "/tmp/${SLUG}-1.md" \
  "<initial brief>"

# Read, then turn 2 with a follow-up
consultant -t reasoning --session "$SLUG" \
  -o "/tmp/${SLUG}-2.md" \
  "<sharper question, or 'reconcile X with Y from your prior answer'>"
```

The system prompt is **locked from turn 1** — passing `-s` on a continuing session is an error. Start a new session name to reset.

### Deciding between them

| Signal | Use |
|---|---|
| Concrete question, all primary sources fit in one brief | Single-shot |
| You already know you'll want to follow up regardless of the answer | Multi-round |
| First answer left ambiguity worth resolving | Continue with `--session` |
| You've spiraled past two refinement rounds without convergence | Stop. Reformulate the question or accept the current answer. |

## Briefing discipline

The consultant sees nothing except your prompt. Vague briefs get vague answers. Include:

- The concrete problem statement — not "what do you think about caching" but "I have N writers and one reader on a shared X; the reader sometimes sees Y; here's the relevant code: ...".
- What you've already tried or ruled out, and what still doesn't fit.
- The primary sources — paste the relevant code, the spec excerpt, the error trace. Prefer `--file path` or `@path` over describing them in prose.
- The specific question you want answered.
- Any constraints (latency budget, can't change schema, must be backwards-compatible).

If your brief feels short, it's probably underspecified. Reread it through fresh eyes before sending.

## File and image input

- `--file path` or `@path` inline: attach text files (code, specs, logs).
- `--image path` or `@path.png`: attach images. For *vision-first* tasks (diagram interpretation, chart analysis, art) prefer the `consult-vision` skill — it routes through the `vision` tag with effort tuned for image work.

## Effort selection

The `reasoning` tag defaults to `-e xhigh`. That's the right setting for actual hard reasoning and the reason this skill exists.

- **Default (`-e xhigh`, implicit via the tag):** anything you're consulting on at all.
- **`-e high` (opt-in):** when you've judged the question light enough that xhigh is wasted (e.g. a quick spec lookup that still wants reasoning, but not deep reasoning).
- **`-e medium` or below:** rarely worth using through this skill — if a question is that small, just answer it yourself.

When in doubt, leave `-e` off and let the tag default apply.

## File output for long answers

Anything over a few paragraphs should go through `-o "/tmp/${SLUG}.md"` (where `SLUG` matches any session name) to avoid polluting your streaming context. Always `Read` the file back before judging or delivering — the file pattern is a working surface, not a black box.

## `--show-thinking` is empty for `gpt-5.5` — that's expected

The current `reasoning` tag target (`openai/gpt-5.5`) bills reasoning tokens but does not surface raw chain-of-thought text. So `--show-thinking` will typically print nothing even when the model spent significant reasoning effort. This is documented in the project CLAUDE.md, not a bug. If a future tag retarget moves to a model that does surface CoT, `--show-thinking` will start working again automatically.

## Failure modes

- **Missing API key:** CLI exits with a clear error pointing at `secrets/openrouter.key` / `$OPENROUTER_API_KEY`. Surface the error to the user; do not silently fall back to your own answer without saying so.
- **Network error / timeout:** retry once with the same `--session` (history is preserved; you don't lose turns). If it fails again, do the task yourself and explicitly note the consultant was unavailable.
- **System prompt lock error** on turn 2+: you tried to pass `-s` on a continuing session. Drop `-s` (the turn-1 system prompt is still in effect) or start a new session with a new name.
- **Answer is confidently wrong:** don't propagate it. The consultant doesn't see your context — if its answer rests on assumptions that contradict primary sources you have, send a critique through `--session` ("you assumed X; the actual code says Y; reconsider") rather than accepting.

## Reporting back to the user

When delivering, briefly note:

- That `consultant -t reasoning` was used.
- Single-shot or multi-round (and how many rounds, if multi).
- What you took from the answer vs. what you set aside, when non-trivial.

Don't paste the full consultant transcript — the user wants the integrated result, not the process. Keep the meta-note to 1–3 lines.
