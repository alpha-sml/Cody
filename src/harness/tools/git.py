from .base import BaseTool, ToolResult
from .env import sanitized_env
import subprocess
from typing import Any, Dict

class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Check git status in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            result = subprocess.run(["git", "status"], cwd=self.repo_path, capture_output=True, text=True, env=sanitized_env())
            if result.returncode != 0:
                error = result.stderr.strip() or f"git status failed with exit code {result.returncode}"
                return self.error_result(
                    error,
                    output=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode
                )
            return self.success_result(output=result.stdout)
        except Exception as e:
            return self.error_result(str(e), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Check git diff in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            result = subprocess.run(["git", "diff"], cwd=self.repo_path, capture_output=True, text=True, env=sanitized_env())
            output = result.stdout
            if len(output) > 10000:
                output = output[:10000] + "\n...[TRUNCATED DIFF]"
            if result.returncode != 0:
                error = result.stderr.strip() or f"git diff failed with exit code {result.returncode}"
                return self.error_result(
                    error,
                    output=output,
                    stderr=result.stderr,
                    exit_code=result.returncode
                )
            return self.success_result(output=output)
        except Exception as e:
            return self.error_result(str(e), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class GitLogTool(BaseTool):
    name = "git_log"
    description = "Inspect recent git commits in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, max_count: int = 10, **kwargs: Any) -> ToolResult:
        try:
            limit = min(max(1, int(max_count)), 50)
            cmd = ["git", "log", f"-n{limit}", "--oneline"]
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                env=sanitized_env(),
            )
            output = result.stdout
            if len(output) > 10000:
                output = output[:10000] + "\n...[TRUNCATED LOG]"
            if result.returncode != 0:
                error = result.stderr.strip() or f"git log failed with exit code {result.returncode}"
                return self.error_result(
                    error,
                    output=output,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            return self.success_result(output=output)
        except Exception as e:
            return self.error_result(str(e), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_count": {"type": "integer", "description": "Maximum number of commits to show (default 10)"}
            },
        }

