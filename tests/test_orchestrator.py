from src.harness.orchestrator import Orchestrator
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner
from src.harness.recovery.recovery import RecoveryManager

class MockModel(BaseModelClient):
    def generate(self, prompt, tools=None):
        return "MOCK_RESPONSE"

def test_orchestrator():
    model = MockModel()
    registry = ToolRegistry()
    verifier = Verifier(TestRunner("."))
    recovery = RecoveryManager(model)
    
    orchestrator = Orchestrator(model, registry, verifier, recovery, max_iterations=2)
    state = State(task="Test")
    
    final_state = orchestrator.run(state)
    assert final_state.status == "finished"
