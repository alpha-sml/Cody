import pytest
from src.harness.recovery.recovery import RecoveryManager
from src.harness.recovery.classifier import classify_failure
from src.harness.state import State
from src.harness.model.base import BaseModelClient


class ScriptedModelClient(BaseModelClient):
    def __init__(self, actions):
        self.actions = list(actions)
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.actions:
            return self.actions.pop(0)
        return {"action": "finish", "result": "done"}


def test_failure_classification_categories():
    # 1. test failure
    c1 = classify_failure({"command": "pytest", "exit_code": 1, "stdout": "FAILED test_auth.py - AssertionError"})
    assert c1["category"] == "test_failure"

    # 2. syntax failure
    c2 = classify_failure({"exit_code": 1, "stderr": "SyntaxError: invalid syntax in file.py"})
    assert c2["category"] == "syntax_error"

    # 3. missing file
    c3 = classify_failure({"exit_code": 1, "stderr": "FileNotFoundError: [Errno 2] No such file or directory: 'foo.txt'"})
    assert c3["category"] == "file_error"

    # 4. dependency failure
    c4 = classify_failure({"command": "pip install foo", "exit_code": 1, "stderr": "No matching distribution found"})
    assert c4["category"] == "dependency_error"

    # 5. timeout
    c5 = classify_failure({"exit_code": -1, "error": "Command timed out"})
    assert c5["category"] == "timeout"


def test_recovery_prompt_includes_targeted_fields():
    model = ScriptedModelClient([{"action": "finish", "result": "fixed"}])
    rm = RecoveryManager(model)

    state = State(task="Fix auth bug", plan=["Step 1: Check login"])
    state.current_step = "Step 1: Check login"
    state.changed_files = ["src/auth.py"]
    state.tool_history = [{"tool": "file_write", "args": {"path": "src/auth.py"}, "result": {"status": "success"}}]

    action = rm.recover(
        state,
        failure_details={"command": "pytest", "exit_code": 1, "stderr": "AssertionError in auth.py"}
    )

    assert action["action"] == "finish"
    last_prompt = model.prompts[-1]
    assert "Failure Classification: test_failure" in last_prompt
    assert "Current Plan Step: Step 1: Check login" in last_prompt
    assert "src/auth.py" in last_prompt
    assert "Recent Tool Calls" in last_prompt


def test_repeated_identical_action_loop_prevention():
    # Model attempts identical tool call that previously failed
    repeated_call = {
        "action": "tool_call",
        "tool": "file_write",
        "arguments": {"path": "broken.py", "content": "bad"}
    }
    model = ScriptedModelClient([repeated_call, repeated_call])
    rm = RecoveryManager(model)

    state = State(task="Fix script")
    # Simulate that this exact action was in history and failed
    state.tool_history = [{
        "tool": "file_write",
        "args": {"path": "broken.py", "content": "bad"},
        "result": {"status": "error", "error": "Write failed"}
    }]

    failure = {"command": "file_write", "error": "Write failed"}

    from src.harness.tools.file_tools import FileWriteTool
    tool_schema = [FileWriteTool(".").schema()]

    # First recovery attempt records the failure
    rm.recover(state, failure, tools=tool_schema)

    # Second recovery attempt with exact same failure and exact same action is intercepted
    res = rm.recover(state, failure, tools=tool_schema)
    assert res["action"] == "error"
    assert res.get("error_type") == "repeated_action_loop_prevented"
