from .base import BaseTool
import subprocess
from typing import Dict, Any

class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Check git status in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(["git", "status"], cwd=self.repo_path, capture_output=True, text=True)
            return {"status": "success", "output": result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Check git diff in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(["git", "diff"], cwd=self.repo_path, capture_output=True, text=True)
            output = result.stdout
            if len(output) > 10000:
                output = output[:10000] + "\n...[TRUNCATED DIFF]"
            return {"status": "success", "output": output}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}
