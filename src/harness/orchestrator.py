from .state import State
from .model.base import BaseModelClient
from .tools.registry import ToolRegistry
from .verification.verifier import Verifier
from .recovery.recovery import RecoveryManager
from .context.context_manager import ContextManager
from .planner import Planner
from typing import Tuple, Set, Dict, Any, Optional, List
import json
import os
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

    def _start_evaluation_report(self, state: State):
        report = state.evaluation_report
        model_provider = report.get("model_provider")
        model_name = report.get("model_name")
        if not model_provider:
            model_provider = type(self.model_client).__module__.split(".")[-1]
        report.clear()
        report.update({
            "task": state.task,
            "model_provider": model_provider,
            "model_name": model_name,
            "model_calls": {"planner": 0, "execution": 0, "recovery": 0},
            "model_call_count": 0,
            "tool_calls": 0,
            "verification_attempts": 0,
            "recovery_attempts": 0,
            "changed_files": [],
            "completion_status": None,
            "final_status": "running",
            "errors": [],
        })

    def _count_model_call(self, state: State, phase: str):
        calls = state.evaluation_report["model_calls"]
        calls[phase] += 1
        state.evaluation_report["model_call_count"] += 1

    def _finish_evaluation_report(self, state: State):
        report = state.evaluation_report
        report["final_status"] = state.status
        report["recovery_attempts"] = state.recovery_attempts
        report["verification_attempts"] = len(state.verification_results)
        report["changed_files"] = list(state.changed_files)
        report["errors"] = list(state.errors[-5:])
        if state.verification_results:
            latest = state.verification_results[-1]
            report["completion_status"] = latest.get("completion_status")
            report["evidence"] = latest.get("evidence", {})
            report["acceptance_criteria"] = latest.get("acceptance_criteria", {})
            report["test_result"] = {
                "status": latest.get("status"),
                "tests_passed": latest.get("tests_passed"),
                "exit_code": latest.get("exit_code"),
            }

    def _capture_baseline(self, state: State):
        capture = getattr(self.verifier, "capture_baseline", None)
        if callable(capture):
            try:
                state.baseline_repository = capture()
            except Exception as exc:
                self._record_error(state, f"Repository baseline capture failed: {exc}")

    def _is_mutating_task(self, state: State) -> bool:
        task_text = (state.task or "").lower()
        mutating_verbs = {"add", "create", "fix", "implement", "update", "modify", "delete", "remove", "refactor", "write", "patch", "build", "set up", "setup"}
        words = set(re.findall(r"\b[a-z]+\b", task_text))
        if words & mutating_verbs:
            return True
        if state.task_spec:
            if state.task_spec.referenced_files:
                return True
            if state.task_spec.acceptance_criteria:
                for crit in state.task_spec.acceptance_criteria:
                    c_lower = crit.lower()
                    if any(v in c_lower for v in ["create", "add", "implement", "modify", "update", "delete", "remove", "must exist", "function", "class", "symbol"]):
                        return True
        struct = getattr(self.planner, "structured_plan", None)
        if struct and struct.expected_files:
            return True
        return False

    def _expected_changed_files(self, state: State, cody_files: Optional[Set[str]] = None) -> set:
        if state.task_spec and getattr(state.task_spec, "allow_broad_changes", False):
            return set(cody_files or state.changed_files)

        explicit_expected = set()
        for path in re.findall(r"\b(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b", state.task):
            if not path.endswith(".") and not re.match(r"^\d+\.\d+$", path):
                explicit_expected.add(path)
        if state.task_spec and state.task_spec.referenced_files:
            explicit_expected.update(state.task_spec.referenced_files)
        struct = getattr(self.planner, "structured_plan", None)
        if struct and struct.expected_files:
            explicit_expected.update(struct.expected_files)

        # If explicit files were designated by the task, spec, or plan, only those are expected
        if explicit_expected:
            return explicit_expected

        # Otherwise, for generic tasks where no specific files were specified upfront:
        if cody_files is not None:
            return set(cody_files)

        expected = set()
        for entry in state.tool_history:
            tool_name = entry.get("tool")
            arguments = entry.get("args", {})
            if tool_name in {"file_write", "apply_patch"} and isinstance(arguments, dict):
                path = arguments.get("path")
                if isinstance(path, str):
                    expected.add(path)
        return expected

    def _compute_cody_changes(self, state: State, verification: dict) -> Tuple[Set[str], Set[str], Set[str]]:
        """Distinguish Cody-introduced changes from pre-existing baseline changes."""
        baseline = state.baseline_repository or {}
        baseline_files = set(baseline.get("changed_files", []))
        current_files = set(verification.get("changed_files", []))
        baseline_signatures = baseline.get("file_signatures", {})
        current_signatures = verification.get("file_signatures", {})

        # New or untracked files added by Cody
        cody_files = current_files - baseline_files

        # Pre-existing files whose contents/signatures were modified by Cody
        for path in current_files & baseline_files:
            if current_signatures.get(path) != baseline_signatures.get(path):
                cody_files.add(path)

        # Files deleted by Cody
        baseline_deleted = set(baseline.get("deleted_files", []))
        current_deleted = set(verification.get("deleted_files", []))
        cody_deleted = current_deleted - baseline_deleted

        # Deletion of untracked baseline files that disappeared from disk
        for path in baseline_files - current_files:
            if path not in baseline_deleted:
                target_p = os.path.join(state.repo_path, path)
                if not os.path.exists(target_p):
                    cody_deleted.add(path)

        cody_files.update(cody_deleted)

        # Files renamed by Cody
        baseline_renamed = set(tuple(r) for r in baseline.get("renamed_files", []))
        current_renamed = set(tuple(r) for r in verification.get("renamed_files", []))
        cody_renamed = current_renamed - baseline_renamed
        for old_p, new_p in cody_renamed:
            cody_files.add(old_p)
            cody_files.add(new_p)

        expected_files = self._expected_changed_files(state, cody_files=cody_files)
        unexpected = cody_files - expected_files
        return cody_files, unexpected, cody_deleted

    def _completion_gate(self, state: State, verification: dict):
        if not verification.get("tests_passed"):
            return "TEST_FAILURE"
        if verification.get("verification_errors"):
            return "VERIFICATION_FAILED"

        ac_result = verification.get("acceptance_criteria")
        if ac_result:
            if ac_result.get("has_failures"):
                return "ACCEPTANCE_CRITERIA_FAILED"
            if ac_result.get("has_unresolved"):
                return "ACCEPTANCE_CRITERIA_UNRESOLVED"

        if not state.baseline_repository and "verification_errors" not in verification:
            return "VERIFIED_SUCCESS"

        cody_files, unexpected, cody_deleted = self._compute_cody_changes(state, verification)

        if not cody_files:
            # Check if this task required code modification
            if self._is_mutating_task(state):
                return "NO_MEANINGFUL_CHANGE"

            mutating_tools = {"file_write", "apply_patch", "shell"}
            has_mutating_action = any(
                entry.get("tool") in mutating_tools
                for entry in state.tool_history
            )
            if has_mutating_action:
                return "NO_MEANINGFUL_CHANGE"

            evidence_tools = {"file_read", "file_search", "git_status", "git_diff"}
            has_task_evidence = any(
                entry.get("tool") in evidence_tools
                for entry in state.tool_history
            )
            if not has_task_evidence:
                return "NO_MEANINGFUL_CHANGE"

        # Check explicit referenced files from task spec
        if state.task_spec and state.task_spec.referenced_files:
            import os
            for rf in state.task_spec.referenced_files:
                full_p = os.path.join(state.repo_path, rf)
                if rf not in cody_files and not os.path.exists(full_p):
                    return "REQUIRED_FILES_NOT_MODIFIED"

        if unexpected:
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
            state.evaluation_report["tool_calls"] += 1
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
                struct = getattr(self.planner, "structured_plan", None)
                curr_step_id = struct.current_step.id if struct and struct.current_step else "none"
                state.plan_step_history.append({
                    "step_id": curr_step_id,
                    "tool": tool_name,
                    "args": kwargs,
                    "status": result.get("status"),
                })
                if result.get("status") == "success":
                    self.context_manager.add_tool_result({"tool": tool_name, "args": kwargs, "result": result})
                    if tool_name in ["file_write", "apply_patch"]:
                        if struct and struct.current_step:
                            step_files = set(struct.current_step.files)
                            touched_path = kwargs.get("path")
                            if not step_files or (touched_path and touched_path in step_files):
                                struct.advance()
                                state.current_step = struct.current_step.description if struct.current_step else None
                                state.structured_plan = struct.to_dict()
                    if tool_name in ["file_write", "shell", "apply_patch"]:
                        state.phase = "VERIFY"
                    elif tool_name in ["file_search", "file_read", "git_status", "git_diff"]:
                        state.phase = "EXECUTE_ACTION"
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
        self._start_evaluation_report(state)
        if hasattr(self.context_manager, "set_task"):
            self.context_manager.set_task(state.task)

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
                    self._count_model_call(state, "planner")
                    state.plan = self.planner.update_plan(state)
                    struct = getattr(self.planner, "structured_plan", None)
                    if struct:
                        state.structured_plan = struct.to_dict()
                        if struct.current_step:
                            state.current_step = struct.current_step.description
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

                struct = getattr(self.planner, "structured_plan", None)
                curr_step = struct.current_step if struct else None
                curr_step_str = f"Step {curr_step.id}: {curr_step.description} (Files: {curr_step.files}, Verification: {curr_step.verification})" if curr_step else "(None)"
                completed_str = ", ".join(f"[{s.id}] {s.description}" for s in struct.completed_steps) if struct and struct.completed_steps else "(None)"
                pending_str = ", ".join(f"[{s.id}] {s.description}" for s in struct.pending_steps) if struct and struct.pending_steps else "(None)"

                sys_prompt = "You are an autonomous coding agent. Use available tools to complete the task."
                prompt = (
                    f"Task: {state.task}\n"
                    f"Context: {json.dumps(state.context)}\n"
                    f"Plan: {state.plan}\n"
                    f"Current Plan Step: {curr_step_str}\n"
                    f"Completed Steps: {completed_str}\n"
                    f"Pending Steps: {pending_str}\n"
                    f"Choose next tool_call or finish."
                )

                self._count_model_call(state, "execution")
                action = self.model_client.generate(
                    prompt,
                    system_prompt=sys_prompt,
                    tools=self.tool_registry.get_all_schemas()
                )
                self._handle_action(action, state)
                state.iteration += 1

            elif current_phase == "VERIFY":
                state.evaluation_report["verification_attempts"] += 1
                try:
                    verif_res = self.verifier.verify(task_spec=state.task_spec)
                except TypeError:
                    verif_res = self.verifier.verify()
                state.verification_results.append(verif_res)
                changed_files = verif_res.get("changed_files", [])
                state.changed_files = list(changed_files) if isinstance(changed_files, list) else []
                completion_status = self._completion_gate(state, verif_res)
                verif_res["completion_status"] = completion_status
                cody_files, unexpected, cody_deleted = self._compute_cody_changes(state, verif_res)
                expected_files = self._expected_changed_files(state, cody_files=cody_files)
                ac = verif_res.get("acceptance_criteria")
                verif_res["evidence"] = {
                    "tests": "PASS" if verif_res.get("tests_passed") else "FAIL",
                    "repository_changed": "YES" if cody_files else "NO",
                    "cody_files": sorted(list(cody_files)),
                    "expected_files_changed": "PASS" if not (expected_files - (set(state.changed_files) | cody_deleted)) else "PARTIAL",
                    "acceptance_criteria": "PASS" if (ac and ac.get("all_passed")) else ("FAIL" if (ac and ac.get("has_failures")) else "UNRESOLVED"),
                    "unexpected_changes": "NONE" if not unexpected else f"FOUND ({len(unexpected)})",
                    "completion": completion_status,
                }
                self.context_manager.add_verification_result(verif_res)
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
                self._count_model_call(state, "recovery")
                recovery_action = self.recovery_manager.recover(
                    state,
                    last_verif,
                    tools=self.tool_registry.get_all_schemas()
                )
                state.plan.append(f"Recovery attempt {state.recovery_attempts + 1}")
                state.recovery_attempts += 1
                self._handle_action(recovery_action, state)
                state.iteration += 1

        self._finish_evaluation_report(state)
        return state
