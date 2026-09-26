import os
import json
import re
import requests
from .base import BaseModelClient
from typing import List, Dict, Any, Optional

def extract_json(text: str) -> Dict[str, Any]:
    # Robust json extraction using regex
    try:
        matches = re.finditer(r'\{(?:[^{}]|(?R))*\}', text)
        # Using a simpler regex that matches { ... } broadly, then loads.
        # Since Python re doesn't have recursive matching (?R), we just find outer braces manually
        stack = []
        start = -1
        last_json = None
        for i, char in enumerate(text):
            if char == '{':
                if not stack:
                    start = i
                stack.append(char)
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack:
                        try:
                            last_json = json.loads(text[start:i+1])
                        except:
                            pass
        if last_json:
            return last_json
    except Exception:
        pass
    
    # Fallback to simple outer braces
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end >= start:
            return json.loads(text[start:end+1])
    except:
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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": "SYSTEM: " + system_prompt}]})
        
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        
        payload = {"contents": contents}
        
        try:
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if response.status_code == 200:
                data = response.json()
                try:
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    return extract_json(text)
                except (KeyError, IndexError):
                    return {"action": "finish", "result": "API error: Invalid response structure"}
            else:
                return {"action": "finish", "result": f"API error: {response.status_code} {response.text}"}
        except Exception as e:
            return {"action": "finish", "result": f"API exception: {str(e)}"}

def get_client(model_name: str) -> BaseModelClient:
    is_mock = os.environ.get("MOCK_MODEL", "false").lower() == "true"
    if is_mock:
        return MockClient()
    
    api_key = os.environ.get("AI_API_KEY")
    if not api_key:
        raise ValueError("AI_API_KEY environment variable is not set")
    return GoogleClient(api_key, model_name)
