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

    def _handle_action(self, action: dict, state: State):
        if action.get("action") == "finish":
            state.final_result = action.get("result", "")
            state.phase = "VERIFY"
        elif action.get("action") == "error":
            error_msg = action.get("message", "Model returned an error action")
            state.errors.append(error_msg)
            self.context_manager.add_error(error_msg)
            state.phase = "PLAN"
        elif action.get("action") == "tool_call":
            tool_name = action.get("tool")
            kwargs = action.get("arguments", {})

            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                result = tool.execute(**kwargs)
                state.tool_history.append({"tool": tool_name, "args": kwargs, "result": result})
                if result.get("status") == "success":
                    self.context_manager.add_tool_result({"tool": tool_name, "result": result})
                    if tool_name in ["file_write", "shell", "apply_patch"]:
                        state.phase = "VERIFY"
                    else:
                        state.phase = "PLAN"
                elif result.get("status") == "error":
                    error = result.get("error", "Tool execution failed.")
                    state.errors.append(error)
                    self.context_manager.add_error(error)
                    state.phase = "PLAN"
            else:
                err = f"Tool {tool_name} not found."
                state.errors.append(err)
                self.context_manager.add_error(err)
                state.phase = "PLAN"
        else:
            state.errors.append("Invalid model action")
            self.context_manager.add_error("Invalid model action")
            state.phase = "PLAN"

    def run(self, state: State) -> State:
        state.status = "running"
        state.phase = "INITIALIZE"

        while state.status == "running":
            current_phase = state.phase

            if current_phase == "INITIALIZE":
                # Discover repo tree
                tree_tool = self.tool_registry.get_tool("repo_tree")
                if tree_tool:
                    res = tree_tool.execute(directory=".")
                    self.context_manager.set_tree(res.get("tree", ""))
                state.phase = "PLAN"

            elif current_phase == "PLAN":
                state.context = self.context_manager.get_context_dict()
                state.plan = self.planner.update_plan(state)
                state.phase = "EXECUTE_ACTION"

            elif current_phase == "EXECUTE_ACTION":
                if state.iteration >= self.max_iterations:
                    state.status = "failed"
                    state.final_result = "Max iterations reached"
                    break

                state.context = self.context_manager.get_context_dict()

                sys_prompt = "You are an autonomous coding agent. Use available tools to complete the task."
                prompt = f"Task: {state.task}\nContext: {json.dumps(state.context)}\nPlan: {state.plan}\nChoose next tool_call or finish."

                action = self.model_client.generate(
                    prompt,
                    system_prompt=sys_prompt,
                    tools=self.tool_registry.get_all_schemas()
                )
                self._handle_action(action, state)
                state.iteration += 1

            elif current_phase == "VERIFY":
                verif_res = self.verifier.verify()
                state.verification_results.append(verif_res)
                if verif_res.get("verified") and verif_res.get("tests_passed"):
                    state.status = "success"
                    if not state.final_result:
                        state.final_result = "Verified successfully."
                    break
                else:
                    state.phase = "RECOVER"

            elif current_phase == "RECOVER":
                if state.recovery_attempts >= self.max_recovery_attempts:
                    state.status = "failed"
                    state.final_result = "Max recovery attempts reached."
                    break

                if state.iteration >= self.max_iterations:
                    state.status = "failed"
                    state.final_result = "Max iterations reached"
                    break

                last_verif = state.verification_results[-1] if state.verification_results else {}
                recovery_action = self.recovery_manager.recover(
                    state,
                    last_verif,
                    tools=self.tool_registry.get_all_schemas()
                )
                state.plan.append(f"Recovery attempt {state.recovery_attempts + 1}")
                state.recovery_attempts += 1
                self._handle_action(recovery_action, state)
                state.iteration += 1

        return state
