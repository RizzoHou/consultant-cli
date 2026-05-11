"""Capability tags.

A tag bundles `(provider, model, effort)` so callers — especially Claude Code
skills — address a capability ("reasoning", "chinese", "vision") instead of a
specific API + model id. Retargeting a tag is a one-line edit here; skills and
docs that reference the tag keep working unchanged.
"""

TAGS = {
    "reasoning": {"provider": "openrouter", "model": "openai/gpt-5.5",  "effort": "xhigh"},
    "vision":    {"provider": "openrouter", "model": "openai/gpt-5.5",  "effort": "high"},
    "chinese":   {"provider": "deepseek",   "model": "deepseek-v4-pro", "effort": "max"},
}

DEFAULT_TAG = "reasoning"


def resolve_tag(name: str) -> dict:
    if name not in TAGS:
        raise ValueError(
            f"Unknown tag {name!r}. Available: {', '.join(sorted(TAGS))}"
        )
    return dict(TAGS[name])
