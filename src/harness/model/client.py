import os
import json
import re
import requests
from .base import BaseModelClient
from typing import List, Dict, Any, Optional

def extract_json(text: str) -> Dict[str, Any]:
    # Try markdown json blocks firs
    json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    for block in json_blocks:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue

    # Try to find the first '{' and parse up to the last valid '}'
    start_idx = text.find('{')
    if start_idx != -1:
        # Iterate backwards from the end to find the closing brace
        for i in range(len(text) - 1, start_idx - 1, -1):
            if text[i] == '}':
                try:
                    return json.loads(text[start_idx:i+1])
                except json.JSONDecodeError:
                    continue

    return {
        "action": "error",
        "error_type": "invalid_model_response",
        "message": "Failed to extract valid JSON action from model response.",
        "raw_response": text
    }

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": "SYSTEM: " + system_prompt}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {"contents": contents}

        try:
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
            if response.status_code == 200:
                data = response.json()
                try:
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    return extract_json(text)
                except (KeyError, IndexError):
                    return {"action": "error", "error_type": "model_api_error", "message": "Invalid response structure from API"}
            else:
                return {"action": "error", "error_type": "model_api_error", "message": f"API error: {response.status_code} {response.text}"}
        except requests.Timeout:
            return {"action": "error", "error_type": "model_api_timeout", "message": "API request timed out"}
        except Exception as e:
            return {"action": "error", "error_type": "model_api_error", "message": f"API exception: {str(e)}"}

def get_client(model_name: str) -> BaseModelClient:
    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true"
    if is_mock:
        return MockClient()

    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError("AI_API_KEY environment variable is not set")
    return GoogleClient(api_key, model_name)
