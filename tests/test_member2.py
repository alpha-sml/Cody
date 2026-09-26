import pytest
import os
from src.harness.model.client import extract_json, MockClient, GoogleClient
from src.harness.tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool, RepoTreeTool, ApplyPatchTool, safe_path
from src.harness.tools.shell import ShellTool
from src.harness.tools.git import GitStatusTool, GitDiffTool
from src.harness.verification.test_runner import TestRunner
from src.harness.verification.verifier import Verifier
from src.harness.tools.registry import ToolRegistry

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
    client = GoogleClient("fake_key", "gemini-pro")
    # This should fail and return a structured error, not "finish"
    res = client.generate("test prompt")
    assert res["action"] == "error"
    assert "model_api_" in res["error_type"]

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

    patch = """--- test.txt
+++ test.txt
@@ -1,3 +1,3 @@
 Line 1
-Line 2
+Line 2 changed
 Line 3
"""
    tool = ApplyPatchTool(repo)
    res = tool.execute("test.txt", patch)
    assert res["status"] == "success"

    with open(file_path, "r") as f:
        content = f.read()
    assert "Line 2 changed" in content

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

def test_member2_integration(tmp_path):
    repo = str(tmp_path)

    # 1. Setup tool registry
    registry = ToolRegistry()
    registry.register(FileWriteTool(repo))
    registry.register(ApplyPatchTool(repo))
    registry.register(ShellTool(repo))

    # 2. Mock model that will return a patch tool call
    class IntegrationModel(MockClient):
        def generate(self, prompt, system_prompt=None, tools=None):
            return {
                "action": "tool_call",
                "tool": "apply_patch",
                "arguments": {
                    "path": "app.py",
                    "patch": "--- app.py\n+++ app.py\n@@ -1,1 +1,1 @@\n-old\n+new"
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
