import os
from src.harness.tools.file_tools import FileWriteTool, FileReadTool
from src.harness.tools.shell import ShellTool

def test_file_tools(tmp_path):
    write_tool = FileWriteTool()
    read_tool = FileReadTool()
    
    file_path = os.path.join(tmp_path, "test.txt")
    write_tool.execute(path=file_path, content="hello")
    
    res = read_tool.execute(path=file_path)
    assert res["content"] == "hello"

def test_shell_tool():
    shell_tool = ShellTool()
    res = shell_tool.execute(command="echo 'test'")
    assert "test" in res["stdout"]
