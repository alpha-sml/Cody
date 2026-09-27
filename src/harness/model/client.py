import os
from .base import BaseModelClient
from .providers import MockClient, DeepSeekClient, QwenClient

# Known valid models per provider. Used for placeholder detection only —
# any non-placeholder string is accepted to allow committee-prescribed models.
_PLACEHOLDER_PATTERN = "<"


def _resolve_api_key(provider: str) -> str:
    """Resolve API key with AI_API_KEY as primary (evaluator interface).

    Priority:
      1. AI_API_KEY  (official evaluation credential)
      2. <PROVIDER>_API_KEY  (local development convenience)
    """
    ai_key = os.environ.get("AI_API_KEY", "").strip()
    if ai_key:
        return ai_key

    provider_key = os.environ.get(f"{provider.upper()}_API_KEY", "").strip()
    if provider_key:
        return provider_key

    raise ValueError(
        f"No API key found. Set AI_API_KEY (preferred) or {provider.upper()}_API_KEY."
    )


def validate_model_name(model_name: str) -> str:
    """Reject placeholder model names that would cause silent failures."""
    if not model_name or not model_name.strip():
        raise ValueError("Model name is empty. Set model.name in config/config.yaml or use --model / CODY_MODEL env var.")
    if _PLACEHOLDER_PATTERN in model_name:
        raise ValueError(
            f"Model name '{model_name}' looks like an unresolved placeholder. "
            f"Set the actual model name in config/config.yaml, --model flag, or CODY_MODEL env var."
        )
    return model_name.strip()


SUPPORTED_PROVIDERS = frozenset(["deepseek", "qwen"])

DEFAULT_PROVIDER_MODELS = {
    "deepseek": "deepseek-chat",
    "qwen": "qwen-plus",
}


def get_client(model_name: str, provider: str = "deepseek") -> BaseModelClient:
    # Allow env-var overrides for evaluator flexibility
    provider = os.environ.get("CODY_PROVIDER", provider).lower().strip()
    model_name = os.environ.get("CODY_MODEL", model_name).strip()

    # Reject unsupported providers early so mock mode cannot mask invalid configurations
    if provider != "mock" and provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown provider: '{provider}'. Evaluation is restricted to approved providers: "
            f"{', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )

    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true" or provider == "mock"
    if is_mock:
        return MockClient()

    # Automatically use provider default if model name was not explicitly overridden
    if provider == "qwen" and (not model_name or model_name == DEFAULT_PROVIDER_MODELS["deepseek"]):
        model_name = DEFAULT_PROVIDER_MODELS["qwen"]
    elif not model_name and provider in DEFAULT_PROVIDER_MODELS:
        model_name = DEFAULT_PROVIDER_MODELS[provider]

    model_name = validate_model_name(model_name)
    api_key = _resolve_api_key(provider)

    if provider == "deepseek":
        return DeepSeekClient(api_key, model_name)
    elif provider == "qwen":
        return QwenClient(api_key, model_name)
