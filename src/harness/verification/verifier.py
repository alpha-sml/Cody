from .test_runner import TestRunner
from typing import Dict, Any
import subprocess

class Verifier:
    def __init__(self, test_runner: TestRunner, repo_path: str):
        self.test_runner = test_runner
        self.repo_path = repo_path

    def verify(self) -> Dict[str, Any]:
        result = self.test_runner.run_tests()
        
        # Check git diff for changed files context
        try:
            diff_res = subprocess.run(["git", "diff", "--name-only"], cwd=self.repo_path, capture_output=True, text=True)
            changed_files = diff_res.stdout.splitlines()
        except:
            changed_files = []

        is_verified = (result.get("exit_code") == 0 and result.get("status") == "success")
        
        return {
            "verified": is_verified,
            "tests_passed": is_verified,
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "changed_files": changed_files
        }
