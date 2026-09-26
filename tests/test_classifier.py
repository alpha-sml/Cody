import pytest
from src.harness.recovery.classifier import classify_failure, extract_files_from_traceback

def test_classify_test_failure():
    evidence = {"command": "pytest", "exit_code": 1, "stdout": "assert False"}
    res = classify_failure(evidence)
    assert res["category"] == "test_failure"

def test_classify_syntax_error():
    evidence = {"exit_code": 1, "stderr": "SyntaxError: invalid syntax"}
    res = classify_failure(evidence)
    assert res["category"] == "syntax_error"

def test_classify_import_error():
    evidence = {"exit_code": 1, "stderr": "ModuleNotFoundError: No module named 'fake'"}
    res = classify_failure(evidence)
    assert res["category"] == "import_error"

def test_classify_type_error():
    evidence = {"exit_code": 1, "stderr": "TypeError: unsupported operand"}
    res = classify_failure(evidence)
    assert res["category"] == "type_error"

def test_classify_file_error():
    evidence = {"exit_code": 1, "stderr": "FileNotFoundError: No such file"}
    res = classify_failure(evidence)
    assert res["category"] == "file_error"

def test_classify_timeout():
    evidence = {"exit_code": -1, "stderr": "Command timeout out after 30s"}
    res = classify_failure(evidence)
    assert res["category"] == "timeout"

def test_classify_shell_error():
    evidence = {"exit_code": 2, "stderr": "grep: unknown option"}
    res = classify_failure(evidence)
    assert res["category"] == "shell_error"

def test_classify_environment_error():
    evidence = {"exit_code": 127, "stderr": "bash: unknown_cmd: command not found"}
    res = classify_failure(evidence)
    assert res["category"] == "environment_error"

def test_classify_unknown():
    evidence = {"exit_code": 0, "stdout": "all good but logic failed"}
    res = classify_failure(evidence)
    assert res["category"] == "unknown"

def test_classify_tool_error():
    evidence = {"tool": "file_read", "error": "some issue"}
    res = classify_failure(evidence)
    assert res["category"] == "tool_error"

def test_extract_files():
    traceback = 'Traceback:\n  File "src/main.py", line 10\n  File "utils.py", line 5'
    files = extract_files_from_traceback(traceback)
    assert set(files) == {"src/main.py", "utils.py"}
