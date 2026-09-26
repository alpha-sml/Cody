from typing import Dict, Any
from ..model.base import BaseModelClient
from ..state import State

class RecoveryManager:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def recover(self, state: State, failure_details: Dict[str, Any]) -> str:
        # Ask model to generate a recovery plan based on failure
        prompt = f"Tests failed. Details: {failure_details}\nUpdate plan to fix."
        response = self.model_client.generate(prompt)
        return response
