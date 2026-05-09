"""Provider registry. Add a new provider by registering its class here."""
from .deepseek import DeepSeekProvider

PROVIDERS = {
    DeepSeekProvider.name: DeepSeekProvider,
}

DEFAULT_PROVIDER = DeepSeekProvider.name


def get_provider_class(name: str):
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider {name!r}. Available: {', '.join(sorted(PROVIDERS))}"
        )
    return PROVIDERS[name]
