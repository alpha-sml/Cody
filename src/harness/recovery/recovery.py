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
                "You MUST try a fundamentally different approach."
            )

        prompt = (
            f"Task: {state.task}\n"
            f"Current Plan: {state.plan}\n"
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

        return validate_action(response, tools=tools)
