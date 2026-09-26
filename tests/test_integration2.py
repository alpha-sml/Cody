import os
from src.harness.state import State
from src.harness.model.providers.mock import MockClient
from src.harness.tools.registry import ToolRegistry
from src.harness.tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool
from src.harness.tools.shell import ShellTool
from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.orchestrator import Orchestrator
import subprocess

def run_git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

def initialize_git_repo(repo):
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")

def test_full_integration_with_classifier(tmp_path):
    repo = str(tmp_path)
    initialize_git_repo(repo)
    
    # Mock model designed to succeed at first, fail test, recover, and succeed
    class ClassifierIntegrationMock(MockClient):
        def __init__(self):
            self.step = 0
            
        def generate(self, prompt, system_prompt=None, tools=None):
            if "Provide a step-by-step plan" in prompt:
                return {"action": "finish", "result": "1. Search\n2. Read\n3. Edit\n4. Test"}
            elif "Failure Classification: test_failure" in prompt:
                # We expect classifier to label it test_failure
                return {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "fixed"}}
                
            if self.step == 0:
                self.step += 1
                return {"action": "tool_call", "tool": "file_search", "arguments": {"pattern": "mock"}}
            elif self.step == 1:
                self.step += 1
                return {"action": "tool_call", "tool": "file_read", "arguments": {"path": "test.txt"}}
            elif self.step == 2:
                self.step += 1
                return {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.txt", "content": "broken"}}
            elif self.step == 3:
                self.step += 1
                return {"action": "finish", "result": "done_broken"}
            return {"action": "finish"}

    model = ClassifierIntegrationMock()
    
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
                return {"status": "error", "exit_code": 1, "stderr": "assert False"} # test_failure
            return {"status": "success", "exit_code": 0, "stdout": "Passed"}

    verifier = Verifier(MockFailingRunner(), repo)
    recovery = RecoveryManager(model)
    context_mgr = ContextManager()
    planner = Planner(model)

    orchestrator = Orchestrator(model, registry, verifier, recovery, context_mgr, planner, max_iterations=15, max_recovery_attempts=2)
    state = State(task="Integration task with classifier", repo_path=repo)
    
    final_state = orchestrator.run(state)
    
    # Verify trajectory
    assert final_state.status == "success"
    assert final_state.recovery_attempts == 1
    assert (tmp_path / "test.txt").read_text() == "fixed"
