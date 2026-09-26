from .test_runner import TestRunner
from typing import Dict, Any
import subprocess

class Verifier:
    def __init__(self, test_runner: TestRunner, repo_path: str):
        self.test_runner = test_runner
        self.repo_path = repo_path

    def verify(self) -> Dict[str, Any]:
        result = self.test_runner.run_tests()

        changed_files = []
        git_error = None
        try:
            diff_res = subprocess.run(
                ["git", "diff", "--name-only"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            untracked_res = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            for path in diff_res.stdout.splitlines() + untracked_res.stdout.splitlines():
                if path and not (path == ".git" or path.startswith(".git/")) and path not in changed_files:
                    changed_files.append(path)
        except subprocess.CalledProcessError as exc:
            git_error = f"Git inspection failed with exit code {exc.returncode}: {exc.stderr or exc.stdout or str(exc)}"
        except OSError as exc:
            git_error = f"Git inspection failed: {exc}"

        is_verified = (result.get("exit_code") == 0 and result.get("status") == "success")

        verification = {
            "verified": is_verified,
            "tests_passed": is_verified,
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "changed_files": changed_files
        }
        if result.get("error") is not None:
            verification["error"] = result["error"]
        if git_error is not None:
            verification["git_error"] = git_error
        return verification
