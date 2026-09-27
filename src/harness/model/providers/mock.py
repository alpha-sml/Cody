import json
import re
from typing import List, Dict, Any, Optional
from ..base import BaseModelClient
from ..boundary import validate_action


class MockClient(BaseModelClient):
    def __init__(self):
        self._step = 0

    def _resolve_target_file(self, prompt: str) -> Optional[str]:
        task_match = re.search(r"Task:\s*(.*)", prompt)
        text_to_search = task_match.group(1) if task_match else prompt
        text_lower = text_to_search.lower()

        m = re.findall(r'\b(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|js|ts|json|md|txt|sh)\b', text_to_search)
        candidates = [f for f in m if f not in ("config.yaml", "config.yml", "requirements.txt") and not f.startswith(("tests/", "n/", "/"))]
        if candidates:
            return candidates[0]

        mutating_words = {"fix", "add", "implement", "update", "modify", "create", "refactor"}
        is_mutating = bool(set(re.findall(r'\b[a-z]+\b', text_lower)) & mutating_words)
        if is_mutating:
            if "auth" in text_lower:
                return "auth.py"
            return "solution.py"
        return None

    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        prompt_lower = prompt.lower()

        # 1. Planner requests (no tools provided, or explicitly asking for a plan)
        if tools is None or "step-by-step plan" in prompt_lower or "structured plan" in prompt_lower:
            target = self._resolve_target_file(prompt)
            files = [target] if target else []
            plan_data = {
                "goal": "Resolve task",
                "steps": [
                    {"id": "1", "description": "Implement task changes and verify solution", "files": files, "verification": ["make test"]}
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

        available_tool_names = [t.get("name") for t in tools] if tools else []

        # 3. Recovery prompt handling
        if "an operation failed" in prompt_lower or "recovery guidance" in prompt_lower:
            if ("meaningful" in prompt_lower or "required_files" in prompt_lower or "no_meaningful_change" in prompt_lower) and "file_write" in available_tool_names:
                target = self._resolve_target_file(prompt) or "solution.py"
                return validate_action({"action": "tool_call", "tool": "file_write", "arguments": {"path": target, "content": "# Fixed during recovery\n"}}, tools=tools)
            return validate_action({"action": "finish", "result": "Corrected and verified"}, tools=tools)

        # 4. Multi-step autonomous execution sequence for evaluator flow
        if self._step == 0:
            self._step += 1
            target_file = self._resolve_target_file(prompt)

            mutating_words = {"fix", "add", "implement", "update", "modify", "create", "refactor"}
            is_mutating = bool(set(re.findall(r'\b[a-z]+\b', prompt_lower)) & mutating_words)

            if target_file and is_mutating and "file_write" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "file_write", "arguments": {"path": target_file, "content": "# Implemented by MockClient\n"}}, tools=tools)
            elif "git_status" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "git_status", "arguments": {}}, tools=tools)
            elif "file_search" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "test"}}, tools=tools)
            elif "file_read" in available_tool_names:
                return validate_action({"action": "tool_call", "tool": "file_read", "arguments": {"path": "README.md"}}, tools=tools)

        return validate_action({"action": "finish", "result": "Task completed and verified successfully."}, tools=tools)
