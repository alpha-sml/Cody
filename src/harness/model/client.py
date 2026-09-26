import os
from .base import BaseModelClient
from .providers import MockClient, DeepSeekClient, QwenClient

def get_client(model_name: str, provider: str = "deepseek") -> BaseModelClient:
    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true"
    if is_mock:
        return MockClient()

    api_key = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError(f"AI_API_KEY or {provider.upper()}_API_KEY environment variable is not set")

    if provider == "deepseek":
        return DeepSeekClient(api_key, model_name)
    elif provider == "qwen":
        return QwenClient(api_key, model_name)
    else:
        raise ValueError(f"Unknown provider: {provider}")
