"""OpenRouter provider.

Uses the OpenAI-compatible Chat Completions endpoint at openrouter.ai. Reasoning
on OpenRouter is controlled via the unified `reasoning` object (not DeepSeek's
`reasoning_effort` + `thinking` pair). Streamed reasoning tokens arrive as
either `delta.reasoning` (string passthrough) or `delta.reasoning_details`
(array of `{type, text, ...}` objects) — handle both.
"""
import json
import urllib.request
import urllib.error
from typing import Iterator


class OpenRouterProvider:
    name = "openrouter"
    default_model = "openai/gpt-5.5"
    default_effort = "xhigh"
    valid_efforts = ("minimal", "low", "medium", "high", "xhigh")
    supports_images = True
    key_env = "OPENROUTER_API_KEY"
    key_file = "secrets/openrouter.key"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenRouter API key is empty")
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
                f"Invalid effort {effort!r} for OpenRouter; "
                f"expected one of {self.valid_efforts}"
            )

        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "reasoning": {"effort": effort, "enabled": True},
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
            raise RuntimeError(f"OpenRouter HTTP {e.code}: {err_body}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"OpenRouter network error: {e.reason}") from None

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
            # OpenRouter sends SSE comments (e.g. ": OPENROUTER PROCESSING") as
            # keepalives; they start with ":" and never parse as JSON.
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            if obj.get("usage"):
                yield {"type": "usage", "data": obj["usage"]}

            for choice in obj.get("choices", []) or []:
                delta = choice.get("delta") or {}

                # String passthrough form (some OpenAI / Anthropic routes).
                r = delta.get("reasoning")
                if isinstance(r, str) and r:
                    yield {"type": "reasoning", "text": r}

                # Structured form (gpt-5.x via OpenRouter's unified API).
                details = delta.get("reasoning_details") or []
                for item in details:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "reasoning.text":
                        continue
                    t = item.get("text")
                    if isinstance(t, str) and t:
                        yield {"type": "reasoning", "text": t}

                c = delta.get("content")
                if isinstance(c, str) and c:
                    yield {"type": "content", "text": c}
