import os
import json
from .base import BaseModelClient
from typing import List, Dict, Any, Optional

def extract_json(text: str) -> Dict[str, Any]:
    # Robust json extraction
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end >= start:
            return json.loads(text[start:end+1])
    except Exception:
        pass
    return {"action": "finish", "result": "Failed to parse json", "raw_response": text}

class MockClient(BaseModelClient):
    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Return deterministic responses based on prompt keywords for testing
        if "test_search" in prompt:
            return {"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "test"}}
        elif "test_write" in prompt:
            return {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "mock"}}
        elif "test_read" in prompt:
            return {"action": "tool_call", "tool": "file_read", "arguments": {"path": "test.txt"}}
        elif "test_shell" in prompt:
            return {"action": "tool_call", "tool": "shell", "arguments": {"command": "echo mock"}}
        elif "recovery" in prompt.lower():
            return {"action": "tool_call", "tool": "shell", "arguments": {"command": "echo fixed"}}
        return {"action": "finish", "result": "Mock finished"}

class GoogleClient(BaseModelClient):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Mocking actual API call since we can't really make one in this hackathon scaffold
        # Assume an actual API call is made and a string is returned
        response_text = '{"action": "finish", "result": "Implement real API call here"}'
        return extract_json(response_text)

def get_client(model_name: str) -> BaseModelClient:
    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true"
    if is_mock:
        return MockClient()
    
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError("AI_API_KEY environment variable is not set")
    return GoogleClient(api_key, model_name)
