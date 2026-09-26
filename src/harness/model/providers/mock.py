from typing import List, Dict, Any, Optional
from ..base import BaseModelClient
from ..boundary import validate_action

class MockClient(BaseModelClient):
    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Return deterministic responses based on prompt keywords for testing
        if "test_search" in prompt:
            return validate_action({"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "test"}}, tools=tools)
        elif "test_write" in prompt:
            return validate_action({"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "mock"}}, tools=tools)
        elif "test_read" in prompt:
            return validate_action({"action": "tool_call", "tool": "file_read", "arguments": {"path": "test.txt"}}, tools=tools)
        elif "test_shell" in prompt:
            return validate_action({"action": "tool_call", "tool": "shell", "arguments": {"command": "echo mock"}}, tools=tools)
        elif "recovery" in prompt.lower():
            return validate_action({"action": "tool_call", "tool": "shell", "arguments": {"command": "echo fixed"}}, tools=tools)
        return validate_action({"action": "finish", "result": "Mock finished"}, tools=tools)
