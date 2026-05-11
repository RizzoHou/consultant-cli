---
name: consult-zh
description: Use when the task involves producing or analyzing native Chinese-language content — translation into/from Chinese, original Chinese prose, literary Chinese (诗词, 文言文, 散文), formal/ceremonial Chinese, domain-specific Chinese (legal, medical, technical), or close analysis of Chinese source text (essays, poems, news, code with substantive Chinese comments). Brings DeepSeek into the loop via the `consultant` CLI in a draft+critique multi-round flow. Skip for trivial 1–2-word translations, English tasks that merely mention Chinese, or pinyin-only prompts.
tools: Bash, Read, Edit, Write
---

# consult-zh

Route Chinese-language work to the `consultant` CLI's `chinese` tag (which currently resolves to DeepSeek) in coordination with your own (Opus) judgment. DeepSeek's edge is native Chinese generation and idiom; yours is structural reasoning and editorial discipline. The default workflow plays both to their strengths.

The skill always passes `-t chinese` explicitly so the routing survives any future change to the CLI's default tag (today the default is `reasoning`, which goes to OpenAI via OpenRouter — wrong choice for native Chinese).

## Prerequisites

- The `consultant` binary is on `$PATH` (typically symlinked from your local clone of [consultant-cli](https://github.com/RizzoHou/consultant-cli) — e.g. `ln -s /path/to/consultant-cli/consultant ~/.local/bin/consultant`).
- A DeepSeek API key is set up per the repo README (`secrets/deepseek.key` or `$DEEPSEEK_API_KEY`) — the `chinese` tag targets DeepSeek, so this is the key that gets loaded.
- Sessions persist at `<consultant-project>/sessions/<NAME>.jsonl` regardless of cwd. To inspect: `cat "$(dirname "$(readlink -f "$(which consultant)")")"/sessions/<NAME>.jsonl`.

## When to trigger

Trigger on tasks that produce or analyze native Chinese, including:

- Translation into Chinese (English/other → Chinese), especially anything beyond a phrase.
- Original Chinese composition: essays, letters, fiction, poetry, formal/ceremonial.
- Classical Chinese: 文言文 reading or composition, 诗词 (律诗, 绝句, 词牌), 对联.
- Domain-specific Chinese where idiom matters: legal contracts, medical notes, technical specs.
- Close analysis or critique of Chinese source material (poems, essays, news).
- Code reviews where Chinese comments/strings carry meaning that affects judgment.

Do NOT trigger for:

- Trivial 1–2-word translations (你好, 谢谢, 是的) — answer directly.
- English-only tasks that merely *mention* Chinese.
- Pinyin-only prompts unless the user explicitly wants 汉字.
- Tasks where the user already provided a Chinese answer and just wants formatting/cleanup.

## Default strategy: draft+critique (one round)

Two roles, one critique-revise cycle. Pick the drafter based on task shape:

| Task shape | Drafter | Critic |
|---|---|---|
| Native Chinese prose (literary, idiomatic, classical) | DeepSeek | You (Opus) |
| Reasoning *expressed in* Chinese (technical explanation, structured argument) | You (Opus) | DeepSeek |

### When DeepSeek drafts

Tie the output file to the session name so parallel tasks don't collide on `/tmp/`:

```bash
# Turn 1: DeepSeek produces the draft, written to a file
SLUG=zh-<short-name>     # e.g. zh-poem-autumn, zh-translate-contract-v3
consultant -t chinese --session "$SLUG" \
  -s "<task-specific system prompt>" \
  -o "/tmp/${SLUG}.md" \
  "<the writing task>"
```

The `chinese` tag defaults to effort `max` — don't pass `-e` unless you have a specific reason to want a lighter, faster pass.

Then:

1. `Read` `/tmp/${SLUG}.md`.
2. Critique it: factual issues, structural problems, register mismatch, idiom errors, parallelism in poetry, etc.
3. If the draft needs work, send the critique back through the same session:

   ```bash
   consultant -t chinese --session "$SLUG" \
     -o "/tmp/${SLUG}-v2.md" \
     "Revise based on these notes: <your critique>"
   ```

4. Read the revision. **Stop after one critique-revise round by default.** Hand the result to the user with a brief note on what changed. Only do a second round if the result is still materially off — never spiral past two rounds.

### When you draft

Produce your draft directly, then send it to DeepSeek for critique:

```bash
consultant -t chinese --session zh-<short-name> \
  "Critique the following Chinese draft for idiom, register, and flow. \
   Be specific — quote phrases that need revision and propose alternatives. \
   Do not produce a full rewrite.

   <your draft>"
```

Read the critique, decide which suggestions to apply, and revise yourself. You retain editorial control.

## File output for long content

Anything over a few paragraphs of Chinese should go through `-o "/tmp/${SLUG}.md"` (where `SLUG` matches the session name) to avoid polluting your streaming context. Always `Read` the file back before judging or delivering — the file pattern is a working surface, not a black box.

## Multi-round mechanics

- `--session NAME` persists conversation across calls. The system prompt is **locked from turn 1**; passing `-s` on a continuing session is an error.
- Pick a session name distinct per task: `zh-poem-autumn`, `zh-translate-contract-v3`. Avoid reuse across unrelated tasks.
- Sessions are project-relative: stored at `<consultant-project>/sessions/<NAME>.jsonl` no matter your cwd.
- To start fresh, just use a new name. Don't try to delete or hand-edit the JSONL.

## Editorial pass on DeepSeek drafts

After DeepSeek's final revision, do a **light** editorial pass before delivering: consistency of proper nouns, obvious typos, formatting. Don't substantively rewrite — that defeats the point of using DeepSeek as drafter. If you find yourself wanting to rewrite >20% of the prose, send another critique round instead.

For literary Chinese specifically (诗词, 文言文), be especially restrained — voice consistency matters more than your own preferences.

## Alternative strategies (only on explicit user request)

The user can override the default with these:

- **Synthesize** ("synthesize / blend / merge two drafts"). Run two parallel `consultant -t chinese` calls (no `--session`), then produce a hybrid yourself. Warning: prone to tonal inconsistency in literary output — flag this if the user requests it for poetry or fiction.
- **Race-and-pick** ("show me both / which is better"). Get DeepSeek's draft, present both yours and DeepSeek's side-by-side, recommend one with reasoning, let the user choose.
- **Labor-split** ("Opus structure, DeepSeek wording"). Draft the structural skeleton yourself, then send to DeepSeek with: *"Refine the wording while keeping the structure intact. Do not reorganize."*

Do not auto-detect when to use these — they require explicit user instruction.

## Effort selection

The `chinese` tag defaults to `-e max` for DeepSeek — that's the right setting for native Chinese work and the reason DeepSeek is in the loop at all. Don't pass `-e` unless you specifically want to opt down.

- **Default (`-e max`, implicit via the `chinese` tag):** all drafts, critiques, revisions, classical composition, idiomatic translation.
- **`-e high` (opt-in only):** when you want a quicker, lighter pass and have judged the task too small to justify max effort (e.g. short factual translation, a one-off register check).

When in doubt, leave `-e` off and let the tag's default apply.

## Failure modes

- **Missing API key**: CLI exits with a clear error pointing at `secrets/deepseek.key` / `$DEEPSEEK_API_KEY` (the `chinese` tag selects DeepSeek, so that's the key looked up). Surface the error to the user; do not silently fall back to your own Chinese.
- **Network error / timeout**: retry once with the same `--session` (the session preserves history; you don't lose turns). If it fails again, do the task yourself and explicitly tell the user DeepSeek was unavailable.
- **System prompt lock error** on turn 2+: you tried to pass `-s` on a continuing session. Either drop `-s` (the turn-1 system prompt is still in effect) or start a new session with a new name.
- **DeepSeek draft is in the wrong register / off-topic**: don't try to fix it editorially. Send a single targeted critique through `--session` and ask for a revision. One round of redirection is cheaper than rewriting yourself.

## Reporting back to the user

When delivering, briefly note:

- Which strategy was used (default draft+critique, or an explicit alternative).
- How many rounds happened.
- Any DeepSeek output you significantly modified, and why.

Don't paste the full DeepSeek transcript — the user wants the result, not the process. Keep the meta-note to 1–3 lines.
