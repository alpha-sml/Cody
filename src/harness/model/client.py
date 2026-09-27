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
    "deepseek": "deepseek-v4-flash",
    "qwen": "qwen-plus",
}


def validate_model_for_provider(model_name: str, provider: str) -> None:
    """Validate that model_name belongs to the specified provider's model family.

    Never silently substitute an arbitrary model for an invalid combination.
    """
    m_lower = model_name.lower().strip()
    if provider == "deepseek":
        if not m_lower.startswith("deepseek"):
            raise ValueError(
                f"Invalid model '{model_name}' for provider 'deepseek'. "
                f"Expected a deepseek model family member (e.g. deepseek-v4-flash, deepseek-chat)."
            )
    elif provider == "qwen":
        if not m_lower.startswith("qwen"):
            raise ValueError(
                f"Invalid model '{model_name}' for provider 'qwen'. "
                f"Expected a qwen model family member (e.g. qwen-plus, qwen-max, qwen-turbo)."
            )


def get_client(model_name: str = "", provider: str = "deepseek") -> BaseModelClient:
    # Allow env-var overrides for evaluator flexibility
    provider = os.environ.get("CODY_PROVIDER", provider).lower().strip()
    env_model = os.environ.get("CODY_MODEL", "").strip()
    if env_model:
        model_name = env_model
    else:
        model_name = model_name.strip()

    # Reject unsupported providers early so mock mode cannot mask invalid configurations
    if provider != "mock" and provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown provider: '{provider}'. Supported evaluation providers are: "
            f"{', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )

    # Locked evaluation mode enforcement
    locked_model = os.environ.get("CODY_LOCKED_MODEL", "").strip()
    if locked_model:
        if model_name and model_name != locked_model:
            raise ValueError(
                f"Attempted arbitrary model override '{model_name}' rejected: "
                f"evaluation model is locked to '{locked_model}'."
            )
        model_name = locked_model

    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true" or provider == "mock"
    if is_mock:
        return MockClient()

    # If model is omitted or empty, use provider default
    if not model_name and provider in DEFAULT_PROVIDER_MODELS:
        model_name = DEFAULT_PROVIDER_MODELS[provider]

    model_name = validate_model_name(model_name)
    validate_model_for_provider(model_name, provider)
    api_key = _resolve_api_key(provider)

    if provider == "deepseek":
        return DeepSeekClient(api_key, model_name)
    elif provider == "qwen":
        return QwenClient(api_key, model_name)
