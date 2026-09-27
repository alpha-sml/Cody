from .test_runner import TestRunner
from .acceptance import AcceptanceVerifier
from typing import Dict, Any, Optional, List, Set, Tuple
import hashlib
import os
import re
import subprocess

_IGNORE_PATTERNS = (
    ".git/",
    "__pycache__",
    ".pytest_cache",
    ".coverage",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".DS_Store",
)

def _is_ignored(path: str) -> bool:
    if any(pattern in path for pattern in _IGNORE_PATTERNS):
        return True
    if path.endswith((".pyc", ".pyo", ".pyd")):
        return True
    return False

def _bounded_output(output: Any) -> str:
    if not output:
        return ""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    return output[:10000] + ("\n...[TRUNCATED]" if len(output) > 10000 else "")


class Verifier:
    def __init__(self, test_runner: TestRunner, repo_path: str):
        self.test_runner = test_runner
        self.repo_path = repo_path
        self._acceptance_verifier = AcceptanceVerifier(repo_path)

    def inspect_repository(self) -> Dict[str, Any]:
        tracked_changes = []
        untracked_changes = []
        deleted_files = []
        renamed_files: List[Tuple[str, str]] = []
        status_lines = []
        errors = []

        try:
            from ..tools.env import sanitized_env
            status_res = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                env=sanitized_env(),
            )
            status_lines = status_res.stdout.splitlines()
            for line in status_lines:
                if len(line) < 4:
                    continue
                code = line[:2]
                raw_path = line[3:].strip()
                if " -> " in raw_path:
                    old_path, new_path = raw_path.split(" -> ", 1)
                    old_path = old_path.strip().strip('"')
                    new_path = new_path.strip().strip('"')
                    renamed_files.append((old_path, new_path))
                    if not _is_ignored(old_path):
                        deleted_files.append(old_path)
                        tracked_changes.append(old_path)
                    path = new_path
                else:
                    path = raw_path.strip('"')

                if _is_ignored(path):
                    continue

                if "D" in code:
                    deleted_files.append(path)
                    tracked_changes.append(path)
                elif code == "??":
                    untracked_changes.append(path)
                else:
                    tracked_changes.append(path)
        except subprocess.CalledProcessError as exc:
            errors.append(f"Git inspection failed with exit code {exc.returncode}: {exc.stderr or exc.stdout or str(exc)}")
        except OSError as exc:
            errors.append(f"Git inspection failed: {exc}")

        changed_files = []
        for path in tracked_changes + untracked_changes:
            if path and not _is_ignored(path) and path not in changed_files:
                changed_files.append(path)

        file_signatures = {}
        for path in changed_files:
            target_path = os.path.join(self.repo_path, path)
            if os.path.isfile(target_path):
                try:
                    with open(target_path, "rb") as changed_file:
                        file_signatures[path] = hashlib.sha256(changed_file.read()).hexdigest()
                except OSError:
                    file_signatures[path] = None
            else:
                file_signatures[path] = None

        return {
            "changed_files": changed_files,
            "tracked_changes": tracked_changes,
            "untracked_changes": untracked_changes,
            "deleted_files": deleted_files,
            "renamed_files": renamed_files,
            "status": status_lines,
            "diff_available": bool(tracked_changes),
            "file_signatures": file_signatures,
            "verification_errors": errors,
        }

    def capture_baseline(self) -> Dict[str, Any]:
        return self.inspect_repository()

    def check_acceptance_criteria(
        self,
        task_spec: Any,
        changed_files: list,
        cody_files: Optional[Set[str]] = None,
        test_passed: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate task acceptance criteria against repository state using AcceptanceVerifier."""
        return self._acceptance_verifier.evaluate_task_spec(
            task_spec=task_spec,
            changed_files=changed_files,
            cody_files=cody_files,
            test_passed=test_passed,
        )

    def verify(self, task_spec: Any = None, cody_files: Optional[Set[str]] = None) -> Dict[str, Any]:
        result = self.test_runner.run_tests()

        repository = self.inspect_repository()
        verification_errors = list(repository["verification_errors"])
        if result.get("error") is not None:
            verification_errors.append(str(result["error"]))

        is_verified = (result.get("exit_code") == 0 and result.get("status") == "success")

        # Determine granular status code
        if repository["verification_errors"]:
            status_code = "REPO_INSPECT_FAIL"
        elif result.get("error") and "timed out" in str(result.get("error")).lower():
            status_code = "TEST_TIMEOUT"
        elif result.get("error") and ("not found" in str(result.get("error")).lower() or "no such" in str(result.get("error")).lower()):
            status_code = "TEST_DISCOVER_FAIL"
        elif not is_verified:
            status_code = "TEST_EXEC_FAIL"
        else:
            status_code = "VERIFY_SUCCESS"

        acceptance = self.check_acceptance_criteria(
            task_spec,
            repository["changed_files"],
            cody_files=cody_files,
            test_passed=is_verified,
        )

        verification = {
            "tests_run": True,
            "verified": is_verified,
            "tests_passed": is_verified,
            "status": result.get("status"),
            "status_code": status_code,
            "exit_code": result.get("exit_code"),
            "stdout": _bounded_output(result.get("stdout", "")),
            "stderr": _bounded_output(result.get("stderr", "")),
            "changed_files": repository["changed_files"],
            "tracked_changes": repository["tracked_changes"],
            "untracked_changes": repository["untracked_changes"],
            "deleted_files": repository.get("deleted_files", []),
            "renamed_files": repository.get("renamed_files", []),
            "diff_available": repository["diff_available"],
            "file_signatures": repository["file_signatures"],
            "verification_errors": verification_errors,
            "acceptance_criteria": acceptance,
        }
        if result.get("discovery"):
            verification["test_discovery"] = result["discovery"]
        if result.get("error") is not None:
            verification["error"] = result["error"]
        if repository["verification_errors"]:
            verification["git_error"] = repository["verification_errors"][0]
        return verification
