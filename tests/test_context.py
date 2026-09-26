import pytest
from src.harness.context.context_manager import ContextManager

def test_context_manager_bounding():
    cm = ContextManager()
    
    # 1. search result becomes relevant context (added to tool_results)
    cm.add_tool_result({"tool": "file_search", "args": {"pattern": "foo"}, "result": {"output": "match"}})
    assert len(cm.tool_results) == 1
    
    # 2. file read becomes relevant context
    cm.add_tool_result({"tool": "file_read", "args": {"path": "test.py"}, "result": {"content": "print('hi')"}})
    assert "test.py" in cm.relevant_files
    assert "test.py" in cm.file_contents
    assert "print('hi')" in cm.file_contents["test.py"]
    
    # 3. duplicate context is bounded
    for i in range(15):
        cm.add_tool_result({"tool": "file_read", "args": {"path": f"file{i}.py"}, "result": {"content": "c"}})
    
    # should only keep last 10 files
    assert len(cm.relevant_files) == 10
    assert len(cm.file_contents) == 10
    assert "file0.py" not in cm.relevant_files
    
    # 4. tool output is bounded
    for i in range(10):
        cm.add_tool_result({"tool": "shell", "result": {"output": f"out{i}"}})
    
    assert len(cm.tool_results) == 5
    
    # 5. recent diff is retained
    cm.add_tool_result({"tool": "git_diff", "result": {"output": "diff content"}})
    assert cm.git_diff == "diff content"
    
    # 6. failure information is retained
    for i in range(10):
        cm.add_error(f"error {i}")
    assert len(cm.errors) == 5
    assert cm.errors[-1] == "error 9"
