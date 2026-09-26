from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class TaskSpec(BaseModel):
    """Normalized task representation for evaluation input."""
    title: str = ""
    description: str = ""
    acceptance_criteria: List[str] = Field(default_factory=list)
    source: str = "cli"  # cli | stdin | env
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Single-line summary for prompts."""
        return self.title or self.description[:200] or "(no task)"

class State(BaseModel):
    task: str = ""
    task_spec: Optional[TaskSpec] = None
    repo_path: str = ""
    status: str = "init"
    phase: str = "INITIALIZE"
    plan: List[str] = []
    current_step: Optional[str] = None
    structured_plan: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    tool_history: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_repository: Dict[str, Any] = Field(default_factory=dict)
    evaluation_report: Dict[str, Any] = Field(default_factory=dict)
    changed_files: List[str] = Field(default_factory=list)
    verification_results: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    iteration: int = 0
    recovery_attempts: int = 0
    final_result: Optional[str] = None
