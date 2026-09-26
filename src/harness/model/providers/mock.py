import json
from typing import List, Dict, Any, Optional
from ..base import BaseModelClient
from ..boundary import validate_action


class MockClient(BaseModelClient):
    def __init__(self):
        self._step = 0

    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        prompt_lower = prompt.lower()

        # 1. Planner requests (no tools provided, or explicitly asking for a plan)
        if tools is None or "step-by-step plan" in prompt_lower or "structured plan" in prompt_lower:
            plan_data = {
                "goal": "Resolve task",
                "steps": [
                    {"id": "1", "description": "Inspect repository and verify solution", "files": [], "verification": ["make test"]}
                ]
            }
            return {"action": "finish", "result": json.dumps(plan_data)}

        # 2. Specific test keyword overrides (when unit tests explicitly check tool calling)
        if "test_search" in prompt and ("pattern" in prompt_lower or len(prompt) < 150):
            return validate_action({"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "test"}}, tools=tools)
        elif "test_write" in prompt and ("content" in prompt_lower or len(prompt) < 150):
            return validate_action({"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "mock"}}, tools=tools)
        elif "test_read" in prompt and len(prompt) < 150:
            return validate_action({"action": "tool_call", "tool": "file_read", "arguments": {"path": "test.txt"}}, tools=tools)
        elif "test_shell" in prompt and len(prompt) < 150:
            return validate_action({"action": "tool_call", "tool": "shell", "arguments": {"command": "echo mock"}}, tools=tools)

        # 3. Recovery prompt handling
        if "an operation failed" in prompt_lower or "recovery guidance" in prompt_lower:
            return validate_action({"action": "finish", "result": "Corrected and verified"}, tools=tools)

        # 4. Multi-step autonomous execution sequence for evaluator flow
        if self._step == 0:
            self._step += 1
            available_tool_names = [t.get("name") for t in tools] if tools else []
            if "git_status" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "git_status", "arguments": {}}, tools=tools)
            elif "file_search" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "test"}}, tools=tools)
            elif "file_read" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "file_read", "arguments": {"path": "README.md"}}, tools=tools)

        return validate_action({"action": "finish", "result": "Task completed and verified successfully."}, tools=tools)

