"""End-to-end evaluator smoke test and credential isolation security tests.

Tests simulate the exact evaluator workflow:
  export AI_API_KEY="fake-test-key"
  make setup
  make run   (with task piped via stdin)
"""
import io
import os
import sys
import json
import subprocess

import pytest

from src.harness import main as main_module
from src.harness.state import State, TaskSpec
from src.harness.model.client import get_client
from src.harness.model.providers.mock import MockClient
from src.harness.tools.shell import ShellTool
from src.harness.tools.git import GitStatusTool, GitDiffTool
from src.harness.tools.env import sanitized_env


# ---------------------------------------------------------------------------
# Credential isolation tests
# ---------------------------------------------------------------------------

class TestCredentialIsolation:
    """Prove that subprocess commands cannot access evaluator credentials."""

    @pytest.fixture(autouse=True)
    def _set_keys(self):
        os.environ["AI_API_KEY"] = "test-secret-key"
        os.environ["DEEPSEEK_API_KEY"] = "test-ds-key"
        os.environ["QWEN_API_KEY"] = "test-qw-key"
        yield
        os.environ.pop("AI_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("QWEN_API_KEY", None)

    def test_sanitized_env_strips_all_keys(self):
        env = sanitized_env()
        assert "AI_API_KEY" not in env
        assert "DEEPSEEK_API_KEY" not in env
        assert "QWEN_API_KEY" not in env

    def test_shell_tool_cannot_read_ai_api_key(self, tmp_path):
        shell = ShellTool(str(tmp_path))
        # This is the exact attack vector: target code trying to steal credentials
        res = shell.execute(command="python3 -c \"import os; print(os.environ.get('AI_API_KEY', 'NONE'))\"")
        assert "test-secret-key" not in res.get("stdout", "")
        assert "NONE" in res.get("stdout", "")

    def test_shell_tool_cannot_read_provider_keys(self, tmp_path):
        shell = ShellTool(str(tmp_path))
        res = shell.execute(command="env")
        stdout = res.get("stdout", "")
        assert "test-secret-key" not in stdout
        assert "test-ds-key" not in stdout
        assert "test-qw-key" not in stdout
        assert "AI_API_KEY" not in stdout
        assert "DEEPSEEK_API_KEY" not in stdout
        assert "QWEN_API_KEY" not in stdout

    def test_test_runner_subprocess_has_clean_env(self, tmp_path):
        """TestRunner must not leak credentials to test subprocesses."""
        from src.harness.verification.test_runner import TestRunner
        # Create a test script that tries to read the key
        script = tmp_path / "test_steal.sh"
        script.write_text("#!/bin/bash\necho $AI_API_KEY\n")
        script.chmod(0o755)

        runner = TestRunner(str(tmp_path), test_command=str(script))
        result = runner.run_tests()
        assert "test-secret-key" not in result.get("stdout", "")


# ---------------------------------------------------------------------------
# TaskSpec tests
# ---------------------------------------------------------------------------

class TestTaskSpec:
    def test_from_cli_text(self):
        spec = TaskSpec(
            title="Fix auth flow",
            description="Fix the authentication flow in login.py",
            source="cli",
        )
        assert spec.summary == "Fix auth flow"
        assert spec.source == "cli"

    def test_from_multiline_stdin(self):
        text = "Fix the bug\nThe login page crashes on submit\nSteps to reproduce..."
        spec = TaskSpec(
            title=text.split("\n")[0][:200],
            description=text,
            source="stdin",
        )
        assert spec.title == "Fix the bug"
        assert "login page" in spec.description

    def test_empty_title_falls_back_to_description(self):
        spec = TaskSpec(description="Some task description")
        assert spec.summary == "Some task description"

    def test_acceptance_criteria(self):
        spec = TaskSpec(
            title="Add tests",
            acceptance_criteria=["All tests pass", "Coverage > 80%"],
        )
        assert len(spec.acceptance_criteria) == 2


# ---------------------------------------------------------------------------
# End-to-end evaluator smoke test
# ---------------------------------------------------------------------------

class TestEvaluatorSmoke:
    """Simulates the complete evaluator workflow with MockClient."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        # Clean env for evaluator simulation
        for k in ["AI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY",
                   "CODY_TASK", "CODY_PROVIDER", "CODY_MODEL", "MOCK_MODEL"]:
            monkeypatch.delenv(k, raising=False)

    def test_evaluator_flow_with_mock_client(self, monkeypatch, tmp_path, capsys):
        """Full evaluator flow: set key → make run → provide task → completion."""
        monkeypatch.setenv("AI_API_KEY", "fake-test-key")
        monkeypatch.setenv("MOCK_MODEL", "true")

        # Simulate: echo "Fix auth" | make run
        monkeypatch.setattr(sys, "stdin", io.StringIO("Fix the authentication flow"))
        monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path)])

        # Initialize git repo in tmp_path so verifier works
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        main_module.main()

        output = capsys.readouterr().out
        assert "Starting harness for task:" in output
        assert "Finished with status:" in output
        # Credential must never appear in output
        assert "fake-test-key" not in output

    def test_evaluator_flow_with_task_env(self, monkeypatch, tmp_path, capsys):
        """Evaluator can also supply task via CODY_TASK env var."""
        monkeypatch.setenv("AI_API_KEY", "fake-test-key")
        monkeypatch.setenv("MOCK_MODEL", "true")
        monkeypatch.setenv("CODY_TASK", "Fix the bug in utils.py")
        monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path)])

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        main_module.main()

        output = capsys.readouterr().out
        assert "Finished with status:" in output
        assert "fake-test-key" not in output

    def test_evaluator_no_task_exits(self, monkeypatch, tmp_path, capsys):
        """Evaluator with no task must fail with clear message."""
        monkeypatch.setenv("AI_API_KEY", "fake-test-key")
        monkeypatch.setenv("MOCK_MODEL", "true")
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path)])

        with pytest.raises(SystemExit) as exit_info:
            main_module.main()

        assert exit_info.value.code == 1
        assert "No task provided" in capsys.readouterr().out

    def test_evaluator_missing_api_key_exits(self, monkeypatch, tmp_path, capsys):
        """Missing API key must fail with clear message, not crash."""
        # No AI_API_KEY, no provider keys, real provider (not mock)
        monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path), "--task", "Fix bug"])

        with pytest.raises(SystemExit) as exit_info:
            main_module.main()

        assert exit_info.value.code == 1
        output = capsys.readouterr().out
        assert "API key" in output or "No API key" in output

    def test_evaluation_report_structure(self, monkeypatch, tmp_path, capsys):
        """Evaluation report must contain required fields."""
        monkeypatch.setenv("AI_API_KEY", "fake-test-key")
        monkeypatch.setenv("MOCK_MODEL", "true")
        monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path), "--task", "Test task"])

        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        main_module.main()

        output = capsys.readouterr().out
        # Find the evaluation JSON line
        for line in output.split("\n"):
            if line.startswith("Evaluation:"):
                eval_json = json.loads(line.replace("Evaluation: ", ""))
                assert "task" in eval_json
                assert "model_provider" in eval_json
                assert "final_status" in eval_json
                assert "model_call_count" in eval_json
                break
        else:
            pytest.fail("No evaluation report found in output")
