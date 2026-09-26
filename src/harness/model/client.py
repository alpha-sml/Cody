import os
from .base import BaseModelClient
from .providers import MockClient, DeepSeekClient, QwenClient

def get_client(model_name: str, provider: str = "deepseek") -> BaseModelClient:
    provider = provider.lower().strip()

    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true" or provider == "mock"
    if is_mock:
        return MockClient()

    if provider not in ("deepseek", "qwen"):
        raise ValueError(f"Unknown provider: {provider}")

    api_key = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError(f"{provider.upper()}_API_KEY or AI_API_KEY environment variable is not set")

    if provider == "deepseek":
        return DeepSeekClient(api_key, model_name)
    elif provider == "qwen":
        return QwenClient(api_key, model_name)
