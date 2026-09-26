from typing import List, Optional
from .state import State
from .model.base import BaseModelClient
import json

class PlanStep:
    """Single step in a structured plan."""
    __slots__ = ("id", "description", "files", "verification", "status")

    def __init__(self, id: str, description: str, files: Optional[List[str]] = None,
                 verification: Optional[List[str]] = None):
        self.id = id
        self.description = description
        self.files = files or []
        self.verification = verification or []
        self.status = "pending"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "files": self.files,
            "verification": self.verification,
            "status": self.status,
        }

class StructuredPlan:
    """Structured plan with goal and typed steps."""
    def __init__(self, goal: str, steps: Optional[List[PlanStep]] = None):
        self.goal = goal
        self.steps = steps or []
        self._current_index = 0

    @property
    def current_step(self) -> Optional[PlanStep]:
        if self._current_index < len(self.steps):
            return self.steps[self._current_index]
        return None

    @property
    def completed_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if s.status == "completed"]

    @property
    def expected_files(self) -> List[str]:
        files = []
        for s in self.steps:
            files.extend(s.files)
        return list(set(files))

    def advance(self):
        if self.current_step:
            self.current_step.status = "completed"
            self._current_index += 1

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self._current_index,
        }

    def to_step_list(self) -> List[str]:
        """Backward-compatible: return list of step description strings."""
        return [s.description for s in self.steps]


def _parse_structured_plan(response_text: str, goal: str) -> StructuredPlan:
    """Try to parse JSON structured plan from model response. Falls back to line-split."""
    try:
        data = json.loads(response_text) if response_text.strip().startswith("{") else None
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict) and "steps" in data:
        steps = []
        for i, step_data in enumerate(data["steps"]):
            if isinstance(step_data, dict):
                steps.append(PlanStep(
                    id=str(step_data.get("id", i + 1)),
                    description=step_data.get("description", ""),
                    files=step_data.get("files", []),
                    verification=step_data.get("verification", []),
                ))
            elif isinstance(step_data, str):
                steps.append(PlanStep(id=str(i + 1), description=step_data))
        return StructuredPlan(goal=data.get("goal", goal), steps=steps)

    # Fallback: line-split for backward compatibility
    lines = [line.strip() for line in response_text.strip().split("\n") if line.strip()]
    steps = [PlanStep(id=str(i + 1), description=line) for i, line in enumerate(lines)]
    return StructuredPlan(goal=goal, steps=steps)


class Planner:
    def __init__(self, model_client: BaseModelClient):
        self.model_client = model_client
        self._plan: Optional[StructuredPlan] = None

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

        self._plan = _parse_structured_plan(plan_str, goal=state.task)

        return self._plan.to_step_list()

    @property
    def structured_plan(self) -> Optional[StructuredPlan]:
        return self._plan
