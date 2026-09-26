from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner
from src.harness.verification import verifier as verifier_module
import subprocess


class MockRunner(TestRunner):
    def __init__(self, result):
        self.result = result

    def run_tests(self):
        return self.result


def git(repo_path, *args):
    return subprocess.run(
        ["git", *args], cwd=repo_path, check=True, capture_output=True, text=True
    )


def create_repo(tmp_path):
    git(str(tmp_path), "init", "-q")
    git(str(tmp_path), "config", "user.email", "test@example.com")
    git(str(tmp_path), "config", "user.name", "Test User")
    tracked_file = tmp_path / "tracked.txt"
    tracked_file.write_text("before\n")
    git(str(tmp_path), "add", "tracked.txt")
    git(str(tmp_path), "commit", "-qm", "initial")
    return tracked_file


def verify_repo(repo_path, result=None):
    return Verifier(
        MockRunner(result or {"status": "success", "exit_code": 0}), str(repo_path)
    ).verify()

def test_verifier_mock():
    verifier = Verifier(MockRunner({"status": "success", "exit_code": 0, "stdout": "pass"}), ".")
    res = verifier.verify()
    assert res["verified"] is True


def test_tracked_modified_file_is_detected(tmp_path):
    tracked_file = create_repo(tmp_path)
    tracked_file.write_text("after\n")

    assert verify_repo(tmp_path)["changed_files"] == ["tracked.txt"]


def test_untracked_file_is_detected(tmp_path):
    create_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("new\n")

    assert verify_repo(tmp_path)["changed_files"] == ["untracked.txt"]


def test_tracked_and_untracked_files_are_detected_together(tmp_path):
    tracked_file = create_repo(tmp_path)
    tracked_file.write_text("after\n")
    (tmp_path / "untracked.txt").write_text("new\n")

    result = verify_repo(tmp_path)
    assert result["changed_files"] == ["tracked.txt", "untracked.txt"]
    assert result["tracked_changes"] == ["tracked.txt"]
    assert result["untracked_changes"] == ["untracked.txt"]
    assert result["tests_run"] is True


def test_clean_repository_has_no_changed_files(tmp_path):
    create_repo(tmp_path)

    assert verify_repo(tmp_path)["changed_files"] == []


def test_git_inspection_failure_is_reported(monkeypatch, tmp_path):
    def fail_git(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0], stderr="not a repository")

    monkeypatch.setattr(verifier_module.subprocess, "run", fail_git)

    result = verify_repo(tmp_path)

    assert result["changed_files"] == []
    assert "Git inspection failed" in result["git_error"]
    assert "not a repository" in result["git_error"]


def test_test_command_failure_is_not_verified(tmp_path):
    result = verify_repo(
        tmp_path,
        {"status": "success", "exit_code": 1, "stdout": "out", "stderr": "failed"},
    )

    assert result["verified"] is False
    assert result["tests_passed"] is False
    assert result["stdout"] == "out"
    assert result["stderr"] == "failed"


def test_successful_tests_are_verified(tmp_path):
    result = verify_repo(
        tmp_path,
        {"status": "success", "exit_code": 0, "stdout": "pass", "stderr": ""},
    )

    assert result["verified"] is True
    assert result["tests_passed"] is True


def test_timeout_and_error_information_is_preserved(tmp_path):
    result = verify_repo(
        tmp_path,
        {
            "status": "error",
            "exit_code": -1,
            "stdout": "partial",
            "stderr": "",
            "error": "Test run timed out",
        },
    )

    assert result["verified"] is False
    assert result["tests_passed"] is False
    assert result["exit_code"] == -1
    assert result["stdout"] == "partial"
    assert result["error"] == "Test run timed out"
