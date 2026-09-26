from .state import State
from .model.base import BaseModelClient
from .tools.registry import ToolRegistry
from .verification.verifier import Verifier
from .recovery.recovery import RecoveryManager
import json

class Orchestrator:
    def __init__(
        self,
        model_client: BaseModelClient,
        tool_registry: ToolRegistry,
        verifier: Verifier,
        recovery_manager: RecoveryManager,
        max_iterations: int = 15
    ):
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.verifier = verifier
        self.recovery_manager = recovery_manager
        self.max_iterations = max_iterations

    def run(self, state: State) -> State:
        state.status = "running"
        while state.iteration < self.max_iterations:
            # Basic prompt construction
            prompt = f"Task: {state.task}\nContext: {state.context}\nPlan: {state.plan}\nProvide next tool call as JSON. Tool schemas: {self.tool_registry.get_all_schemas()}"
            
            response = self.model_client.generate(prompt)
            
            # Very basic parsing for hackathon base
            try:
                # Assume model returns JSON like {"tool": "file_read", "kwargs": {"path": "..."}}
                # In real scenario, more robust parsing needed.
                # Here we just mock it if it's mock response
                if response == "MOCK_RESPONSE":
                    state.status = "finished"
                    break
                
                # Try parsing JSON block if present
                if "{" in response and "}" in response:
                    start = response.find("{")
                    end = response.rfind("}") + 1
                    json_str = response[start:end]
                    action = json.loads(json_str)
                    
                    tool_name = action.get("tool")
                    kwargs = action.get("kwargs", {})
                    
                    tool = self.tool_registry.get_tool(tool_name)
                    if tool:
                        result = tool.execute(**kwargs)
                        state.tool_history.append({"tool": tool_name, "args": kwargs, "result": result})
                        
                        if result.get("status") == "success" and tool_name in ["file_write", "shell"]:
                            verif_res = self.verifier.verify()
                            if verif_res["verified"]:
                                state.status = "success"
                                state.final_result = "Verified"
                                break
                            else:
                                recovery_plan = self.recovery_manager.recover(state, verif_res)
                                state.plan.append(f"Recovery: {recovery_plan}")
                                
            except Exception as e:
                state.errors.append(str(e))
                
            state.iteration += 1

        if state.status == "running":
            state.status = "failed"
            state.final_result = "Max iterations reached"

        return state
