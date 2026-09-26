import re
from typing import Dict, Any

def classify_failure(evidence: Dict[str, Any]) -> Dict[str, Any]:
    command = str(evidence.get("command", ""))
    exit_code = evidence.get("exit_code", -1)
    stdout = str(evidence.get("stdout", ""))
    stderr = str(evidence.get("stderr", ""))
    error_msg = str(evidence.get("error", ""))

    full_text = f"{stdout}\n{stderr}\n{error_msg}".lower()

    category = "unknown"
    
    if exit_code == -1 and "timeout" in full_text:
        category = "timeout"
    elif "assertionerror" in full_text or "test fail" in full_text or ("failed" in full_text and exit_code != 0) or "assert " in full_text:
        if "syntaxerror" in full_text or "indentationerror" in full_text:
            category = "syntax_error"
        elif "modulenotfounderror" in full_text or "importerror" in full_text:
            category = "import_error"
        elif "typeerror" in full_text:
            category = "type_error"
        elif "filenotfounderror" in full_text or "no such file" in full_text:
            category = "file_error"
        else:
            category = "test_failure" if "test" in command.lower() or "pytest" in command.lower() or "assert " in full_text else "shell_error"
    elif "syntaxerror" in full_text or "indentationerror" in full_text:
        category = "syntax_error"
    elif "modulenotfounderror" in full_text or "importerror" in full_text:
        category = "import_error"
    elif "typeerror" in full_text:
        category = "type_error"
    elif "filenotfounderror" in full_text or "no such file" in full_text:
        category = "file_error"
    elif exit_code != 0:
        if "command not found" in full_text:
            category = "environment_error"
        else:
            category = "test_failure" if "test" in command.lower() or "pytest" in command.lower() else "shell_error"
            
    if evidence.get("tool"):
        category = "tool_error"
        if "timeout" in full_text:
            category = "timeout"

    return {
        "category": category,
        "message": error_msg or (stderr.strip() if stderr else stdout.strip()),
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "likely_files": extract_files_from_traceback(full_text)
    }

def extract_files_from_traceback(text: str) -> list:
    matches = re.findall(r'[Ff]ile "([^"]+\.py)"', text)
    return list(set(matches))
