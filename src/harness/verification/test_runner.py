import subprocess
from typing import Dict, Any

class TestRunner:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def run_tests(self) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["make", "test"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "exit_code": -1}
