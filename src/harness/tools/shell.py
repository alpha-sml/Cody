from .base import BaseTool
import subprocess
from typing import Dict, Any

class ShellTool(BaseTool):
    name = "shell"
    description = "Execute a shell command in the repository."

    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30  # Bound execution time
            )
            return {
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Command timed out"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
