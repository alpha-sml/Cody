import pytest
from src.harness.orchestrator import Orchestrator
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner
from src.harness.tools.base import BaseTool

class ExplicitMockTool(BaseTool):
    name = "file_write"
    description = "Mock file write tool"
    def execute(self, **kwargs):
        return self.success_result(changed="yes")
    def get_parameters_schema(self):
        return {"type": "object", "properties": {}}

class ExplicitVerifier:
    def __init__(self, succeed_on_call=1):
        self.calls = 0
        self.succeed_on_call = succeed_on_call
    def verify(self):
        self.calls += 1
        if self.calls >= self.succeed_on_call:
            return {"verified": True, "tests_passed": True}
        return {"verified": False, "tests_passed": False, "error": "tests failed"}

class ExplicitModel(BaseModelClient):
    def __init__(self, actions):
        self.actions = actions
        self.call_count = 0

    def generate(self, prompt, system_prompt=None, tools=None):
        if self.call_count < len(self.actions):
            action = self.actions[self.call_count]
            self.call_count += 1
            return action
        return {"action": "finish", "result": "default finish"}

class ExplicitPlanner(Planner):
    def update_plan(self, state):
        return ["mock plan step"]

def test_recovery_state_machine_path():
    """
    Proves: broken file -> model tool_call -> verification failure -> RECOVER -> recovery tool_call executes through ToolRegistry -> VERIFY -> SUCCESS
    """
    model_actions = [
        # broken file triggers this tool_call (first step EXECUTE_ACTION)
        {"action": "tool_call", "tool": "file_write", "arguments": {}},
        # Verifier fails, goes to RECOVER. Recovery manager calls model which returns this tool_call
        {"action": "tool_call", "tool": "file_write", "arguments": {}}
    ]
    
    model = ExplicitModel(model_actions)
    registry = ToolRegistry()
    registry.register(ExplicitMockTool())
    verifier = ExplicitVerifier(succeed_on_call=2) # Fails first time, passes second time
    recovery = RecoveryManager(model)
    context_mgr = ContextManager()
    planner = ExplicitPlanner(model)
    
    orchestrator = Orchestrator(model, registry, verifier, recovery, context_mgr, planner, max_iterations=15, max_recovery_attempts=2)
    state = State(task="Test")
    
    final_state = orchestrator.run(state)
    
    assert final_state.status == "success"
    assert final_state.recovery_attempts == 1
    assert len(final_state.tool_history) == 2 # Initial tool_call + Recovery tool_call
    assert final_state.tool_history[1]["tool"] == "file_write"

def test_finish_action_state_machine_path():
    """
    Proves: model -> {"action":"finish"} -> VERIFY -> verifier success -> SUCCESS
    and that finish can never directly set SUCCESS.
    """
    model_actions = [
        {"action": "finish", "result": "done"}
    ]
    
    model = ExplicitModel(model_actions)
    registry = ToolRegistry()
    verifier = ExplicitVerifier(succeed_on_call=1) # Passes immediately
    recovery = RecoveryManager(model)
    context_mgr = ContextManager()
    planner = ExplicitPlanner(model)
    
    orchestrator = Orchestrator(model, registry, verifier, recovery, context_mgr, planner)
    state = State(task="Test")
    
    final_state = orchestrator.run(state)
    
    # Prove finish does not set SUCCESS, it sets VERIFY which sets SUCCESS
    assert final_state.status == "success"
    assert final_state.final_result == "done"
    assert len(final_state.verification_results) == 1
    assert final_state.verification_results[0]["verified"] is True
