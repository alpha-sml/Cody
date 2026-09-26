import os
import subprocess
from src.harness.state import State
from src.harness.model.client import MockClient
from src.harness.tools.registry import ToolRegistry
from src.harness.tools.file_tools import ApplyPatchTool, FileReadTool, FileWriteTool, FileSearchTool, RepoTreeTool
from src.harness.tools.shell import ShellTool
from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.orchestrator import Orchestrator


class PipelineModel(MockClient):
    def __init__(self, actions):
        self.actions = list(actions)
        self.action_count = 0

    def generate(self, prompt, system_prompt=None, tools=None):
        if "Provide a step-by-step plan" in prompt:
            return {"action": "finish", "result": "plan"}
        action = self.actions[self.action_count] if self.action_count < len(self.actions) else {"action": "finish", "result": "done"}
        self.action_count += 1
        return action


class SequenceRunner(TestRunner):
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def run_tests(self):
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return result


def run_git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def initialize_git_repo(repo):
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")


def build_pipeline(repo, actions, test_results, max_iterations=15, max_recovery_attempts=3):
    model = PipelineModel(actions)
    registry = ToolRegistry()
    registry.register(RepoTreeTool(repo))
    registry.register(FileReadTool(repo))
    registry.register(FileWriteTool(repo))
    registry.register(FileSearchTool(repo))
    registry.register(ApplyPatchTool(repo))
    registry.register(ShellTool(repo))
    verifier = Verifier(SequenceRunner(test_results), repo)
    recovery = RecoveryManager(model)
    context = ContextManager()
    planner = Planner(model)
    orchestrator = Orchestrator(
        model,
        registry,
        verifier,
        recovery,
        context,
        planner,
        max_iterations=max_iterations,
        max_recovery_attempts=max_recovery_attempts,
    )
    return orchestrator, model, verifier

def test_full_integration(tmp_path):
    repo = str(tmp_path)
    
    # Mock model designed to succeed at first, fail test, recover, and succeed
    class IntegrationMock(MockClient):
        def __init__(self):
            self.step = 0
            
        def generate(self, prompt, system_prompt=None, tools=None):
            if "Provide a step-by-step plan" in prompt:
                return {"action": "finish", "result": "1. Write file\n2. Test"}
            elif "Tests failed" in prompt:
                return {"action": "finish", "result": "Fixing code"}
                
            if self.step == 0:
                self.step += 1
                return {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "mock"}}
            elif self.step == 1:
                self.step += 1
                return {"action": "finish", "result": "Done"}
            return {"action": "finish"}

    model = IntegrationMock()
    
    registry = ToolRegistry()
    registry.register(FileReadTool(repo))
    registry.register(FileWriteTool(repo))
    registry.register(FileSearchTool(repo))
    registry.register(ShellTool(repo))

    class MockFailingRunner(TestRunner):
        def __init__(self):
            self.runs = 0
        def run_tests(self):
            self.runs += 1
            if self.runs == 1:
                return {"status": "error", "exit_code": 1, "stderr": "Failed"}
            return {"status": "success", "exit_code": 0, "stdout": "Passed"}

    verifier = Verifier(MockFailingRunner(), repo)
    recovery = RecoveryManager(model)
    context_mgr = ContextManager()
    planner = Planner(model)

    orchestrator = Orchestrator(model, registry, verifier, recovery, context_mgr, planner, max_iterations=15, max_recovery_attempts=2)
    state = State(task="Integration task", repo_path=repo)
    
    final_state = orchestrator.run(state)
    
    # Verify trajectory
    assert final_state.status == "success"
    assert final_state.recovery_attempts == 1
    assert "test.txt" in os.listdir(repo)


