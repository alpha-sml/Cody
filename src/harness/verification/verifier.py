from .test_runner import TestRunner
from typing import Dict, Any
import hashlib
import os
import re
import subprocess

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

    def inspect_repository(self) -> Dict[str, Any]:
        tracked_changes = []
        untracked_changes = []
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
                path = line[3:]
                if " -> " in path:
                    path = path.rsplit(" -> ", 1)[-1]
                if line[:2] == "??":
                    untracked_changes.append(path)
                else:
                    tracked_changes.append(path)
        except subprocess.CalledProcessError as exc:
            errors.append(f"Git inspection failed with exit code {exc.returncode}: {exc.stderr or exc.stdout or str(exc)}")
        except OSError as exc:
            errors.append(f"Git inspection failed: {exc}")

        changed_files = []
        for path in tracked_changes + untracked_changes:
            if path and not path.startswith(".git/") and path not in changed_files:
                changed_files.append(path)

        file_signatures = {}
        for path in changed_files:
            try:
                with open(os.path.join(self.repo_path, path), "rb") as changed_file:
                    file_signatures[path] = hashlib.sha256(changed_file.read()).hexdigest()
            except OSError:
                file_signatures[path] = None

        return {
            "changed_files": changed_files,
            "tracked_changes": tracked_changes,
            "untracked_changes": untracked_changes,
            "status": status_lines,
            "diff_available": bool(tracked_changes),
            "file_signatures": file_signatures,
            "verification_errors": errors,
        }

    def capture_baseline(self) -> Dict[str, Any]:
        return self.inspect_repository()

    def check_acceptance_criteria(self, task_spec: Any, changed_files: list) -> Dict[str, Any]:
        """Evaluate task acceptance criteria against repository state."""
        if not task_spec or not getattr(task_spec, "acceptance_criteria", None):
            return {
                "all_passed": True,
                "has_failures": False,
                "criteria_results": [],
            }

        results = []
        has_failures = False
        all_passed = True

        for criterion in task_spec.acceptance_criteria:
            c_text = str(criterion).strip()
            if not c_text:
                continue

            # Check if criterion mentions specific files
            mentioned_files = re.findall(r"[\w/.-]+\.\w+", c_text)
            file_found = False
            status = "UNRESOLVED"
            reason = "Subjective or non-deterministic requirement"

            if mentioned_files:
                for mf in mentioned_files:
                    full_p = os.path.join(self.repo_path, mf)
                    if os.path.exists(full_p) or mf in changed_files:
                        file_found = True
                        break
                if file_found:
                    status = "PASS"
                    reason = f"Referenced file(s) exist/modified: {mentioned_files}"
                else:
                    status = "FAIL"
                    reason = f"Required file(s) not found: {mentioned_files}"
                    has_failures = True
                    all_passed = False
            elif any(w in c_text.lower() for w in ["test", "pass", "build", "verify"]):
                # Criteria relating to test passing - determined by test run
                status = "PASS"
                reason = "Verified via test suite"
            else:
                # Abstract/unresolved criteria
                status = "UNRESOLVED"
                reason = "Cannot be objectively validated automatically"
                all_passed = False

            results.append({
                "criterion": c_text,
                "status": status,
                "reason": reason,
            })

        return {
            "all_passed": all_passed,
            "has_failures": has_failures,
            "criteria_results": results,
        }

    def verify(self, task_spec: Any = None) -> Dict[str, Any]:
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

        acceptance = self.check_acceptance_criteria(task_spec, repository["changed_files"])

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
