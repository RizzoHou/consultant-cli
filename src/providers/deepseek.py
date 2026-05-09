"""DeepSeek V4 Pro provider.

Uses the OpenAI-compatible Chat Completions endpoint at api.deepseek.com.
Sends `reasoning_effort` and the `thinking: {type: enabled}` body field
together — the API requires both to actually run in thinking mode.
"""
import json
import urllib.request
import urllib.error
from typing import Iterator


class DeepSeekProvider:
    name = "deepseek"
    default_model = "deepseek-v4-pro"
    default_effort = "max"
    valid_efforts = ("high", "max")
    supports_images = False
    key_env = "DEEPSEEK_API_KEY"
    key_file = "secrets/deepseek.key"
    endpoint = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is empty")
        self.api_key = api_key

    def stream(
        self,
        messages: list,
        model: str | None = None,
        effort: str | None = None,
    ) -> Iterator[dict]:
        """Yield events as dicts:
            {"type": "content",   "text": "..."}
            {"type": "reasoning", "text": "..."}
            {"type": "usage",     "data": {...}}
            {"type": "done"}
        Raises RuntimeError on API errors.
        """
        model = model or self.default_model
        effort = effort or self.default_effort
        if effort not in self.valid_efforts:
            raise ValueError(
                f"Invalid effort {effort!r} for DeepSeek; "
                f"expected one of {self.valid_efforts}"
            )

        body = {
            "model": model,
            "messages": messages,
            "reasoning_effort": effort,
            "thinking": {"type": "enabled"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {e.code}: {err_body}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"DeepSeek network error: {e.reason}") from None

        with resp:
            buf = b""
            while True:
                chunk = resp.read1(4096) if hasattr(resp, "read1") else resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    block, buf = buf.split(b"\n\n", 1)
                    yield from self._parse_sse_block(block.decode("utf-8", errors="replace"))
            if buf.strip():
                yield from self._parse_sse_block(buf.decode("utf-8", errors="replace"))

        yield {"type": "done"}

    @staticmethod
    def _parse_sse_block(block: str) -> Iterator[dict]:
        for line in block.splitlines():
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            if obj.get("usage"):
                yield {"type": "usage", "data": obj["usage"]}

            for choice in obj.get("choices", []) or []:
                delta = choice.get("delta") or {}
                rc = delta.get("reasoning_content")
                if rc:
                    yield {"type": "reasoning", "text": rc}
                c = delta.get("content")
                if c:
                    yield {"type": "content", "text": c}
