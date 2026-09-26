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

        if not isinstance(response, dict):
            raise ValueError("Planner model returned a malformed response: expected a dictionary.")

        action = response.get("action")
        if action == "error":
            raise ValueError(f"Planner model error: {response.get('message', 'Unknown error')}")

        if action != "finish":
            raise ValueError(f"Planner expected 'finish' action, got '{action}'")

        plan_result = response.get("result")
        if not plan_result or not isinstance(plan_result, str):
            raise ValueError("Planner response missing valid 'result' string containing the plan.")

        plan_str = plan_result.strip()
        if not plan_str:
            raise ValueError("Planner returned an empty plan.")

        return plan_str.split("\n")
