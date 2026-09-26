from typing import List
from .state import State
from .model.base import BaseModelClient

class Planner:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client

    def update_plan(self, state: State) -> List[str]:
        # Minimal planner implementation
        prompt = f"Task: {state.task}. Current plan: {state.plan}. Provide an updated step-by-step plan."
        response = self.model_client.generate(prompt)
        # Parse plan from response
        return [response]
