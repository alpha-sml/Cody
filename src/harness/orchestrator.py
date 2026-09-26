from .state import State
from .model.base import BaseModelClient
from .tools.registry import ToolRegistry
from .verification.verifier import Verifier
from .recovery.recovery import RecoveryManager
from .context.context_manager import ContextManager
from .planner import Planner
import json

class Orchestrator:
    def __init__(
        self,
        model_client: BaseModelClient,
        tool_registry: ToolRegistry,
        verifier: Verifier,
        recovery_manager: RecoveryManager,
        context_manager: ContextManager,
        planner: Planner,
        max_iterations: int = 15,
        max_recovery_attempts: int = 3
    ):
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.verifier = verifier
        self.recovery_manager = recovery_manager
        self.context_manager = context_manager
        self.planner = planner
        self.max_iterations = max_iterations
        self.max_recovery_attempts = max_recovery_attempts

    def run(self, state: State) -> State:
        state.status = "running"
        state.phase = "INITIALIZE"
        
        while state.iteration < self.max_iterations:
            if state.phase == "INITIALIZE":
                # Discover repo tree
                tree_tool = self.tool_registry.get_tool("repo_tree")
                if tree_tool:
                    res = tree_tool.execute(directory=".")
                    self.context_manager.set_tree(res.get("tree", ""))
                state.phase = "PLAN"
                continue
                
            if state.phase == "PLAN":
                state.context = self.context_manager.get_context_dict()
                state.plan = self.planner.update_plan(state)
                state.phase = "EXECUTE_ACTION"
                continue
                
            if state.phase == "EXECUTE_ACTION":
                state.context = self.context_manager.get_context_dict()
                
                sys_prompt = f"Available tools: {json.dumps(self.tool_registry.get_all_schemas())}"
                prompt = f"Task: {state.task}\nContext: {json.dumps(state.context)}\nPlan: {state.plan}\nChoose next tool_call or finish."
                
                action = self.model_client.generate(prompt, system_prompt=sys_prompt)
                
                if action.get("action") == "finish":
                    state.final_result = action.get("result", "")
                    state.status = "success"
                    break
                elif action.get("action") == "tool_call":
                    tool_name = action.get("tool")
                    kwargs = action.get("arguments", {})
                    
                    tool = self.tool_registry.get_tool(tool_name)
                    if tool:
                        result = tool.execute(**kwargs)
                        state.tool_history.append({"tool": tool_name, "args": kwargs, "result": result})
                        self.context_manager.add_tool_result({"tool": tool_name, "result": result})
                        
                        if tool_name in ["file_write", "shell"]:
                            state.phase = "VERIFY"
                    else:
                        err = f"Tool {tool_name} not found."
                        state.errors.append(err)
                        self.context_manager.add_error(err)
                else:
                    state.errors.append("Invalid model action")
                    self.context_manager.add_error("Invalid model action")

            if state.phase == "VERIFY":
                verif_res = self.verifier.verify()
                state.verification_results.append(verif_res)
                if verif_res["verified"]:
                    state.status = "success"
                    state.final_result = "Verified successfully."
                    break
                else:
                    state.phase = "RECOVER"
                    continue
                    
            if state.phase == "RECOVER":
                if state.recovery_attempts >= self.max_recovery_attempts:
                    state.status = "failed"
                    state.final_result = "Max recovery attempts reached."
                    break
                
                last_verif = state.verification_results[-1] if state.verification_results else {}
                recovery_plan = self.recovery_manager.recover(state, last_verif)
                state.plan.append(f"Recovery: {recovery_plan}")
                state.recovery_attempts += 1
                state.phase = "EXECUTE_ACTION"

            state.iteration += 1

        if state.status == "running":
            state.status = "failed"
            state.final_result = "Max iterations reached"

        return state
