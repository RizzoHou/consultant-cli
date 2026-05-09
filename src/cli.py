"""consultant CLI entrypoint."""
import argparse
import json
import os
import sys
from pathlib import Path

from inputs import build_messages, collect_attachments
from outputs import make_content_sink, make_reasoning_sink
from providers import DEFAULT_PROVIDER, get_provider_class

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_key(provider_cls, explicit_key_file: str | None) -> str:
    """Resolution order: --key-file > $<KEY_ENV> > <project>/<key_file>."""
    if explicit_key_file:
        return Path(explicit_key_file).read_text(encoding="utf-8").strip()
    env_val = os.environ.get(provider_cls.key_env)
    if env_val:
        return env_val.strip()
    default_path = PROJECT_ROOT / provider_cls.key_file
    if default_path.is_file():
        return default_path.read_text(encoding="utf-8").strip()
    raise SystemExit(
        f"No API key found. Set ${provider_cls.key_env}, "
        f"create {default_path}, or pass --key-file."
    )


def _read_prompt(args_prompt: str | None) -> str:
    if args_prompt is not None and args_prompt != "":
        return args_prompt
    if sys.stdin.isatty():
        raise SystemExit(
            "No prompt given. Pass it as an argument, pipe via stdin, "
            "or use --file to attach context."
        )
    return sys.stdin.read()


def _read_system(value: str | None) -> str | None:
    if not value:
        return None
    # If value points to a file, read it; otherwise treat as inline text.
    p = Path(value)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="consultant",
        description="Ask a stronger model for advice. Pipe-friendly, "
                    "supports file refs (@path or --file), images, and writing "
                    "the answer to a file.",
    )
    p.add_argument("prompt", nargs="?", default=None,
                   help="The question. If omitted, read from stdin.")
    p.add_argument("-p", "--provider", default=DEFAULT_PROVIDER,
                   help=f"Provider name (default: {DEFAULT_PROVIDER}).")
    p.add_argument("-m", "--model", default=None,
                   help="Model id. Default depends on provider.")
    p.add_argument("-e", "--effort", default=None,
                   help="Reasoning effort. For deepseek: high|max (default: max).")
    p.add_argument("-s", "--system", default=None,
                   help="System prompt. Inline string or path to a text file.")
    p.add_argument("-f", "--file", action="append", default=[], metavar="PATH",
                   help="Attach a text file (repeatable). Same as @path inline.")
    p.add_argument("-i", "--image", action="append", default=[], metavar="PATH",
                   help="Attach an image (repeatable). Provider must support images.")
    p.add_argument("-o", "--output", default=None, metavar="PATH",
                   help="Write the answer to PATH instead of stdout.")
    p.add_argument("--thinking-output", default=None, metavar="PATH",
                   help="Write reasoning trace to PATH (separate from --output).")
    p.add_argument("--show-thinking", action="store_true",
                   help="Stream reasoning to stderr as it arrives.")
    p.add_argument("--json", action="store_true",
                   help="Emit a final JSON object {content, reasoning, model, usage} "
                        "instead of streaming text. Overrides --output/--thinking-output "
                        "for stdout (file outputs still apply).")
    p.add_argument("--key-file", default=None, metavar="PATH",
                   help="Read API key from this file instead of env / secrets/.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    provider_cls = get_provider_class(args.provider)
    api_key = _load_key(provider_cls, args.key_file)
    provider = provider_cls(api_key)

    raw_prompt = _read_prompt(args.prompt)
    system = _read_system(args.system)

    rewritten, attachments = collect_attachments(raw_prompt, args.file, args.image)
    messages = build_messages(
        user_text=rewritten,
        attachments=attachments,
        system=system,
        supports_images=provider.supports_images,
    )

    model = args.model or provider.default_model
    effort = args.effort or provider.default_effort

    content_buf: list[str] = []
    reasoning_buf: list[str] = []
    usage: dict | None = None

    # In --json mode the final stdout write is the JSON object, so we don't
    # let the streaming sink touch stdout. File sinks still work.
    content_sink = make_content_sink(args.output, stream_to_stdout=not args.json)
    reasoning_sink = make_reasoning_sink(args.thinking_output, args.show_thinking)

    try:
        for event in provider.stream(messages, model=model, effort=effort):
            t = event.get("type")
            if t == "content":
                text = event["text"]
                content_buf.append(text)
                content_sink.write(text)
            elif t == "reasoning":
                text = event["text"]
                reasoning_buf.append(text)
                reasoning_sink.write(text)
            elif t == "usage":
                usage = event["data"]
            elif t == "done":
                break
    finally:
        # Trailing newline for terminal readability when streaming to stdout.
        if not args.json and not args.output and content_sink.used:
            sys.stdout.write("\n")
            sys.stdout.flush()
        if args.show_thinking and not args.thinking_output and reasoning_sink.used:
            sys.stderr.write("\n")
            sys.stderr.flush()
        content_sink.close()
        reasoning_sink.close()

    if args.json:
        payload = {
            "content": "".join(content_buf),
            "reasoning_content": "".join(reasoning_buf),
            "model": model,
            "provider": provider.name,
            "effort": effort,
            "usage": usage,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")

    return 0


def _entry() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        sys.stderr.write("\nconsultant: interrupted\n")
        return 130
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.stderr.write(f"consultant: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(_entry())
