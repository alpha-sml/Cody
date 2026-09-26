from typing import Dict, Any
import json
from ..model.base import BaseModelClient
from ..state import State

class RecoveryManager:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def recover(self, state: State, failure_details: Dict[str, Any]) -> str:
        prompt = (
            f"Tests failed during verification. Please provide a corrective plan.\n"
            f"Failure Details:\n{json.dumps(failure_details, indent=2)}\n"
            f"Update the plan to fix this."
        )
        response = self.model_client.generate(prompt)
        
        if response.get("action") == "tool_call" or "result" in response:
            return response.get("result", "Recovery plan generated (structured action received)")
            
        return "Apply fix based on failure"
