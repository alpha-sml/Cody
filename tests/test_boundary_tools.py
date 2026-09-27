import pytest
import os
from typing import List, Dict, Any, Optional, cast
import requests
from unittest.mock import patch
from src.harness.model.base import BaseModelClient
from src.harness.model.boundary import extract_json, validate_action
from src.harness.model.providers.mock import MockClient
from src.harness.model.providers.deepseek import DeepSeekClient
from src.harness.tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool, RepoTreeTool, ApplyPatchTool, safe_path
from src.harness.tools.shell import ShellTool
from src.harness.tools.git import GitStatusTool, GitDiffTool
from src.harness.verification.test_runner import TestRunner
from src.harness.verification.verifier import Verifier
from src.harness.tools.registry import ToolRegistry
from src.harness.planner import Planner
from src.harness.state import State
from src.harness.recovery.recovery import RecoveryManager

def test_extract_json_fences():
    # standard
    res = extract_json('```json\n{"action": "test"}\n```')
    assert res == {"action": "test"}

    # nested
    res2 = extract_json('some text\n{"action": "nested", "args": {"key": "value"}}\nend text')
    assert res2 == {"action": "nested", "args": {"key": "value"}}

    # braces inside strings
    res3 = extract_json('{"action": "string_brace", "message": "here is a { brace"}')
    assert res3 == {"action": "string_brace", "message": "here is a { brace"}

    # malformed
    res4 = extract_json('{"action": "malformed", "message": "unclosed string}')
    assert res4["action"] == "error"
    assert res4["error_type"] == "invalid_model_response"

def test_api_failure_behavior():
    client = DeepSeekClient("fake_key", "deepseek-flash")

    # 1. Timeout
    with patch("requests.post", side_effect=requests.Timeout):
        res = client.generate("test prompt")
        assert res["action"] == "error"
        assert res["error_type"] == "model_api_timeout"

    # 2. HTTP Error
    class MockResponse:
        status_code = 500
        text = "Internal Server Error"
    with patch("requests.post", return_value=MockResponse()):
        res = client.generate("test prompt")
        assert res["action"] == "error"
        assert "model_api_error" in res["error_type"]

    # 3. Valid JSON with tool call
    class MockValidResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"tool_calls": [{"type": "function", "function": {"name": "test", "arguments": "{}"}}]}}]
            }
    with patch("requests.post", return_value=MockValidResponse()):
        res = client.generate("test prompt")
        assert res["action"] == "tool_call"

    # 4. Invalid structure returned by model
    class MockInvalidResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"invalid_key": "here"}}]
            }
    with patch("requests.post", return_value=MockInvalidResponse()):
        res = client.generate("test prompt")
        assert res["action"] == "error"
        assert res["error_type"] == "model_api_error"

def test_mock_client_accepts_tools():
    client = MockClient()
    res = client.generate("test prompt", tools=[{"name": "test"}])
    assert res["action"] == "finish"

def test_tool_registry():
    registry = ToolRegistry()
    registry.register(ShellTool("."))
    schemas = registry.get_all_schemas()

    assert len(schemas) == 1
    assert schemas[0]["name"] == "shell"
    assert "parameters" in schemas[0]
    assert schemas[0]["parameters"]["type"] == "object"

def test_apply_patch(tmp_path):
    repo = str(tmp_path)
    file_path = os.path.join(repo, "test.txt")
    with open(file_path, "w") as f:
        f.write("Line 1\nLine 2\nLine 3\n")

    patch_content = """--- test.txt\n+++ test.txt\n@@ -1,3 +1,3 @@\n Line 1\n-Line 2\n+Line 2 changed\n Line 3\n"""
    tool = ApplyPatchTool(repo)
    res = tool.execute("test.txt", patch_content)
    assert res["status"] == "success"

    with open(file_path, "r") as f:
        content = f.read()
    assert "Line 2 changed" in content

def test_apply_patch_edge_cases(tmp_path):
    repo = str(tmp_path)
    tool = ApplyPatchTool(repo)

    # 1. Non-existent file
    res = tool.execute("missing.txt", "--- missing.txt\n+++ missing.txt\n@@ -1 +1 @@\n-a\n+b\n")
    assert res["status"] == "error"
    assert "does not exist" in res["error"]

    # 2. Path traversal
    res = tool.execute("../outside.txt", "patch")
    assert res["status"] == "error"
    assert "outside workspace" in res["error"]

    # 3. Malformed patch
    file_path = os.path.join(repo, "test2.txt")
    with open(file_path, "w") as f:
        f.write("Line 1\n")

    res = tool.execute("test2.txt", "this is not a valid patch format")
    assert res["status"] == "error"
    assert "Patch failed" in res["error"]

def test_shell_failure(tmp_path):
    tool = ShellTool(str(tmp_path))
    res = tool.execute("exit 1")
    assert res["status"] == "error"
    assert res["exit_code"] == 1

def test_verifier_structure(tmp_path):
    runner = TestRunner(str(tmp_path), test_command="echo 'test pass'")
    verifier = Verifier(runner, str(tmp_path))
    res = verifier.verify()

    assert "verified" in res
    assert "tests_passed" in res
    assert "exit_code" in res
    assert "stdout" in res
    assert "stderr" in res
    assert "changed_files" in res
    assert res["tests_passed"] is True