def test_file_write_flow_verifies_and_tracks_changed_file(tmp_path):
    repo = str(tmp_path)
    initialize_git_repo(repo)
    orchestrator, model, verifier = build_pipeline(
        repo,
        [{"action": "tool_call", "tool": "file_write", "arguments": {"path": "created.txt", "content": "created"}}],
        [{"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Write a file", repo_path=repo))

    assert state.status == "success"
    assert (tmp_path / "created.txt").read_text() == "created"
    assert state.changed_files == ["created.txt"]
    assert verifier.test_runner.calls == 1


def test_apply_patch_flow_changes_file_and_verifies(tmp_path):
    repo = str(tmp_path)
    initialize_git_repo(repo)
    target = tmp_path / "tracked.txt"
    target.write_text("before\n")
    run_git(repo, "add", "tracked.txt")
    run_git(repo, "commit", "-qm", "initial")
    patch = "--- tracked.txt\n+++ tracked.txt\n@@ -1 +1 @@\n-before\n+after\n"
    orchestrator, model, verifier = build_pipeline(
        repo,
        [{"action": "tool_call", "tool": "apply_patch", "arguments": {"path": "tracked.txt", "patch": patch}}],
        [{"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Patch a file", repo_path=repo))

    assert state.status == "success"
    assert target.read_text() == "after\n"
    assert state.changed_files == ["tracked.txt"]


def test_tool_failure_records_error_and_returns_to_plan(tmp_path):
    repo = str(tmp_path)
    orchestrator, model, verifier = build_pipeline(
        repo,
        [
            {"action": "tool_call", "tool": "file_write", "arguments": {"path": "../outside.txt", "content": "bad"}},
            {"action": "finish", "result": "done"},
        ],
        [{"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Fail safely", repo_path=repo))

    assert state.status == "success"
    assert any("outside workspace" in error for error in state.errors)
    assert model.action_count == 2


def test_verification_failure_enters_recovery(tmp_path):
    repo = str(tmp_path)
    orchestrator, model, verifier = build_pipeline(
        repo,
        [{"action": "finish", "result": "done"}, {"action": "finish", "result": "retry"}],
        [{"status": "error", "exit_code": 1}, {"status": "error", "exit_code": 1}],
        max_recovery_attempts=1,
    )

    state = orchestrator.run(State(task="Recover", repo_path=repo))

    assert state.status == "failed"
    assert state.recovery_attempts == 1
    assert verifier.test_runner.calls == 2


def test_recovery_success_runs_verification_again(tmp_path):
    repo = str(tmp_path)
    target = tmp_path / "fixed.txt"
    target.write_text("broken")
    orchestrator, model, verifier = build_pipeline(
        repo,
        [
            {"action": "finish", "result": "initial"},
            {"action": "tool_call", "tool": "file_write", "arguments": {"path": "fixed.txt", "content": "fixed"}},
        ],
        [{"status": "error", "exit_code": 1}, {"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Fix the file", repo_path=repo))

    assert state.status == "success"
    assert state.recovery_attempts == 1
    assert verifier.test_runner.calls == 2
    assert target.read_text() == "fixed"


def test_multiple_tracked_and_untracked_changes_are_preserved(tmp_path):
    repo = str(tmp_path)
    initialize_git_repo(repo)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n")
    run_git(repo, "add", "tracked.txt")
    run_git(repo, "commit", "-qm", "initial")
    orchestrator, model, verifier = build_pipeline(
        repo,
        [{"action": "tool_call", "tool": "shell", "arguments": {"command": "printf 'after\\n' > tracked.txt && printf 'new\\n' > untracked.txt"}}],
        [{"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Change two files", repo_path=repo))

    assert state.status == "success"
    assert state.changed_files == ["tracked.txt", "untracked.txt"]


def test_iteration_limit_counts_meaningful_actions_only(tmp_path):
    repo = str(tmp_path)
    actions = [{"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "missing"}}] * 4
    orchestrator, model, verifier = build_pipeline(repo, actions, [{"status": "success", "exit_code": 0}], max_iterations=2)

    state = orchestrator.run(State(task="Search repeatedly", repo_path=repo))

    assert state.status == "failed"
    assert state.iteration == 2
    assert state.final_result == "Max iterations reached"
    assert verifier.test_runner.calls == 0


def test_recovery_limit_stops_repeated_failures(tmp_path):
    repo = str(tmp_path)
    orchestrator, model, verifier = build_pipeline(
        repo,
        [{"action": "finish", "result": "try"}] * 4,
        [{"status": "error", "exit_code": 1}],
        max_recovery_attempts=2,
    )

    state = orchestrator.run(State(task="Never passes", repo_path=repo))

    assert state.status == "failed"
    assert state.recovery_attempts == 2
    assert state.final_result == "Max recovery attempts reached."


def test_malformed_action_records_error_and_returns_to_plan(tmp_path):
    repo = str(tmp_path)
    orchestrator, model, verifier = build_pipeline(
        repo,
        [None, {"action": "finish", "result": "recovered"}],
        [{"status": "success", "exit_code": 0}],
    )

    state = orchestrator.run(State(task="Handle malformed action", repo_path=repo))

    assert state.status == "success"
    assert "Invalid model action" in state.errors
    assert "Invalid model action" in orchestrator.context_manager.errors
    assert model.action_count == 2
