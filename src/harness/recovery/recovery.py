from typing import Dict, Any, List, Optional
import json
from ..model.base import BaseModelClient
from ..model.client import validate_action
from ..state import State

class RecoveryManager:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def recover(self, state: State, failure_details: Dict[str, Any], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        prompt = (
            f"Task: {state.task}\n"
            f"Current Plan: {state.plan}\n"
            f"Context: {json.dumps(state.context, indent=2)}\n"
            f"Tests failed during verification. Please provide a corrective tool_call or finish.\n"
            f"Failure Details:\n{json.dumps(failure_details, indent=2)}\n"
        )
        response = self.model_client.generate(prompt, tools=tools)

        if not isinstance(response, dict):
            return {
                "action": "error",
                "error_type": "invalid_model_response",
                "message": "Recovery model returned a malformed response: expected a dictionary."
            }

        # validate_action handles checking tool_call, finish, error structure
        # If it returns an error, it intercepts invalid structures.
        return validate_action(response)
