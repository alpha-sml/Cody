from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class State(BaseModel):
    task: str = ""
    repo_path: str = ""
    status: str = "init"
    phase: str = "INITIALIZE"
    plan: List[str] = []
    current_step: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    tool_history: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_repository: Dict[str, Any] = Field(default_factory=dict)
    changed_files: List[str] = Field(default_factory=list)
    verification_results: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    iteration: int = 0
    recovery_attempts: int = 0
    final_result: Optional[str] = None
