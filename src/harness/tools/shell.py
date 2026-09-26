from .base import BaseTool
import subprocess
from typing import Any, Dict


def _bounded_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    if len(output) > 10000:
        return output[:10000] + "\n...[TRUNCATED]"
    return output

class ShellTool(BaseTool):
    name = "shell"
    description = "Execute a shell command in the repository workspace."
    category = "MUTATING"

    def __init__(self, repo_path: str, timeout: int = 30):
        self.repo_path = repo_path
        self.timeout = timeout

    def execute(self, command: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            import os
            env = os.environ.copy()
            env.pop("AI_API_KEY", None)

            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env
            )

            stdout = _bounded_output(result.stdout)
            stderr = _bounded_output(result.stderr)
            if result.returncode != 0:
                error = stderr.strip() or f"Command exited with code {result.returncode}"
                return self.error_result(
                    error,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=result.returncode
                )

            return self.success_result(stdout=stdout, stderr=stderr, exit_code=result.returncode)
        except subprocess.TimeoutExpired as e:
            stdout = _bounded_output(e.stdout)
            stderr = _bounded_output(e.stderr)
            return self.error_result(
                "Command timed out",
                stdout=stdout,
                stderr=stderr,
                exit_code=-1
            )
        except Exception as e:
            return self.error_result(str(e), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object", 
            "properties": {
                "command": {"type": "string"}
            }, 
            "required": ["command"]
        }
