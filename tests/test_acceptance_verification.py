import pytest
from src.harness.state import TaskSpec, State
from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner


class MockTestRunner(TestRunner):
    def __init__(self, exit_code=0, status="success", error=None):
        self._exit_code = exit_code
        self._status = status
        self._error = error

    def run_tests(self):
        res = {
            "status": self._status,
            "exit_code": self._exit_code,
            "stdout": "tests ran",
            "stderr": "",
        }
        if self._error:
            res["error"] = self._error
        return res


import subprocess


def init_git(p):
    subprocess.run(["git", "init", "-q"], cwd=str(p), check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=str(p), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(p), check=True)


def test_acceptance_criteria_success(tmp_path):
    init_git(tmp_path)
    (tmp_path / "auth.py").write_text("def authenticate(): pass\n")
    spec = TaskSpec(
        title="Add auth",
        acceptance_criteria=["File auth.py must be implemented", "all tests pass"]
    )
    runner = MockTestRunner(exit_code=0, status="success")
    verifier = Verifier(runner, str(tmp_path))

    verif = verifier.verify(task_spec=spec)
    assert verif["verified"] is True
    assert verif["status_code"] == "VERIFY_SUCCESS"
    ac = verif["acceptance_criteria"]
    assert ac["all_passed"] is True
    assert ac["has_failures"] is False


def test_acceptance_criteria_missing_file_failure(tmp_path):
    init_git(tmp_path)
    spec = TaskSpec(
        title="Add middleware",
        acceptance_criteria=["Must create middleware/cors.py", "tests pass"]
    )
    runner = MockTestRunner(exit_code=0, status="success")
    verifier = Verifier(runner, str(tmp_path))

    verif = verifier.verify(task_spec=spec)
    ac = verif["acceptance_criteria"]
    assert ac["has_failures"] is True
    assert ac["all_passed"] is False
    failed = [c for c in ac["criteria_results"] if c["status"] == "FAIL"]
    assert len(failed) == 1
    assert "cors.py" in failed[0]["criterion"]


def test_acceptance_criteria_unresolved_subjective(tmp_path):
    init_git(tmp_path)
    spec = TaskSpec(
        title="Refactor",
        acceptance_criteria=["Code should be elegant and readable"]
    )
    runner = MockTestRunner(exit_code=0, status="success")
    verifier = Verifier(runner, str(tmp_path))

    verif = verifier.verify(task_spec=spec)
    ac = verif["acceptance_criteria"]
    assert ac["has_failures"] is False
    assert ac["all_passed"] is False  # subjective marked UNRESOLVED
    unresolved = [c for c in ac["criteria_results"] if c["status"] == "UNRESOLVED"]
    assert len(unresolved) == 1


def test_missing_or_empty_acceptance_criteria(tmp_path):
    init_git(tmp_path)
    spec = TaskSpec(title="No criteria", acceptance_criteria=[])
    runner = MockTestRunner(exit_code=0, status="success")
    verifier = Verifier(runner, str(tmp_path))

    verif = verifier.verify(task_spec=spec)
    ac = verif["acceptance_criteria"]
    assert ac["all_passed"] is True
    assert ac["has_failures"] is False


def test_verifier_status_codes(tmp_path, monkeypatch):
    init_git(tmp_path)

    # Test execution failure
    v_fail = Verifier(MockTestRunner(exit_code=1, status="failure"), str(tmp_path))
    res_fail = v_fail.verify()
    assert res_fail["status_code"] == "TEST_EXEC_FAIL"

    # Test timeout
    v_timeout = Verifier(MockTestRunner(exit_code=-1, status="error", error="Test run timed out"), str(tmp_path))
    res_timeout = v_timeout.verify()
    assert res_timeout["status_code"] == "TEST_TIMEOUT"

    # Test discover fail
    v_disc = Verifier(MockTestRunner(exit_code=-1, status="error", error="pytest: command not found"), str(tmp_path))
    res_disc = v_disc.verify()
    assert res_disc["status_code"] == "TEST_DISCOVER_FAIL"

    # Test repo inspection failure (git error)
    def fail_git(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0], stderr="fatal: not a git repo")

    monkeypatch.setattr(subprocess, "run", fail_git)
    v_inspect = Verifier(MockTestRunner(exit_code=0, status="success"), str(tmp_path))
    res_inspect = v_inspect.verify()
    assert res_inspect["status_code"] == "REPO_INSPECT_FAIL"

