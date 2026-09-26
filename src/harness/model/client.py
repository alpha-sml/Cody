import os
from .base import BaseModelClient
from typing import List, Dict, Any

class MockClient(BaseModelClient):
    def generate(self, prompt: str, tools: List[Dict[str, Any]] = None) -> str:
        return "MOCK_RESPONSE"

class GoogleClient(BaseModelClient):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, tools: List[Dict[str, Any]] = None) -> str:
        # Implement actual API call here
        return f"Response from {self.model_name}"

def get_client(model_name: str) -> BaseModelClient:
    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true"
    if is_mock:
        return MockClient()
    
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError("AI_API_KEY environment variable is not set")
    return GoogleClient(api_key, model_name)
