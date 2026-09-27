import os
import subprocess
import pytest
from src.harness.tools.shell import ShellTool
from src.harness.tools.file_tools import FileSearchTool, RepoTreeTool, ApplyPatchTool, FileWriteTool
from src.harness.tools.code_tools import FindSymbolTool, FindReferencesTool
from src.harness.tools.git import GitStatusTool, GitDiffTool, GitLogTool
from src.harness.tools.env import sanitized_env
from src.harness.verification.test_runner import TestRunner
from src.harness.verification.verifier import Verifier


@pytest.fixture(autouse=True)
def inject_credentials(monkeypatch):
    """Set fake credentials in ambient os.environ for every test in this module."""
    monkeypatch.setenv("AI_API_KEY", "secret-evaluator-token-xyz")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-deepseek-key-123")
    monkeypatch.setenv("QWEN_API_KEY", "secret-qwen-key-456")


def test_shell_tool_credential_isolation(tmp_path):
    shell = ShellTool(str(tmp_path))

    # Test 1: Python os.environ.get
    cmd = 'python3 -c "import os; print(os.environ.get(\'AI_API_KEY\', \'NONE\'))"'
    res = shell.execute(command=cmd)
    assert res["status"] == "success"
    assert "secret-evaluator-token-xyz" not in res["stdout"]
    assert res["stdout"].strip() == "NONE"

    # Test 2: env command — verify all 3 credential variables absent
    res_env = shell.execute(command="env")
    assert res_env["status"] == "success"
    env_out = res_env["stdout"]
    assert "AI_API_KEY" not in env_out
    assert "DEEPSEEK_API_KEY" not in env_out
    assert "QWEN_API_KEY" not in env_out


def test_test_runner_credential_isolation(tmp_path):
    # Create test script checking environment
    script = tmp_path / "check_env.sh"
    script.write_text(
        "#!/bin/sh\n"
        "echo AI=$AI_API_KEY\n"
        "echo DEEPSEEK=$DEEPSEEK_API_KEY\n"
        "echo QWEN=$QWEN_API_KEY\n"
        "env\n"
    )
    script.chmod(0o755)

    runner = TestRunner(str(tmp_path), test_command=str(script))
    res = runner.run_tests()
    assert res["status"] == "success"
    combined = res["stdout"] + res["stderr"]
    assert "secret-evaluator-token-xyz" not in combined
    assert "secret-deepseek-key-123" not in combined
    assert "secret-qwen-key-456" not in combined
    assert "AI=\n" in combined or "AI=\r\n" in combined
    assert "AI_API_KEY=" not in combined
    assert "DEEPSEEK_API_KEY=" not in combined
    assert "QWEN_API_KEY=" not in combined


def test_file_search_tool_credential_isolation(tmp_path):
    (tmp_path / "sample.txt").write_text("hello target world\n")
    search_tool = FileSearchTool(str(tmp_path))
    res = search_tool.execute(pattern="hello")
    assert res["status"] == "success"
    assert "hello target world" in res["results"]
    assert "secret-evaluator-token-xyz" not in str(res)


def test_repo_tree_tool_credential_isolation(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("data")
    tree_tool = RepoTreeTool(str(tmp_path))
    res = tree_tool.execute(depth=2)
    assert res["status"] == "success"
    assert "file.txt" in res["tree"]
    assert "secret-evaluator-token-xyz" not in str(res)


def test_apply_patch_tool_credential_isolation(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("line1\nline2\n")

    patch_content = (
        "--- file.txt\n"
        "+++ file.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-line1\n"
        "+patched\n"
        " line2\n"
    )

    patch_tool = ApplyPatchTool(str(tmp_path))
    res = patch_tool.execute(path="file.txt", patch=patch_content)
    assert res["status"] == "success"
    assert target.read_text() == "patched\nline2\n"
    assert "secret-evaluator-token-xyz" not in str(res)


def test_git_tools_credential_isolation(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)
    (tmp_path / "tracked.txt").write_text("initial\n")
    subprocess.run(["git", "add", "tracked.txt"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=str(tmp_path), check=True)

    status_tool = GitStatusTool(str(tmp_path))
    res_status = status_tool.execute()
    assert res_status["status"] == "success"
    assert "secret-evaluator-token-xyz" not in str(res_status)

    (tmp_path / "tracked.txt").write_text("modified\n")
    diff_tool = GitDiffTool(str(tmp_path))
    res_diff = diff_tool.execute()
    assert res_diff["status"] == "success"
    assert "secret-evaluator-token-xyz" not in str(res_diff)

    log_tool = GitLogTool(str(tmp_path))
    res_log = log_tool.execute()
    assert res_log["status"] == "success"
    assert "init" in res_log["output"]
    assert "secret-evaluator-token-xyz" not in str(res_log)


def test_verifier_credential_isolation(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)
    (tmp_path / "file.txt").write_text("hello\n")
    runner = TestRunner(str(tmp_path))
    verifier = Verifier(runner, str(tmp_path))
    repo_info = verifier.inspect_repository()
    assert "secret-evaluator-token-xyz" not in str(repo_info)
    assert "secret-deepseek-key-123" not in str(repo_info)
    assert "secret-qwen-key-456" not in str(repo_info)


def test_code_tools_credential_isolation(tmp_path):
    (tmp_path / "module.py").write_text("def my_symbol():\n    pass\n")
    find_sym = FindSymbolTool(str(tmp_path))
    res_sym = find_sym.execute(symbol="my_symbol")
    assert res_sym["status"] == "success"
    assert "secret-evaluator-token-xyz" not in str(res_sym)

    find_ref = FindReferencesTool(str(tmp_path))
    res_ref = find_ref.execute(symbol="my_symbol")
    assert res_ref["status"] == "success"
    assert "secret-evaluator-token-xyz" not in str(res_ref)


def test_sanitized_env_case_insensitivity(monkeypatch):
    monkeypatch.setenv("ai_api_key", "lower-key")
    monkeypatch.setenv("Ai_Api_Key", "mixed-key")
    monkeypatch.setenv("antigravity_metadata", "meta-lower")
    env = sanitized_env()
    assert "ai_api_key" not in env
    assert "Ai_Api_Key" not in env
    assert "antigravity_metadata" not in env
