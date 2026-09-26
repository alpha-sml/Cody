from .state import State
from .model.base import BaseModelClient
from .tools.registry import ToolRegistry
from .verification.verifier import Verifier
from .recovery.recovery import RecoveryManager
from .context.context_manager import ContextManager
from .planner import Planner
import json
import re

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

    def _record_error(self, state: State, error: str):
        state.errors.append(error)
        self.context_manager.add_error(error)

    def _capture_baseline(self, state: State):
        capture = getattr(self.verifier, "capture_baseline", None)
        if callable(capture):
            try:
                state.baseline_repository = capture()
            except Exception as exc:
                self._record_error(state, f"Repository baseline capture failed: {exc}")

    def _expected_changed_files(self, state: State):
        expected = set()
        for entry in state.tool_history:
            tool_name = entry.get("tool")
            arguments = entry.get("args", {})
            if tool_name in {"file_write", "apply_patch"} and isinstance(arguments, dict):
                path = arguments.get("path")
                if isinstance(path, str):
                    expected.add(path)

        for path in re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", state.task):
            expected.add(path)
        return expected

    def _completion_gate(self, state: State, verification: dict):
        if not verification.get("tests_passed"):
            return "TEST_FAILURE"
        if verification.get("verification_errors"):
            return "VERIFICATION_FAILED"

        if not state.baseline_repository and "verification_errors" not in verification:
            return "VERIFIED_SUCCESS"

        baseline = state.baseline_repository or {}
        baseline_files = set(baseline.get("changed_files", []))
        current_files = set(verification.get("changed_files", []))
        cody_files = current_files - baseline_files
        expected_files = self._expected_changed_files(state)

        if not cody_files:
            evidence_tools = {"file_read", "file_search", "git_status", "git_diff"}
            has_task_evidence = any(
                entry.get("tool") in evidence_tools
                for entry in state.tool_history
            )
            if not has_task_evidence:
                return "NO_MEANINGFUL_CHANGE"

        unexpected = cody_files - expected_files
        has_shell_change = any(entry.get("tool") == "shell" for entry in state.tool_history)
        if unexpected and not has_shell_change:
            return "UNEXPECTED_CHANGES"

        return "VERIFIED_SUCCESS"

    def _handle_action(self, action: dict, state: State):
        if not isinstance(action, dict):
            self._record_error(state, "Invalid model action")
            state.phase = "PLAN"
            return

        if action.get("action") == "finish":
            if not isinstance(action.get("result"), str) or not action.get("result", "").strip():
                self._record_error(state, "Invalid finish action: result must be a non-empty string.")
                state.phase = "PLAN"
                return
            state.final_result = action.get("result", "")
            state.phase = "VERIFY"
        elif action.get("action") == "error":
            error_msg = str(action.get("message", "Model returned an error action"))
            self._record_error(state, error_msg)
            state.phase = "PLAN"
        elif action.get("action") == "tool_call":
            tool_name = action.get("tool")
            kwargs = action.get("arguments", {})

            if not isinstance(tool_name, str) or not tool_name:
                self._record_error(state, "Invalid model action: tool_call requires a tool name.")
                state.phase = "PLAN"
                return
            if not isinstance(kwargs, dict):
                self._record_error(state, f"Invalid model action: arguments for tool {tool_name} must be an object.")
                state.phase = "PLAN"
                return

            tool = self.tool_registry.get_tool(tool_name)
            if tool:
                try:
                    result = tool.execute(**kwargs)
                except Exception as exc:
                    self._record_error(state, f"Tool {tool_name} execution failed: {exc}")
                    state.phase = "PLAN"
                    return

                if not isinstance(result, dict):
                    self._record_error(state, f"Tool {tool_name} returned an invalid result.")
                    state.phase = "PLAN"
                    return

                state.tool_history.append({"tool": tool_name, "args": kwargs, "result": result})
                if result.get("status") == "success":
                    self.context_manager.add_tool_result({"tool": tool_name, "args": kwargs, "result": result})
                    if tool_name in ["file_write", "shell", "apply_patch"]:
                        state.phase = "VERIFY"
                    else:
                        state.phase = "PLAN"
                elif result.get("status") == "error":
                    error = str(result.get("error", "Tool execution failed."))
                    self._record_error(state, error)
                    state.phase = "PLAN"
                else:
                    self._record_error(state, f"Tool {tool_name} returned an invalid result status.")
                    state.phase = "PLAN"
            else:
                err = f"Tool {tool_name} not found."
                self._record_error(state, err)
                state.phase = "PLAN"
        else:
            self._record_error(state, "Invalid model action")
            state.phase = "PLAN"

    def run(self, state: State) -> State:
        state.status = "running"
        state.phase = "INITIALIZE"

        while state.status == "running":
            current_phase = state.phase

            if current_phase == "INITIALIZE":
                # Discover repo tree
                tree_tool = self.tool_registry.get_tool("repo_tree")
                if not tree_tool:
                    self._record_error(state, "Tool repo_tree not found.")
                else:
                    try:
                        res = tree_tool.execute(directory=".")
                    except Exception as exc:
                        self._record_error(state, f"Tool repo_tree execution failed: {exc}")
                        res = None

                    if isinstance(res, dict) and res.get("status") == "success":
                        self.context_manager.set_tree(res.get("tree", ""))
                    elif isinstance(res, dict):
                        self._record_error(state, str(res.get("error", "Repository tree discovery failed.")))
                    elif res is not None:
                        self._record_error(state, "Repository tree discovery returned an invalid result.")
                self._capture_baseline(state)
                state.phase = "PLAN"

            elif current_phase == "PLAN":
                state.context = self.context_manager.get_context_dict()
                try:
                    state.plan = self.planner.update_plan(state)
                except ValueError as exc:
                    self._record_error(state, f"Planner update failed: {exc}")
                    state.phase = "RECOVER"
                else:
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
                changed_files = verif_res.get("changed_files", [])
                state.changed_files = list(changed_files) if isinstance(changed_files, list) else []
                completion_status = self._completion_gate(state, verif_res)
                verif_res["completion_status"] = completion_status
                if completion_status == "VERIFIED_SUCCESS":
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
