import os
import subprocess
from src.harness.tools.file_tools import FileWriteTool, FileReadTool, safe_path
from src.harness.tools.file_tools import ApplyPatchTool, FileSearchTool, RepoTreeTool
from src.harness.tools import file_tools
from src.harness.tools.shell import ShellTool
import pytest

def test_file_tools(tmp_path):
    repo_path = str(tmp_path)
    write_tool = FileWriteTool(repo_path)
    read_tool = FileReadTool(repo_path)
    
    write_tool.execute(path="test.txt", content="hello\nworld")
    
    res = read_tool.execute(path="test.txt")
    assert "hello\nworld" in res["content"]

    res_lines = read_tool.execute(path="test.txt", start_line=2)
    assert res_lines["content"] == "world"

def test_shell_tool(tmp_path):
    shell_tool = ShellTool(str(tmp_path))
    res = shell_tool.execute(command="echo 'test'")
    assert "test" in res["stdout"]

def test_safe_path(tmp_path):
    repo_path = str(tmp_path)
    
    # Normal file
    safe_path(repo_path, "inside.txt")
    
    # Directory traversal out
    with pytest.raises(ValueError):
        safe_path(repo_path, "../outside.txt")
        
    # Sibling directory prefix
    sibling_path = str(tmp_path) + "_sibling"
    os.makedirs(sibling_path, exist_ok=True)
    with pytest.raises(ValueError):
        safe_path(repo_path, "../" + os.path.basename(sibling_path) + "/outside.txt")


def test_apply_patch_success(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before\n")
    patch = "--- target.txt\n+++ target.txt\n@@ -1 +1 @@\n-before\n+after\n"

    result = ApplyPatchTool(str(tmp_path)).execute("target.txt", patch)

    assert result["status"] == "success"
    assert target.read_text() == "after\n"


def test_apply_patch_nonexistent_target(tmp_path):
    result = ApplyPatchTool(str(tmp_path)).execute("missing.txt", "malformed")

    assert result["status"] == "error"
    assert "does not exist" in result["error"]


def test_apply_patch_malformed_patch_preserves_file(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before\n")

    result = ApplyPatchTool(str(tmp_path)).execute("target.txt", "not a patch")

    assert result["status"] == "error"
    assert target.read_text() == "before\n"


def test_apply_patch_subprocess_failure_is_structured_and_preserves_file(monkeypatch, tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before\n")

    def fail_patch(*args, **kwargs):
        raise subprocess.CalledProcessError(2, args[0], output="patch output", stderr="patch error")

    monkeypatch.setattr(file_tools.subprocess, "run", fail_patch)
    result = ApplyPatchTool(str(tmp_path)).execute("target.txt", "patch")

    assert result["status"] == "error"
    assert result["exit_code"] == 2
    assert result["stdout"] == "patch output"
    assert result["stderr"] == "patch error"
    assert target.read_text() == "before\n"


def test_apply_patch_timeout_is_structured_and_preserves_file(monkeypatch, tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before\n")

    def timeout_patch(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 30, output="partial output", stderr="partial error")

    monkeypatch.setattr(file_tools.subprocess, "run", timeout_patch)
    result = ApplyPatchTool(str(tmp_path)).execute("target.txt", "patch")

    assert result["status"] == "error"
    assert result["error"] == "Patch operation timed out."
    assert result["stdout"] == "partial output"
    assert result["stderr"] == "partial error"
    assert target.read_text() == "before\n"


def test_apply_patch_rejects_repository_escape(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n")

    result = ApplyPatchTool(str(tmp_path)).execute("../outside.txt", "patch")

    assert result["status"] == "error"
    assert "outside workspace" in result["error"]
    assert outside.read_text() == "outside\n"


def test_file_search_pattern_starting_with_dash_is_not_an_option(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("-needle\nother\n")

    result = FileSearchTool(str(tmp_path)).execute("-needle")

    assert result["status"] == "success"
    assert "-needle" in result["results"]


def test_file_search_distinguishes_no_match_and_execution_failure(monkeypatch, tmp_path):
    no_match = FileSearchTool(str(tmp_path)).execute("missing")
    assert no_match["status"] == "success"
    assert no_match["results"] == ""

    def fail_grep(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 2, stdout="", stderr="grep error")

    monkeypatch.setattr(file_tools.subprocess, "run", fail_grep)
    failure = FileSearchTool(str(tmp_path)).execute("pattern")
    assert failure["status"] == "error"
    assert failure["exit_code"] == 2
    assert failure["stderr"] == "grep error"


@pytest.mark.parametrize("depth", ["two", -1, 101])
def test_repo_tree_rejects_invalid_depth(tmp_path, depth):
    result = RepoTreeTool(str(tmp_path)).execute(depth=depth)

    assert result["status"] == "error"
    assert "depth" in result["error"]


def test_repo_tree_accepts_zero_depth(tmp_path):
    result = RepoTreeTool(str(tmp_path)).execute(depth=0)

    assert result["status"] == "success"
    assert result["tree"].strip() == str(tmp_path)


def test_repo_tree_generates_tree_for_valid_depth(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "file.txt").write_text("content")

    result = RepoTreeTool(str(tmp_path)).execute(depth=2)

    assert result["status"] == "success"
    assert str(tmp_path / "nested") in result["tree"]
    assert str(tmp_path / "nested" / "file.txt") in result["tree"]
