from typing import List
from .state import State
from .model.base import BaseModelClient
import json

class Planner:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def update_plan(self, state: State) -> List[str]:
        prompt = (
            f"Task: {state.task}\n"
            f"Current context: {json.dumps(state.context, indent=2)}\n"
            f"Provide a step-by-step plan. Return action finish with result containing the plan."
        )
        response = self.model_client.generate(prompt)
        
        plan_str = response.get("result", "1. Inspect repository\n2. Modify files\n3. Verify")
        return plan_str.split("\n")
