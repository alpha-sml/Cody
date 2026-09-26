import os
from src.harness.tools.file_tools import FileWriteTool, FileReadTool, safe_path
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
