import subprocess
import shlex
from typing import Dict, Any

class TestRunner:
    def __init__(self, repo_path: str, test_command: str = "make test", timeout: int = 120):
        self.repo_path = repo_path
        self.test_command = test_command
        self.timeout = timeout

    def run_tests(self) -> Dict[str, Any]:
        try:
            cmd = shlex.split(self.test_command)
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return {
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Test run timed out", "exit_code": -1, "stdout": "", "stderr": ""}
        except Exception as e:
            return {"status": "error", "error": str(e), "exit_code": -1, "stdout": "", "stderr": ""}
