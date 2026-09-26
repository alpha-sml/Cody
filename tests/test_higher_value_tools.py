import json
import subprocess
from src.harness.tools.code_tools import RunTestTool, InspectProjectTool, FindSymbolTool, FindReferencesTool
from src.harness.tools.git import GitLogTool


def test_inspect_project_tool(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")
    (tmp_path / "requirements.txt").write_text("pydantic\n")
    (tmp_path / "Makefile").write_text("test:\n\t@echo ok\n")

    tool = InspectProjectTool(str(tmp_path))
    res = tool.execute()
    assert res["status"] == "success"
    assert "Python" in res["languages"]
    assert "makefile" in res["config_files"]
    assert "python_pyproject" in res["config_files"]
    assert res["test_discovery"]["command"] == "make test"


def test_find_symbol_tool(tmp_path):
    src = tmp_path / "service.py"
    src.write_text(
        "class OrderService:\n"
        "    def process_order(self):\n"
        "        pass\n"
    )

    tool = FindSymbolTool(str(tmp_path))

    # Find class
    res_cls = tool.execute(symbol="OrderService")
    assert res_cls["status"] == "success"
    assert res_cls["count"] >= 1
    assert any("class OrderService" in m for m in res_cls["matches"])

    # Find method
    res_method = tool.execute(symbol="process_order")
    assert res_method["status"] == "success"
    assert res_method["count"] >= 1
    assert any("def process_order" in m for m in res_method["matches"])

    # Empty symbol error
    res_err = tool.execute(symbol="")
    assert res_err["status"] == "error"


def test_find_references_tool(tmp_path):
    (tmp_path / "client.py").write_text("from service import process_order\nprocess_order()\n")
    (tmp_path / "other.py").write_text("# no call\n")

    tool = FindReferencesTool(str(tmp_path))
    res = tool.execute(symbol="process_order")
    assert res["status"] == "success"
    assert res["count"] >= 2
    assert any("client.py" in m for m in res["matches"])


def test_run_test_tool(tmp_path):
    # Success test run
    runner_script = tmp_path / "run.sh"
    runner_script.write_text("#!/bin/sh\necho 'suite passed'\nexit 0\n")
    runner_script.chmod(0o755)

    tool = RunTestTool(str(tmp_path), default_command=str(runner_script))
    res = tool.execute()
    assert res["status"] == "success"
    assert "suite passed" in res["stdout"]

    # Failing test run
    fail_script = tmp_path / "fail.sh"
    fail_script.write_text("#!/bin/sh\necho 'suite failed' >&2\nexit 1\n")
    fail_script.chmod(0o755)

    res_fail = tool.execute(command=str(fail_script))
    assert res_fail["status"] == "error"
    assert res_fail["exit_code"] == 1


def test_git_log_tool(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), check=True)
    (tmp_path / "a.txt").write_text("1")
    subprocess.run(["git", "add", "a.txt"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-qm", "feat: initial commit"], cwd=str(tmp_path), check=True)

    tool = GitLogTool(str(tmp_path))
    res = tool.execute(max_count=5)
    assert res["status"] == "success"
    assert "feat: initial commit" in res["output"]
