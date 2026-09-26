from typing import Dict, Any, List, Optional
import json
from ..model.base import BaseModelClient
from ..model.boundary import validate_action
from ..state import State
from .classifier import classify_failure

class RecoveryManager:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def recover(self, state: State, failure_details: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        classified = classify_failure(failure_details)

        # Build targeted context instead of full dump
        targeted_context = {
            "relevant_files": state.context.get("relevant_files", []),
            "file_contents": state.context.get("file_contents", {})
        }
        for k, v in state.context.items():
            if k not in ["tool_results", "errors", "relevant_files", "file_contents", "repository_tree", "git_diff"]:
                targeted_context[k] = v

        if classified["category"] == "test_failure":
            if "git_diff" in state.context:
                targeted_context["recent_diff"] = state.context["git_diff"]

        prompt = (
            f"Task: {state.task}\n"
            f"Current Plan: {state.plan}\n"
            f"Context: {json.dumps(targeted_context, indent=2)}\n"
            f"An operation failed. Please provide a corrective tool_call or finish.\n"
            f"Failure Classification: {classified['category']}\n"
            f"Classified Evidence:\n{json.dumps(classified, indent=2)}\n"
        )
        response = self.model_client.generate(prompt, tools=tools)

        if not isinstance(response, dict):
            return {
                "action": "error",
                "error_type": "invalid_model_response",
                "message": "Recovery model returned a malformed response: expected a dictionary."
            }

        return validate_action(response, tools=tools)
