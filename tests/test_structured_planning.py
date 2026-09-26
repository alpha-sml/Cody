import json
import pytest
from src.harness.planner import PlanStep, StructuredPlan, _parse_structured_plan, Planner
from src.harness.state import State
from src.harness.model.base import BaseModelClient


class MockPlannerClient(BaseModelClient):
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response


def test_structured_plan_object_model():
    step1 = PlanStep(id="1", description="Inspect auth.py", files=["auth.py"], verification=["pytest tests/test_auth.py"])
    step2 = PlanStep(id="2", description="Update middleware", files=["middleware.py", "auth.py"], verification=["make test"])

    plan = StructuredPlan(goal="Fix auth flow", steps=[step1, step2])

    assert plan.goal == "Fix auth flow"
    assert len(plan.steps) == 2
    assert plan.current_step.id == "1"
    assert plan.current_step.description == "Inspect auth.py"
    assert plan.completed_steps == []
    assert len(plan.pending_steps) == 2
    assert set(plan.expected_files) == {"auth.py", "middleware.py"}
    assert set(plan.expected_verification) == {"pytest tests/test_auth.py", "make test"}

    # Advance
    plan.advance()
    assert plan.current_step.id == "2"
    assert len(plan.completed_steps) == 1
    assert plan.completed_steps[0].id == "1"
    assert len(plan.pending_steps) == 1

    plan.advance()
    assert plan.current_step is None
    assert len(plan.completed_steps) == 2
    assert plan.pending_steps == []


def test_parse_valid_json_structured_plan():
    json_plan = json.dumps({
        "goal": "Refactor tokens",
        "steps": [
            {
                "id": "s1",
                "description": "Read token.py",
                "files": ["src/token.py"],
                "verification": ["pytest"]
            },
            {
                "id": "s2",
                "description": "Update parser",
                "files": ["src/parser.py"],
                "verification": ["make test"]
            }
        ]
    })

    plan = _parse_structured_plan(json_plan, goal="Fallback goal")
    assert plan.goal == "Refactor tokens"
    assert len(plan.steps) == 2
    assert plan.steps[0].id == "s1"
    assert plan.steps[0].files == ["src/token.py"]
    assert plan.steps[1].files == ["src/parser.py"]


def test_parse_markdown_fenced_json_structured_plan():
    fenced = "```json\n" + json.dumps({
        "goal": "Fenced plan",
        "steps": [{"id": "1", "description": "Step 1", "files": ["f.py"]}]
    }) + "\n```"

    plan = _parse_structured_plan(fenced, goal="Goal")
    assert plan.goal == "Fenced plan"
    assert len(plan.steps) == 1
    assert plan.steps[0].files == ["f.py"]


def test_parse_line_split_fallback_and_file_extraction():
    raw_text = (
        "1. Inspect src/auth/login.py and find bugs\n"
        "2. Modify config.yaml to enable auth\n"
        "3. Run make test to verify\n"
    )

    plan = _parse_structured_plan(raw_text, goal="Line split goal")
    assert plan.goal == "Line split goal"
    assert len(plan.steps) == 3
    assert plan.steps[0].id == "1"
    assert "src/auth/login.py" in plan.steps[0].files
    assert "config.yaml" in plan.steps[1].files


def test_planner_update_plan_integration():
    model = MockPlannerClient({
        "action": "finish",
        "result": json.dumps({
            "goal": "Implement rate limiting",
            "steps": [
                {"id": "1", "description": "Add limiter in limiter.py", "files": ["limiter.py"]},
                {"id": "2", "description": "Add test in test_limiter.py", "files": ["test_limiter.py"]}
            ]
        })
    })

    planner = Planner(model)
    state = State(task="Implement rate limiting")
    steps = planner.update_plan(state)

    assert len(steps) == 2
    assert steps[0] == "Add limiter in limiter.py"
    assert planner.structured_plan is not None
    assert planner.structured_plan.expected_files == ["limiter.py", "test_limiter.py"]


def test_planner_malformed_response_handling():
    # Not a finish action
    model = MockPlannerClient({"action": "tool_call", "tool": "file_read"})
    planner = Planner(model)
    state = State(task="Some task")

    with pytest.raises(ValueError, match="Planner expected 'finish' action"):
        planner.update_plan(state)
