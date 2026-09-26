import pytest
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.tools.base import BaseTool
from src.harness.verification.verifier import Verifier
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.orchestrator import Orchestrator

class MockTool(BaseTool):
    name = "mock_tool"
    description = "Mock tool"
    def execute(self, **kwargs):
        return {"status": "success", "data": "mock data"}
    def get_parameters_schema(self):
        return {"type": "object", "properties": {}}

class RepoTreeMock(MockTool):
    name = "repo_tree"

class MockVerifier(Verifier):
    def __init__(self, succeed_on_call=1):
        self.calls = 0
        self.succeed_on_call = succeed_on_call
    def verify(self):
        self.calls += 1
        if self.calls >= self.succeed_on_call:
            return {"tests_run": True, "tests_passed": True, "changed_files": []}
        return {"tests_run": True, "tests_passed": False, "changed_files": []}

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

def test_planner_redundancy():
    model = CountingModel([{"action": "tool_call", "tool": "mock_tool", "arguments": {}}, {"action": "finish", "result": "completed"}])
    registry = ToolRegistry()
    registry.register(MockTool())
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
    print("Plan calls:", model.plan_calls)

test_planner_redundancy()
