from .base import BaseTool
import subprocess
from typing import Dict, Any

class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Check git status."

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(["git", "status"], capture_output=True, text=True)
            return {"status": "success", "output": result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Check git diff."

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(["git", "diff"], capture_output=True, text=True)
            return {"status": "success", "output": result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}
