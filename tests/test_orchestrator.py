import subprocess
import pytest
from src.harness.orchestrator import Orchestrator
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.tools.base import BaseTool
from src.harness.tools.file_tools import FileReadTool, FileSearchTool, FileWriteTool, RepoTreeTool
from src.harness.tools.git import GitDiffTool, GitStatusTool

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


class CountingModel(BaseModelClient):
    def __init__(self, actions):
        self.actions = list(actions)
        self.plan_calls = 0
        self.execution_calls = 0
        self.recovery_calls = 0
        self.prompts = []

    def generate(self, prompt, system_prompt=None, tools=None):
        self.prompts.append(prompt)
        if "Provide a step-by-step plan" in prompt:
            self.plan_calls += 1
            return {"action": "finish", "result": "inspect, then update the target"}
        if "Failure Classification:" in prompt:
            self.recovery_calls += 1
        else:
            self.execution_calls += 1
        if self.actions:
            return self.actions.pop(0)
        return {"action": "finish", "result": "done"}


class TracePlanner(Planner):
    def __init__(self, model_client, trace):
        super().__init__(model_client)
        self.trace = trace

    def update_plan(self, state):
        self.trace.append(("planner", state.phase))
        return super().update_plan(state)


class TraceOrchestrator(Orchestrator):
    def __init__(self, *args, trace, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace = trace

    def _handle_action(self, action, state):
        before = state.phase
        super()._handle_action(action, state)
        action_name = action.get("action") if isinstance(action, dict) else type(action).__name__
        tool_name = action.get("tool") if isinstance(action, dict) else None
        self.trace.append(("action", tool_name or action_name, before, state.phase))

class MockPlanner(Planner):
    def update_plan(self, state):
        return ["mock plan step"]


class FailingPlanner(Planner):
    def __init__(self, model_client, message="planner failed"):
        super().__init__(model_client)
        self.message = message
        self.calls = 0

    def update_plan(self, state):
        self.calls += 1
        raise ValueError(self.message)

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


def test_normal_success_call_sequence_keeps_planner_context():
    model = CountingModel([{"action": "finish", "result": "completed"}])
    registry = ToolRegistry()
    registry.register(MockTool())
    class RepoTreeMock(MockTool):
        name = "repo_tree"
    registry.register(RepoTreeMock())
    verifier = MockVerifier()
    orchestrator = Orchestrator(
        model,
        registry,
        verifier,
        RecoveryManager(model),
        ContextManager(),
        Planner(model),
    )

    final_state = orchestrator.run(State(task="Test"))

    assert final_state.status == "success"
    assert model.plan_calls == 1
    assert model.execution_calls == 1
    assert model.recovery_calls == 0
    assert len(model.prompts) == 2
    assert "inspect, then update the target" in model.prompts[1]


def test_evaluation_report_records_run_evidence():
    model = CountingModel([{"action": "tool_call", "tool": "file_write", "arguments": {}}])
    registry = ToolRegistry()
    registry.register(MockTool())
    class RepoTreeMock(MockTool):
        name = "repo_tree"
    class FileWriteMock(MockTool):
        name = "file_write"
    registry.register(RepoTreeMock())
    registry.register(FileWriteMock())
    verifier = MockVerifier(changed_files=["changed.py"])
    state = State(
        task="Change a file",
        evaluation_report={"model_provider": "mock", "model_name": "test-model"},
    )
    orchestrator = Orchestrator(
        model,
        registry,
        verifier,
        RecoveryManager(model),
        ContextManager(),
        Planner(model),
    )

    final_state = orchestrator.run(state)

    report = final_state.evaluation_report
    assert report["final_status"] == "success"
    assert report["model_provider"] == "mock"
    assert report["model_name"] == "test-model"
    assert report["model_calls"] == {"planner": 1, "execution": 1, "recovery": 0}
    assert report["model_call_count"] == 2
    assert report["tool_calls"] == 1
    assert report["verification_attempts"] == 1
    assert report["recovery_attempts"] == 0
    assert report["changed_files"] == ["changed.py"]
    assert report["completion_status"] == "VERIFIED_SUCCESS"
    assert report["test_result"]["tests_passed"] is True


def test_recovery_call_sequence_adds_one_model_call_per_recovery():
    model = CountingModel([
        {"action": "finish", "result": "initial"},
        {"action": "finish", "result": "retry"},
    ])
    registry = ToolRegistry()
    registry.register(MockTool())
    class RepoTreeMock(MockTool):
        name = "repo_tree"
    registry.register(RepoTreeMock())
    verifier = MockVerifier(succeed_on_call=2)
    orchestrator = Orchestrator(
        model,
        registry,
        verifier,
        RecoveryManager(model),
        ContextManager(),
        Planner(model),
    )

    final_state = orchestrator.run(State(task="Test"))

    assert final_state.status == "success"
    assert model.plan_calls == 1
    assert model.execution_calls == 1
    assert model.recovery_calls == 1
    assert len(model.prompts) == 3


@pytest.mark.parametrize(
    ("informational_tools", "expected_tools"),
    [
        (["file_search", "file_read"], ["file_search", "file_read", "file_write"]),
        (["file_read"], ["file_read", "file_write"]),
        (["git_status"], ["git_status", "file_write"]),
        (["git_diff"], ["git_diff", "file_write"]),
    ],
)
def test_informational_tools_continue_execution_with_updated_context(
    tmp_path, informational_tools, expected_tools
):
    repo = str(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "probe@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Probe"], cwd=repo, check=True)
    (tmp_path / "target.txt").write_text("before\n")
    subprocess.run(["git", "add", "target.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
    if "git_diff" in informational_tools:
        (tmp_path / "target.txt").write_text("preexisting diff\n")

    actions = []
    for tool_name in informational_tools:
        arguments = {"pattern": "before"} if tool_name == "file_search" else {}
        if tool_name == "file_read":
            arguments = {"path": "target.txt"}
        actions.append({"action": "tool_call", "tool": tool_name, "arguments": arguments})
    actions.append({"action": "tool_call", "tool": "file_write", "arguments": {"path": "target.txt", "content": "after\n"}})

    model = CountingModel(actions)
    trace = []
    registry = ToolRegistry()
    registry.register(RepoTreeTool(repo))
    registry.register(FileReadTool(repo))
    registry.register(FileSearchTool(repo))
    registry.register(FileWriteTool(repo))
    registry.register(GitStatusTool(repo))
    registry.register(GitDiffTool(repo))
    verifier = MockVerifier()
    orchestrator = TraceOrchestrator(
        model,
        registry,
        verifier,
        RecoveryManager(model),
        ContextManager(),
        TracePlanner(model, trace),
        trace=trace,
    )

    state = orchestrator.run(State(task="Update target.txt", repo_path=repo))

    assert state.status == "success"
    assert state.verification_results[0]["completion_status"] == "VERIFIED_SUCCESS"
    assert model.plan_calls == 1
    assert model.execution_calls == len(expected_tools)
    assert model.recovery_calls == 0
    assert [entry[1] for entry in trace if entry[0] == "action"] == expected_tools
    assert trace[0] == ("planner", "PLAN")
    assert all(entry[2] == "EXECUTE_ACTION" for entry in trace if entry[0] == "action")
    assert trace[-1][3] == "VERIFY"

    context_markers = {
        "file_search": "file_search",
        "file_read": "target.txt",
        "git_status": "git_status",
        "git_diff": "git_diff",
    }
    for index, tool_name in enumerate(informational_tools, start=2):
        assert context_markers[tool_name] in model.prompts[index]

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


def test_planner_value_error_is_recorded_and_enters_controlled_recovery():
    orch, model = setup_orchestrator([{"action": "finish", "result": "recovered"}])
    planner = FailingPlanner(model, "malformed planner response")
    orch.planner = planner

    final_state = orch.run(State(task="Test"))

    assert final_state.status == "success"
    assert final_state.recovery_attempts == 1
    assert final_state.iteration == 1
    assert "Planner update failed: malformed planner response" in final_state.errors
    assert "Planner update failed: malformed planner response" in orch.context_manager.errors
    assert planner.calls == 1


def test_repeated_planner_failures_respect_recovery_limit():
    orch, model = setup_orchestrator(
        [{"action": "error", "message": "recovery unavailable"}] * 3,
        max_recovery=2,
    )
    planner = FailingPlanner(model)
    orch.planner = planner

    final_state = orch.run(State(task="Test"))

    assert final_state.status == "failed"
    assert final_state.final_result == "Max recovery attempts reached."
    assert final_state.recovery_attempts == 2
    assert final_state.iteration == 2
    assert planner.calls == 3
    assert final_state.errors.count("Planner update failed: planner failed") == 3