def test_tool_execution_integration(tmp_path):
    repo = str(tmp_path)

    # 1. Setup tool registry
    registry = ToolRegistry()
    registry.register(FileWriteTool(repo))
    registry.register(ApplyPatchTool(repo))
    registry.register(ShellTool(repo))

    # 2. Mock model that will return a patch tool call
    class IntegrationModel(MockClient):
        def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            return {
                "action": "tool_call",
                "tool": "apply_patch",
                "arguments": {
                    "path": "app.py",
                    "patch": "--- app.py\n+++ app.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"
                }
            }

    model = IntegrationModel()

    # 3. Create target file
    with open(os.path.join(repo, "app.py"), "w") as f:
        f.write("old\n")

    # 4. Agent simulates execution
    action = model.generate("test")
    assert action["action"] == "tool_call"

    tool = registry.get_tool(action["tool"])
    assert tool is not None
    res = tool.execute(**action["arguments"])
    assert res["status"] == "success"

    # 5. Verify file changed
    with open(os.path.join(repo, "app.py"), "r") as f:
        assert "new" in f.read()

    # 6. Verify via verifier
    runner = TestRunner(repo, test_command="echo 'tests pass'")
    verifier = Verifier(runner, repo)
    v_res = verifier.verify()
    assert v_res["verified"] is True
    assert v_res["tests_passed"] is True

def test_planner_validation():
    class BadPlannerModel(BaseModelClient):
        def __init__(self, action: str, result: Optional[str] = None):
            self.action = action
            self.result = result

        def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            if self.action == "string": return cast(Dict[str, Any], "just a string")
            if self.action == "empty": return {"action": "finish", "result": ""}
            if self.action == "error": return {"action": "error", "message": "boom"}
            if self.action == "bad_action": return {"action": "tool_call"}
            return {"action": "finish", "result": self.result}

    state = State(task="Test")

    # 1. string response
    planner = Planner(BadPlannerModel("string"))
    with pytest.raises(ValueError, match="expected a dictionary"):
        planner.update_plan(state)

    # 2. empty plan
    planner = Planner(BadPlannerModel("empty"))
    with pytest.raises(ValueError, match="missing valid 'result'"):
        planner.update_plan(state)

    # 3. error action
    planner = Planner(BadPlannerModel("error"))
    with pytest.raises(ValueError, match="boom"):
        planner.update_plan(state)

    # 4. bad action type
    planner = Planner(BadPlannerModel("bad_action"))
    with pytest.raises(ValueError, match="expected 'finish'"):
        planner.update_plan(state)

    # 5. valid
    planner = Planner(BadPlannerModel("valid", "1. Do this\n2. Do that"))
    plan = planner.update_plan(state)
    assert plan == ["1. Do this", "2. Do that"]

def test_model_validation():
    # finish missing result
    res = validate_action({"action": "finish"})
    assert res["action"] == "error"

    # tool_call missing tool
    res = validate_action({"action": "tool_call", "arguments": {}})
    assert res["action"] == "error"

    # tool_call empty tool
    res = validate_action({"action": "tool_call", "tool": "  ", "arguments": {}})
    assert res["action"] == "error"

    # tool_call arguments not dict
    res = validate_action({"action": "tool_call", "tool": "test", "arguments": []})
    assert res["action"] == "error"

def test_recovery_validation_extended():
    class CapturingModel(BaseModelClient):
        def __init__(self, return_val: Dict[str, Any]):
            self.return_val = return_val
            self.last_prompt: Optional[str] = None
            self.last_tools: Optional[List[Dict[str, Any]]] = None

        def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
            self.last_prompt = prompt
            self.last_tools = tools
            return self.return_val

    # 1. capture arguments
    model = CapturingModel({"action": "finish", "result": "done"})
    recovery = RecoveryManager(model)

    state = State(task="The Task", plan=["1", "2"])
    state.context = {"foo": "bar"}
    failure_details = {"error": "boom"}
    tools = [{"name": "fake_tool"}]

    recovery.recover(state, failure_details, tools=tools)

    assert model.last_prompt is not None
    assert "The Task" in model.last_prompt
    assert "['1', '2']" in model.last_prompt
    assert "foo" in model.last_prompt
    assert "boom" in model.last_prompt
    assert model.last_tools == tools

    # 2. recovery model returning {"action": "error", ...}
    model = CapturingModel({"action": "error", "error_type": "some_err", "message": "msg"})
    recovery = RecoveryManager(model)
    res = recovery.recover(state, {})
    assert res["action"] == "error"
    assert res["error_type"] == "some_err"

    # 3. malformed tool_call
    model = CapturingModel({"action": "tool_call", "tool": ""})
    recovery = RecoveryManager(model)
    res = recovery.recover(state, {})
    assert res["action"] == "error"
    assert res["error_type"] == "invalid_model_action"

    # 4. malformed finish
    model = CapturingModel({"action": "finish"})
    recovery = RecoveryManager(model)
    res = recovery.recover(state, {})
    assert res["action"] == "error"
    assert res["error_type"] == "invalid_model_action"

    # 5. valid recovery tool_call
    model = CapturingModel({"action": "tool_call", "tool": "fix", "arguments": {}})
    recovery = RecoveryManager(model)
    res = recovery.recover(state, {})
    assert res["action"] == "tool_call"

    # 6. valid recovery finish
    model = CapturingModel({"action": "finish", "result": "done"})
    recovery = RecoveryManager(model)
    res = recovery.recover(state, {})
    assert res["action"] == "finish"
