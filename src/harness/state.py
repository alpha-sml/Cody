from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class State(BaseModel):
    task: str = ""
    repo_path: str = ""
    plan: List[str] = []
    current_step: Optional[str] = None
    context: List[str] = []
    tool_history: List[Dict[str, Any]] = []
    changed_files: List[str] = []
    test_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    iteration: int = 0
    status: str = "init"
    final_result: Optional[str] = None
