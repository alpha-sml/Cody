from .base import BaseTool, ToolResult
from .env import sanitized_env
from .file_tools import safe_path, _bounded_output
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List


class RunTestTool(BaseTool):
    name = "run_test"
    description = "Execute project tests on demand with discovered or explicit command."

    def __init__(self, repo_path: str, default_command: str = "make test"):
        self.repo_path = repo_path
        self.default_command = default_command

    def execute(self, command: Optional[str] = None, **kwargs: Any) -> ToolResult:
        try:
            from ..verification.test_runner import TestRunner
            runner = TestRunner(
                repo_path=self.repo_path,
                test_command=command or self.default_command,
                explicit_test_command=command,
            )
            res = runner.run_tests()
            stdout = _bounded_output(res.get("stdout", ""))
            stderr = _bounded_output(res.get("stderr", ""))
            if res.get("status") == "success" and res.get("exit_code") == 0:
                return self.success_result(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=res.get("exit_code", 0),
                    command=res.get("discovery", {}).get("command", command or self.default_command),
                )
            else:
                err_msg = res.get("error") or stderr.strip() or f"Tests failed with exit code {res.get('exit_code')}"
                return self.error_result(
                    err_msg,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=res.get("exit_code", 1),
                    command=res.get("discovery", {}).get("command", command or self.default_command),
                )
        except Exception as exc:
            return self.error_result(str(exc), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Optional explicit test command override"}
            },
        }


class InspectProjectTool(BaseTool):
    name = "inspect_project"
    description = "Inspect repository ecosystem, configuration files, test runner, and primary languages."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            root = Path(self.repo_path)
            indicators = {}
            languages = []

            if (root / "package.json").is_file():
                indicators["node"] = "package.json"
                languages.append("JavaScript/TypeScript")
            if (root / "pyproject.toml").is_file():
                indicators["python_pyproject"] = "pyproject.toml"
                languages.append("Python")
            if (root / "requirements.txt").is_file():
                indicators["python_requirements"] = "requirements.txt"
                if "Python" not in languages:
                    languages.append("Python")
            if (root / "Cargo.toml").is_file():
                indicators["rust"] = "Cargo.toml"
                languages.append("Rust")
            if (root / "go.mod").is_file():
                indicators["go"] = "go.mod"
                languages.append("Go")
            if (root / "pom.xml").is_file():
                indicators["maven"] = "pom.xml"
                languages.append("Java")
            if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
                indicators["gradle"] = "build.gradle"
                languages.append("Java/Kotlin")
            if (root / "Makefile").is_file():
                indicators["makefile"] = "Makefile"

            from ..verification.test_runner import TestRunner
            runner = TestRunner(self.repo_path)
            discovery = runner.discover_test_command()

            return self.success_result(
                languages=languages or ["Unknown"],
                config_files=indicators,
                test_discovery=discovery,
                repo_path=self.repo_path,
            )
        except Exception as exc:
            return self.error_result(str(exc))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class FindSymbolTool(BaseTool):
    name = "find_symbol"
    description = "Locate definitions of functions, classes, methods, or symbols in repository files."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, symbol: str, directory: str = ".", **kwargs: Any) -> ToolResult:
        try:
            if not symbol or not symbol.strip():
                return self.error_result("Symbol name is required.")
            safe_dir = safe_path(self.repo_path, directory)
            sym = symbol.strip()
            # Search for common definition patterns across languages
            # def sym, class sym, fn sym, function sym, sym =
            pattern = rf"(def\s+{re.escape(sym)}\b|class\s+{re.escape(sym)}\b|fn\s+{re.escape(sym)}\b|function\s+{re.escape(sym)}\b|^\s*{re.escape(sym)}\s*[:=])"
            cmd = [
                "grep",
                "-rnEI",
                "--exclude-dir=.git",
                "--exclude-dir=venv",
                "--exclude-dir=__pycache__",
                "--exclude-dir=node_modules",
                "--",
                pattern,
                safe_dir,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, env=sanitized_env())
            if result.returncode > 1:
                return self.error_result(result.stderr.strip() or "Search error", exit_code=result.returncode)

            output = _bounded_output(result.stdout)
            matches = [line.strip() for line in output.splitlines() if line.strip()]
            return self.success_result(symbol=sym, count=len(matches), matches=matches)
        except Exception as exc:
            return self.error_result(str(exc))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol, function, or class name to find"},
                "directory": {"type": "string", "description": "Directory to search within (default '.')"},
            },
            "required": ["symbol"],
        }


class FindReferencesTool(BaseTool):
    name = "find_references"
    description = "Find all usage references of a symbol across the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, symbol: str, directory: str = ".", **kwargs: Any) -> ToolResult:
        try:
            if not symbol or not symbol.strip():
                return self.error_result("Symbol name is required.")
            safe_dir = safe_path(self.repo_path, directory)
            sym = symbol.strip()
            pattern = rf"\b{re.escape(sym)}\b"
            cmd = [
                "grep",
                "-rnEI",
                "--exclude-dir=.git",
                "--exclude-dir=venv",
                "--exclude-dir=__pycache__",
                "--exclude-dir=node_modules",
                "--",
                pattern,
                safe_dir,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, env=sanitized_env())
            if result.returncode > 1:
                return self.error_result(result.stderr.strip() or "Search error", exit_code=result.returncode)

            output = _bounded_output(result.stdout)
            matches = [line.strip() for line in output.splitlines() if line.strip()]
            return self.success_result(symbol=sym, count=len(matches), matches=matches[:50])
        except Exception as exc:
            return self.error_result(str(exc))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol to search references for"},
                "directory": {"type": "string", "description": "Directory to search within (default '.')"},
            },
            "required": ["symbol"],
        }
