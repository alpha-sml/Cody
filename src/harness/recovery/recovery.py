from typing import Dict, Any, List, Optional, Set, Tuple
import json
from ..model.base import BaseModelClient
from ..model.boundary import validate_action
from ..state import State
from .classifier import classify_failure

# Targeted recovery guidance per failure category
_RECOVERY_GUIDANCE = {
    "syntax_error": "Fix the syntax error in the identified file. Check indentation, brackets, and quotes.",
    "import_error": "The module or package is missing. Check the import path or install the dependency.",
    "type_error": "A function received wrong argument types. Check the function signature and call site.",
    "file_error": "A file or directory was not found. Verify the path exists and is correctly spelled.",
    "test_failure": "Tests failed. Review the test output, check recent changes against test expectations.",
    "timeout": "The command timed out. Simplify the operation or increase the timeout.",
    "patch_failure": "The patch could not be applied cleanly. The file may have changed. Re-read the file and create a new patch.",
    "dependency_error": "A dependency is missing or incompatible. Check requirements and install needed packages.",
    "environment_error": "A required command or tool is not available in the environment.",
    "tool_error": "A tool returned an error. Check the tool arguments and retry with corrected input.",
    "shell_error": "A shell command failed. Check the command syntax and working directory.",
    "unknown": "An unknown error occurred. Review the error output and try a different approach.",
}


class RecoveryManager:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self._failed_actions: List[Tuple[str, str]] = []  # (category, action_summary)

    def _record_failed_action(self, category: str, action_summary: str):
        self._failed_actions.append((category, action_summary))
        # Keep bounded
        if len(self._failed_actions) > 10:
            self._failed_actions.pop(0)

    def _is_repeated_failure(self, category: str, action_summary: str) -> bool:
        """Check if this exact failure pattern has been seen before."""
        return (category, action_summary) in self._failed_actions

    def recover(self, state: State, failure_details: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        classified = classify_failure(failure_details)
        category = classified["category"]

        # Record this failure for loop prevention
        action_summary = f"{classified.get('command', '')}:{classified.get('message', '')[:100]}"
        is_repeated = self._is_repeated_failure(category, action_summary)
        self._record_failed_action(category, action_summary)

        # Extract affected files
        affected_files = list(classified.get("likely_files", []))
        for f in state.changed_files:
            if f not in affected_files:
                affected_files.append(f)

        # Recent tool calls for context
        recent_tool_calls = [
            {"tool": h.get("tool"), "args": h.get("args"), "status": h.get("result", {}).get("status")}
            for h in state.tool_history[-3:]
        ]

        # Current plan step
        current_step = state.current_step or (state.plan[0] if state.plan else "Resolve task failure")

        # Build targeted context instead of full dump
        targeted_context = {
            "relevant_files": state.context.get("relevant_files", []),
            "file_contents": state.context.get("file_contents", {})
        }
        for k, v in state.context.items():
            if k not in ["tool_results", "errors", "relevant_files", "file_contents", "repository_tree", "git_diff"]:
                targeted_context[k] = v

        if category == "test_failure":
            if "git_diff" in state.context:
                targeted_context["recent_diff"] = state.context["git_diff"]
        elif category == "patch_failure":
            import os
            repo_path = state.repo_path or "."
            refreshed = {}
            for af in affected_files:
                full_p = os.path.join(repo_path, af)
                if os.path.isfile(full_p):
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="replace") as pf:
                            refreshed[af] = pf.read()[:5000]
                    except OSError:
                        pass
            if refreshed:
                targeted_context["refreshed_file_contents"] = refreshed
        elif category == "import_error":
            import os, re
            repo_path = state.repo_path or "."
            msg = classified.get("message", "")
            mod_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", msg)
            if mod_match:
                missing_mod = mod_match.group(1).split(".")[0]
                is_local = os.path.isdir(os.path.join(repo_path, missing_mod)) or os.path.isfile(os.path.join(repo_path, f"{missing_mod}.py"))
                targeted_context["import_analysis"] = {
                    "missing_module": missing_mod,
                    "is_local": is_local,
                    "likely_type": "local_project_module" if is_local else "external_dependency",
                }
        elif category == "file_error":
            import os, re
            repo_path = state.repo_path or "."
            file_match = re.search(r"(?:No such file or directory|FileNotFoundError).*?['\"]([^'\"]+)['\"]", classified.get("message", ""))
            if file_match:
                missing_path = file_match.group(1)
                parent_dir = os.path.dirname(os.path.join(repo_path, missing_path)) or repo_path
                if os.path.isdir(parent_dir):
                    try:
                        targeted_context["existing_files_in_directory"] = sorted(os.listdir(parent_dir))[:20]
                    except OSError:
                        pass

        guidance = _RECOVERY_GUIDANCE.get(category, _RECOVERY_GUIDANCE["unknown"])

        # Build failed-actions context for loop prevention
        failed_actions_context = ""
        if self._failed_actions:
            failed_actions_context = (
                "\n\nPrevious failed recovery attempts (DO NOT repeat these):\n"
                + "\n".join(f"  - [{cat}] {act}" for cat, act in self._failed_actions[-5:])
            )

        repeated_warning = ""
        if is_repeated:
            repeated_warning = (
                "\n\nWARNING: This exact failure has occurred before. "
                "You MUST try a fundamentally different approach. Do not retry the same failed action."
            )

        prompt = (
            f"Task: {state.task}\n"
            f"Current Plan: {state.plan}\n"
            f"Current Plan Step: {current_step}\n"
            f"Recent Tool Calls: {json.dumps(recent_tool_calls)}\n"
            f"Affected Files: {json.dumps(affected_files)}\n"
            f"Context: {json.dumps(targeted_context, indent=2)}\n"
            f"An operation failed. Please provide a corrective tool_call or finish.\n"
            f"Failure Classification: {category}\n"
            f"Recovery Guidance: {guidance}\n"
            f"Classified Evidence:\n{json.dumps(classified, indent=2)}\n"
            f"{failed_actions_context}"
            f"{repeated_warning}"
        )
        response = self.model_client.generate(prompt, tools=tools)

        if not isinstance(response, dict):
            return {
                "action": "error",
                "error_type": "invalid_model_response",
                "message": "Recovery model returned a malformed response: expected a dictionary."
            }

        action = validate_action(response, tools=tools)

        # Detect if model attempts identical failed tool call from previous attempt
        if action.get("action") == "tool_call" and state.tool_history:
            last_tool = state.tool_history[-1]
            if (
                last_tool.get("tool") == action.get("tool")
                and last_tool.get("args") == action.get("arguments")
                and last_tool.get("result", {}).get("status") == "error"
                and is_repeated
            ):
                return {
                    "action": "error",
                    "error_type": "repeated_action_loop_prevented",
                    "message": f"Action {action.get('tool')} with identical arguments failed previously. Alternative recovery strategy required.",
                }

        return action
