from .base import BaseTool
import subprocess
from typing import Dict, Any

class ShellTool(BaseTool):
    name = "shell"
    description = "Execute a shell command in the repository workspace."

    def __init__(self, repo_path: str, timeout: int = 30):
        self.repo_path = repo_path
        self.timeout = timeout

    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            stdout = result.stdout
            if len(stdout) > 10000:
                stdout = stdout[:10000] + "\n...[TRUNCATED]"
                
            stderr = result.stderr
            if len(stderr) > 10000:
                stderr = stderr[:10000] + "\n...[TRUNCATED]"
                
            return {
                "status": "success",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Command timed out", "exit_code": -1}
        except Exception as e:
            return {"status": "error", "error": str(e), "exit_code": -1}

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object", 
            "properties": {
                "command": {"type": "string"}
            }, 
            "required": ["command"]
        }
