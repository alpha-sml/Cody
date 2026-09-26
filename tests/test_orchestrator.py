import pytest
from src.harness.orchestrator import Orchestrator
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.tools.base import BaseTool

class MockTool(BaseTool):
    name = "mock_tool"
    description = "Mock tool"
    def __init__(self, succeed=True):
        self.succeed = succeed
    def execute(self, **kwargs):
        if self.succeed:
            return self.success_result(changed="yes")
        else:
            return self.error_result("Mock tool failed")
    def get_parameters_schema(self):
        return {"type": "object", "properties": {}}

class MockVerifier:
    def __init__(self, succeed_on_call=1, changed_files=None):
        self.calls = 0
        self.succeed_on_call = succeed_on_call
        self.changed_files = changed_files or []
    def verify(self):
        self.calls += 1
        if self.calls >= self.succeed_on_call:
            return {"verified": True, "tests_passed": True, "changed_files": self.changed_files}
        return {"verified": False, "tests_passed": False, "error": "tests failed", "changed_files": self.changed_files}

class MockModel(BaseModelClient):
    def __init__(self, actions):
        self.actions = actions
        self.call_count = 0
        self.received_tools = None

    def generate(self, prompt, system_prompt=None, tools=None):
        self.received_tools = tools
        if self.call_count < len(self.actions):
            action = self.actions[self.call_count]
            self.call_count += 1
            return action
        return {"action": "finish", "result": "default finish"}

class MockPlanner(Planner):
    def update_plan(self, state):
        return ["mock plan step"]

def setup_orchestrator(model_actions, verifier_succeed_on=1, max_iterations=15, max_recovery=2, tool_succeeds=True):
    model = MockModel(model_actions)
    registry = ToolRegistry()
    registry.register(MockTool(succeed=tool_succeeds))

    # We also need file_write for the orchestrator to trigger VERIFY from a tool_call
    class FileWriteMock(MockTool):
        name = "file_write"
    registry.register(FileWriteMock(succeed=tool_succeeds))

    class RepoTreeMock(MockTool):
        name = "repo_tree"
    registry.register(RepoTreeMock())

    verifier = MockVerifier(succeed_on_call=verifier_succeed_on)
    recovery = RecoveryManager(model)
    context_mgr = ContextManager()
    planner = MockPlanner(model)

    return Orchestrator(model, registry, verifier, recovery, context_mgr, planner, max_iterations, max_recovery), model

def test_successful_finish():
    # Model immediately finishes. Verifier passes on 1st try.
    orch, model = setup_orchestrator([{"action": "finish", "result": "Done"}], verifier_succeed_on=1)
    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "success"
    assert final_state.final_result == "Done"
    assert model.received_tools is not None
    assert len(model.received_tools) > 0

def test_finish_with_recovery():
    # Model finishes -> verifier fails -> recover with tool -> verifier passes
    orch, model = setup_orchestrator([
        {"action": "finish", "result": "First try"},
        # Recovery model call returns a tool_call
        {"action": "tool_call", "tool": "file_write", "arguments": {}},
    ], verifier_succeed_on=2)

    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "success"
    assert state.recovery_attempts == 1
    assert state.iteration == 2


def test_changed_files_are_copied_from_verifier():
    orch, model = setup_orchestrator([{"action": "finish", "result": "Done"}])
    orch.verifier.changed_files = ["src/changed.py", "tests/changed.py"]

    final_state = orch.run(State(task="Test"))

    assert final_state.status == "success"
    assert final_state.changed_files == ["src/changed.py", "tests/changed.py"]

def test_model_error():
    orch, model = setup_orchestrator([{"action": "error", "error_type": "api", "message": "API down"}] * 10, max_iterations=5)
    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "failed"
    assert len(state.errors) > 0
    assert "API down" in state.errors[0]

def test_tool_execution_error():
    orch, model = setup_orchestrator([
        {"action": "tool_call", "tool": "mock_tool", "arguments": {}},
    ] * 10, tool_succeeds=False, max_iterations=5)

    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "failed"
    assert len(state.errors) > 0
    assert "Mock tool failed" in state.errors[0]

def test_max_recovery():
    # Verifier NEVER passes, max recovery = 2
    orch, model = setup_orchestrator([
        {"action": "finish", "result": "Try 1"},
        {"action": "finish", "result": "Recover 1"},
        {"action": "finish", "result": "Recover 2"},
        {"action": "finish", "result": "Recover 3"}
    ], verifier_succeed_on=99, max_recovery=2)

    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "failed"
    assert state.recovery_attempts == 2
    assert "Max recovery attempts reached" in final_state.final_result

def test_max_iterations():
    # Model keeps outputting tool_calls that don't trigger VERIFY (mock_tool is not file_write/shell/patch)
    orch, model = setup_orchestrator([
        {"action": "tool_call", "tool": "mock_tool", "arguments": {}}
    ] * 10, max_iterations=3)

    state = State(task="Test")
    final_state = orch.run(state)

    assert final_state.status == "failed"
    assert final_state.iteration == 3
    assert "Max iterations reached" in final_state.final_result


def test_malformed_model_action_returns_to_plan_with_context_error():
    orch, model = setup_orchestrator([None, {"action": "finish", "result": "Done"}])

    final_state = orch.run(State(task="Test"))

    assert final_state.status == "success"
    assert "Invalid model action" in final_state.errors
    assert "Invalid model action" in orch.context_manager.errors


def test_repo_tree_failure_is_recorded_and_does_not_crash():
    orch, model = setup_orchestrator([{"action": "finish", "result": "Done"}])
    repo_tree = orch.tool_registry.get_tool("repo_tree")
    repo_tree.succeed = False

    final_state = orch.run(State(task="Test"))

    assert final_state.status == "success"
    assert "Mock tool failed" in final_state.errors
    assert "Mock tool failed" in orch.context_manager.errors
