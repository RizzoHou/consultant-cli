"""Input handling: @path file references, --file/--image attachments, prompt assembly."""
import base64
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}
PDF_RENDER_DPI = 150

# Match @<path> tokens. The @ must be at start-of-string or preceded by
# whitespace / open-bracket / common punctuation (so we don't match emails
# like user@example.com). Capture maximal non-whitespace; we trim trailing
# punctuation when checking existence.
_AT_RE = re.compile(r'(?:(?<=^)|(?<=[\s(\[{,;:]))@(\S+)')
_TRAIL_PUNCT = '.,;:!?)]}'


class Attachment:
    __slots__ = ("path", "kind")

    def __init__(self, path: str, kind: str):
        self.path = path
        self.kind = kind  # "text" | "image" | "pdf"

    def __eq__(self, other):
        return isinstance(other, Attachment) and self.path == other.path

    def __hash__(self):
        return hash(self.path)


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def is_pdf(path: str) -> bool:
    return Path(path).suffix.lower() in PDF_EXTS


def _classify(path: str) -> str:
    if is_image(path):
        return "image"
    if is_pdf(path):
        return "pdf"
    return "text"


def _resolve_at_token(raw: str) -> str | None:
    """Given the captured token after @, return the longest prefix that
    is an existing file (after stripping trailing punctuation), or None."""
    candidate = raw
    while candidate:
        if Path(candidate).is_file():
            return candidate
        if candidate[-1] in _TRAIL_PUNCT:
            candidate = candidate[:-1]
            continue
        return None
    return None


def expand_at_refs(text: str) -> tuple[str, list[Attachment]]:
    """Replace @path tokens (that resolve to existing files) with [file: path]
    placeholders, and return (rewritten_text, attachments_in_order).

    Use \\@ to escape a literal @ that should NOT be treated as a reference.
    """
    found: list[Attachment] = []
    seen: set[str] = set()

    def repl(m: re.Match) -> str:
        # Honor backslash-escape: if the @ was preceded by backslash, leave alone.
        start = m.start()
        if start > 0 and text[start - 1] == "\\":
            return m.group(0)
        token = m.group(1)
        path = _resolve_at_token(token)
        if path is None:
            return m.group(0)
        if path not in seen:
            seen.add(path)
            found.append(Attachment(path, _classify(path)))
        # Preserve trailing chars that weren't part of the path
        trailing = token[len(path):]
        return f"[file: {path}]{trailing}"

    new_text = _AT_RE.sub(repl, text)
    # Unescape \@ -> @
    new_text = new_text.replace("\\@", "@")
    return new_text, found


def collect_attachments(prompt_text: str, file_args: list[str], image_args: list[str]):
    """Return (rewritten_prompt, attachments) where attachments is a deduped
    list preserving first-seen order across @refs, --file, and --image."""
    rewritten, refs = expand_at_refs(prompt_text)
    seen: set[str] = {a.path for a in refs}
    out: list[Attachment] = list(refs)
    for p in file_args:
        if p in seen:
            continue
        if not Path(p).is_file():
            raise FileNotFoundError(f"--file not found: {p}")
        out.append(Attachment(p, _classify(p)))
        seen.add(p)
    for p in image_args:
        if p in seen:
            continue
        if not Path(p).is_file():
            raise FileNotFoundError(f"--image not found: {p}")
        out.append(Attachment(p, "image"))
        seen.add(p)
    return rewritten, out


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _image_data_url(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime or not mime.startswith("image/"):
        # Default by extension
        ext = Path(path).suffix.lower().lstrip(".")
        mime = f"image/{ext or 'png'}"
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _pdf_to_data_urls(path: str) -> list[str]:
    """Render a PDF to one PNG data URL per page using `pdftoppm`."""
    if shutil.which("pdftoppm") is None:
        raise RuntimeError(
            "PDF support requires `pdftoppm` (poppler-utils). "
            "Install with `apt install poppler-utils` (Debian/Ubuntu) or "
            "`brew install poppler` (macOS)."
        )
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(PDF_RENDER_DPI), path, str(prefix)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"pdftoppm failed on {path}: {err}") from None
        # Sort by trailing page index — padding is uniform within a single
        # run, but a numeric key is bulletproof regardless.
        pngs = sorted(
            Path(tmp).glob("page-*.png"),
            key=lambda p: int(p.stem.rsplit("-", 1)[1]),
        )
        if not pngs:
            raise RuntimeError(f"pdftoppm produced no pages for {path}")
        sys.stderr.write(
            f"consultant: rendered {len(pngs)} page{'s' if len(pngs) != 1 else ''} "
            f"from {path}\n"
        )
        urls = []
        for png in pngs:
            b64 = base64.b64encode(png.read_bytes()).decode("ascii")
            urls.append(f"data:image/png;base64,{b64}")
        return urls


def build_messages(
    user_text: str,
    attachments: list[Attachment],
    system: str | None,
    supports_images: bool,
) -> list[dict]:
    """Assemble the messages array. Text files are appended as a delimited
    block at the end of the user message. Images become multimodal content
    blocks if the provider supports them; otherwise we raise."""
    text_atts = [a for a in attachments if a.kind == "text"]
    visual_atts = [a for a in attachments if a.kind in ("image", "pdf")]

    if visual_atts and not supports_images:
        names = ", ".join(a.path for a in visual_atts)
        msg = f"Provider does not support image input, but received: {names}"
        if any(a.kind == "pdf" for a in visual_atts):
            msg += " (PDFs render to images, so they need an image-capable provider too)"
        raise ValueError(msg + ".")

    body = user_text.rstrip()
    if text_atts:
        parts = ["", "--- Attached files ---"]
        for a in text_atts:
            content = _read_text(a.path)
            parts.append(f"\n=== file: {a.path} ===\n{content}")
        body = body + "\n" + "\n".join(parts)

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})

    if visual_atts:
        content_blocks: list[dict] = [{"type": "text", "text": body}]
        for a in visual_atts:
            if a.kind == "image":
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": _image_data_url(a.path)},
                })
            else:  # pdf
                for url in _pdf_to_data_urls(a.path):
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": url},
                    })
        messages.append({"role": "user", "content": content_blocks})
    else:
        messages.append({"role": "user", "content": body})

    return messages
