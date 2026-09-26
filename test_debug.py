from src.harness.orchestrator import Orchestrator
from src.harness.state import State
from src.harness.model.base import BaseModelClient
from src.harness.tools.registry import ToolRegistry
from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner
from src.harness.recovery.recovery import RecoveryManager
from src.harness.context.context_manager import ContextManager
from src.harness.planner import Planner

class MockModel(BaseModelClient):
    def generate(self, prompt, system_prompt=None, tools=None):
        return {"action": "finish", "result": "MOCK_RESPONSE"}

model = MockModel()
registry = ToolRegistry()
verifier = Verifier(TestRunner("."), ".")
recovery = RecoveryManager(model)
context_mgr = ContextManager()
planner = Planner(model)

orchestrator = Orchestrator(model, registry, verifier, recovery, context_mgr, planner, max_iterations=2)
state = State(task="Test")

final_state = orchestrator.run(state)
print(final_state.model_dump_json(indent=2))
