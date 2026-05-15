---
name: consult-vision
description: Use when the task hinges on careful interpretation of an image or PDF page — dense diagrams (architecture, sequence, schematics), charts and data visualizations where precise reading matters, figures inside papers / slide decks delivered as PDFs, art / visual analysis (composition, technique, iconography, attribution), second opinion on a visual reading you've already done, or sub-agent contexts that don't have the file in scope. Brings OpenRouter's `openai/gpt-5.5` (high effort, image input) into the loop via the `consultant` CLI's `vision` tag; PDFs are rendered page-by-page to images automatically. Skip for "what's in this photo," clean OCR, simple UI screenshots, and plain-text PDFs where the words are the point — Claude is itself multimodal and handles those directly.
tools: Bash, Read, Edit, Write
---

# consult-vision

Route image-interpretation work to the `consultant` CLI's `vision` tag (today: OpenRouter / `openai/gpt-5.5` / `high`). Claude Code is itself multimodal, so the bar for delegating to this skill is higher than for `consult-zh` or `consult-reasoning` — only reach for it when a strong second mind on the image actually helps.

The skill always passes `-t vision` explicitly so routing survives any future tag retarget.

## When to trigger

- **Dense diagrams** — architecture, sequence, schematics, ER diagrams, network topologies — where reading the image carefully *is* the task.
- **Charts and data visualizations** where the answer hinges on precise reading (axes, scales, multi-series, annotations).
- **Art and visual analysis** — composition, technique, iconography, period attribution, comparison across images.
- **Second opinion on a visual interpretation you've already done** — analogous to `advisor()` but for an image-grounded reading.
- **Sub-agent contexts that don't carry the image** — when you're orchestrating and need a partner that can see the file directly.
- **PDF pages where the figure / layout / typography matters** — papers with diagrams, slide decks, anything where rendering the page as an image preserves information that plain text extraction loses.

Do NOT trigger for:

- "What's in this photo" — Claude is multimodal, just look.
- Clean OCR on text screenshots — Claude handles directly.
- Simple UI screenshots Claude can read at a glance.
- Generating images — this CLI does not produce images.
- Plain-text PDFs (reports, contracts, prose) — `consult-reasoning` with `-f file.pdf` works too, but if the words are all that matter you're better off extracting text yourself (`pdftotext`) and avoiding the per-page image upload.

## Prerequisites

- Same as `consult-reasoning`: `consultant` on `$PATH`, OpenRouter key at `secrets/openrouter.key` or `$OPENROUTER_API_KEY`. The `vision` tag uses the same provider as `reasoning`, just with image input enabled and a lower default effort.
- Sessions persist at `<consultant-project>/sessions/<NAME>.jsonl` regardless of cwd.

## Attaching images

Two equivalent forms:

```bash
# Explicit flag (clearest for one or two images, repeatable)
consultant -t vision -i path/to/diagram.png "Walk me through the data flow."

# Inline @path reference (good when interleaving prose and images)
consultant -t vision "Compare @left.png and @right.png — what changed?"
```

Multiple `-i` flags or `@path` references attach multiple images. Mix with `--file path` for accompanying text (e.g. a spec alongside the diagram, or an artist's bio alongside the painting).

### PDFs

PDFs are first-class input — attach with `-f path.pdf` or `@path.pdf`. The CLI renders each page to a PNG (150 dpi) and sends them as image content blocks, so multi-page documents Just Work without you converting first. A `rendered N pages from <path>` line goes to stderr so you see the upload size before the model bills for it.

```bash
consultant -t vision -f paper.pdf "Read figure 3 and walk me through what the curves show."
consultant -t vision -f slides.pdf "Which slide introduces the latency budget? Quote it."
```

Use `-f` / `@path` for PDFs — `-i/--image` is reserved for actual image files. Requires `pdftoppm` (poppler-utils) on `$PATH`; the CLI errors with an install hint if it's missing.

## Choosing your strategy: single-shot vs. multi-round

Same decision as `consult-reasoning` — pick based on task shape, don't reflexively reach for `--session`.

### Single-shot (default for one concrete question)

```bash
SLUG=vis-<short-name>     # e.g. vis-ml-arch, vis-q3-revenue, vis-rothko-1957
consultant -t vision -i path/to/image.png \
  -o "/tmp/${SLUG}.md" \
  "<focused question about the image>"
```

### Multi-round via `--session`

Common for art analysis and dense diagram readings, where you expect to layer interpretations: overall reading → drill into specific elements → reconcile across images → synthesize.

```bash
SLUG=vis-<short-name>
# Turn 1 — overall reading
consultant -t vision --session "$SLUG" \
  -i path/to/image.png \
  -o "/tmp/${SLUG}-1.md" \
  "<initial brief>"

# Turn 2 — drill in
consultant -t vision --session "$SLUG" \
  -o "/tmp/${SLUG}-2.md" \
  "<follow-up — focus on element X, or add @another-image.png for comparison>"
```

The system prompt is **locked from turn 1** — passing `-s` on a continuing session is an error.

Images attached in earlier turns remain in session context — only re-attach (`-i ...` or `@path.png`) when you want to introduce a *new* image.

### Deciding between them

| Signal | Use |
|---|---|
| One concrete question about one image | Single-shot |
| Layered interpretation expected (typical for art / dense schematics) | Multi-round |
| You'll want to introduce additional images partway through | Multi-round |
| You've spiraled past two rounds without convergence | Stop. Reformulate or accept. |

## Briefing discipline

The consultant has the image, but no other context. Tell it:

- What kind of image it is (architecture diagram, oil painting, line chart) — disambiguates reading conventions.
- The specific question — not "what do you see," but "trace the request path from client to database; flag any missing error edges" or "read this composition through Wölfflin's polarities."
- Constraints or background — the era, the system being depicted, the data source, the artist.
- For art tasks: any thematic, scholarly, or technical frame you want considered (formalist, iconographic, biographical, comparative, material/process-focused).

A vague brief on a rich image gives you generic art-history boilerplate or generic "this is a diagram of a system" filler. Specific framings get specific readings.

## Effort selection

The `vision` tag defaults to `-e high`. Lower than `reasoning`'s `xhigh` because image inference is the dominant cost; high is the right balance for most visual work.

- **Default (`-e high`, implicit via the tag):** most diagram, chart, and art tasks.
- **`-e xhigh` (opt-in):** dense schematics with many components; multi-image comparative analysis; art tasks where you want maximal interpretive depth.
- **`-e medium` or below:** quick reads where Claude itself probably suffices anyway — consider whether you should be using this skill at all.

## File output, sessions, failure modes, `--show-thinking`

Same patterns as `consult-reasoning` — see that skill for the full treatment. In brief:

- Pipe long outputs to `-o "/tmp/${SLUG}.md"` and `Read` them back.
- `--show-thinking` is empty for `gpt-5.5` (bills reasoning tokens but doesn't surface CoT) — expected, not a bug.
- Missing key → clear error pointing at `secrets/openrouter.key` / `$OPENROUTER_API_KEY`. Do not silently fall back to your own visual reading without saying so.
- Network error → retry once with the same `--session`.

## Reporting back to the user

Brief 1–3 line note when delivering:

- That `consultant -t vision` was used.
- Number of images and rounds.
- What you took from the answer vs. what you set aside.

For art analysis specifically: keep the consultant's own interpretive language attached when relaying — voice and framing carry meaning, and paraphrasing washes them out. If the user is going to use the reading downstream, deliver the consultant's text + your editorial annotations side by side rather than a flattened summary.
