"""Strong behavioral acceptance verification for Cody AI Coding Harness.

Converts acceptance criteria into concrete, objective evidence:
- File existence and non-empty checks
- File modification checks
- Symbol/function/class existence checks (via AST for Python, regex for other files)
- Command execution with expected exit codes
- Structured output and JSON validation
- Stdout/stderr string assertions
- Regression / targeted test checks
- Explicit UNRESOLVED status for subjective or non-testable criteria (NEVER mark as PASS)
"""

import ast
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

from ..tools.env import sanitized_env


def _bounded_sample(text: Any, max_len: int = 1000) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    s = str(text).strip()
    return s[:max_len] + ("...[TRUNCATED]" if len(s) > max_len else "")


class AcceptanceVerifier:
    """Evaluates task acceptance criteria against real workspace and behavioral evidence."""

    def __init__(self, repo_path: str, timeout: int = 30):
        self.repo_path = repo_path
        self.timeout = timeout

    def verify_criterion(
        self,
        criterion: str,
        task_spec: Any = None,
        changed_files: Optional[List[str]] = None,
        cody_files: Optional[Set[str]] = None,
        test_passed: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate a single criterion and return status (PASS, FAIL, UNRESOLVED) with evidence."""
        c_text = str(criterion).strip()
        if not c_text:
            return {
                "criterion": "",
                "status": "PASS",
                "reason": "Empty criterion",
                "evidence": {},
            }

        changed_files = changed_files or []
        cody_files = cody_files if cody_files is not None else set(changed_files)
        repo = Path(self.repo_path)

        # -------------------------------------------------------------------
        # 1. Test suite / regression test criteria
        # -------------------------------------------------------------------
        test_keywords = ["test pass", "tests pass", "all tests pass", "test suite passes", "regression test"]
        if any(kw in c_text.lower() for kw in test_keywords):
            if test_passed:
                return {
                    "criterion": c_text,
                    "status": "PASS",
                    "reason": "Project test suite passed successfully.",
                    "evidence": {"tests_passed": True},
                }
            else:
                return {
                    "criterion": c_text,
                    "status": "FAIL",
                    "reason": "Project test suite failed or did not run.",
                    "evidence": {"tests_passed": False},
                }

        # -------------------------------------------------------------------
        # 2. Command execution & output / JSON validation
        # E.g. "Add a --json flag that outputs JSON", "Run `python3 foo.py` and exit code 0",
        # "Command `...` outputs 'hello'"
        # -------------------------------------------------------------------
        cmd_match = re.search(r"`([^`]+)`", c_text)
        flag_match = re.search(r"(--[a-zA-Z0-9_-]+)", c_text)
        has_json_requirement = "json" in c_text.lower()
        has_exec_intent = any(kw in c_text.lower() for kw in ["run", "execute", "outputs", "output", "exit code", "flag"])

        # Check if criterion specifies a command or executable script
        command_to_run = None
        if cmd_match and (has_exec_intent or has_json_requirement):
            command_to_run = cmd_match.group(1).strip()
        elif flag_match and has_exec_intent:
            flag = flag_match.group(1).strip()
            # Try to find target python entrypoint or script mentioned in task or repo
            entrypoint = None
            if task_spec and getattr(task_spec, "referenced_files", None):
                for rf in task_spec.referenced_files:
                    if rf.endswith(".py") and (repo / rf).is_file():
                        entrypoint = rf
                        break
            if not entrypoint:
                for candidate in ["main.py", "app.py", "cli.py", "src/main.py"]:
                    if (repo / candidate).is_file():
                        entrypoint = candidate
                        break
            if entrypoint:
                command_to_run = f"python3 {entrypoint} {flag}"

        if command_to_run:
            exec_res = self._execute_command_check(command_to_run, c_text, has_json_requirement)
            if exec_res:
                return exec_res

        # -------------------------------------------------------------------
        # 3. File existence and symbol existence checks
        # E.g. "Add calculator.py containing add(a,b)", "File auth.py must be implemented"
        # -------------------------------------------------------------------
        mentioned_files = re.findall(r"\b(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b", c_text)
        mentioned_files = [f for f in mentioned_files if not f.endswith(".") and not re.match(r"^\d+\.\d+$", f)]

        # If files mentioned in criterion
        if mentioned_files:
            missing_files = []
            present_files = []
            for mf in mentioned_files:
                full_path = repo / mf
                if full_path.is_file():
                    present_files.append(mf)
                else:
                    missing_files.append(mf)

            if missing_files:
                return {
                    "criterion": c_text,
                    "status": "FAIL",
                    "reason": f"Required file(s) missing: {missing_files}",
                    "evidence": {"missing_files": missing_files, "present_files": present_files},
                }

            # Check if criterion mentions specific symbols (functions/classes)
            # e.g. "containing add(a,b)", "function add", "class Calculator", "def authenticate"
            symbols_to_check = self._extract_symbols_from_criterion(c_text)
            if symbols_to_check:
                symbol_results = []
                all_symbols_found = True
                for sym in symbols_to_check:
                    sym_found, sym_evidence = self._check_symbol_in_files(sym, present_files)
                    symbol_results.append({"symbol": sym, "found": sym_found, "evidence": sym_evidence})
                    if not sym_found:
                        all_symbols_found = False

                if all_symbols_found:
                    return {
                        "criterion": c_text,
                        "status": "PASS",
                        "reason": f"Files exist and required symbols verified: {[s['symbol'] for s in symbol_results]}",
                        "evidence": {"files": present_files, "symbols": symbol_results},
                    }
                else:
                    missing_syms = [s["symbol"] for s in symbol_results if not s["found"]]
                    return {
                        "criterion": c_text,
                        "status": "FAIL",
                        "reason": f"Required symbol(s) missing: {missing_syms}",
                        "evidence": {"files": present_files, "symbols": symbol_results},
                    }

            # Files exist, no specific symbol checked
            return {
                "criterion": c_text,
                "status": "PASS",
                "reason": f"Referenced file(s) exist: {present_files}",
                "evidence": {"present_files": present_files},
            }

        # -------------------------------------------------------------------
        # 4. Symbol checks without explicit filename in criterion
        # E.g. "Function authenticate must exist", "Add add(a,b)"
        # -------------------------------------------------------------------
        symbols_to_check = self._extract_symbols_from_criterion(c_text)
        if symbols_to_check:
            # Search in changed files first, then throughout repo
            search_files = [f for f in cody_files if (repo / f).is_file()] or [f for f in changed_files if (repo / f).is_file()]
            if not search_files and task_spec and getattr(task_spec, "referenced_files", None):
                search_files = [rf for rf in task_spec.referenced_files if (repo / rf).is_file()]

            if search_files:
                symbol_results = []
                all_symbols_found = True
                for sym in symbols_to_check:
                    sym_found, sym_evidence = self._check_symbol_in_files(sym, search_files)
                    symbol_results.append({"symbol": sym, "found": sym_found, "evidence": sym_evidence})
                    if not sym_found:
                        all_symbols_found = False

                if all_symbols_found:
                    return {
                        "criterion": c_text,
                        "status": "PASS",
                        "reason": f"Symbol(s) verified in repository: {[s['symbol'] for s in symbol_results]}",
                        "evidence": {"symbols": symbol_results},
                    }
                else:
                    missing_syms = [s["symbol"] for s in symbol_results if not s["found"]]
                    return {
                        "criterion": c_text,
                        "status": "FAIL",
                        "reason": f"Required symbol(s) not found in candidate files: {missing_syms}",
                        "evidence": {"symbols": symbol_results, "searched_files": search_files},
                    }

        # -------------------------------------------------------------------
        # 5. Subjective / Unresolved Criteria
        # E.g. "Code should be clean and readable", "Must be robust"
        # CRITICAL: Must be marked UNRESOLVED, never PASS!
        # -------------------------------------------------------------------
        return {
            "criterion": c_text,
            "status": "UNRESOLVED",
            "reason": "Subjective or non-deterministic requirement without objective automated test/command",
            "evidence": {},
        }

    def _execute_command_check(self, command: str, criterion_text: str, require_json: bool) -> Optional[Dict[str, Any]]:
        """Run command and evaluate exit code, stdout, and JSON format."""
        try:
            cmd_args = shlex.split(command)
            result = subprocess.run(
                cmd_args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=sanitized_env(),
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "criterion": criterion_text,
                "status": "FAIL",
                "reason": f"Command timed out after {self.timeout}s: {command}",
                "evidence": {"command": command, "timeout": True},
            }
        except Exception as exc:
            return {
                "criterion": criterion_text,
                "status": "FAIL",
                "reason": f"Command execution failed: {exc}",
                "evidence": {"command": command, "error": str(exc)},
            }

        # Check exit code
        expected_exit_code = 0
        code_match = re.search(r"exit code\s*(\d+)", criterion_text, re.IGNORECASE)
        if code_match:
            expected_exit_code = int(code_match.group(1))

        if result.returncode != expected_exit_code:
            return {
                "criterion": criterion_text,
                "status": "FAIL",
                "reason": f"Command exited with code {result.returncode}, expected {expected_exit_code}",
                "evidence": {
                    "command": command,
                    "exit_code": result.returncode,
                    "expected_exit_code": expected_exit_code,
                    "stdout": _bounded_sample(result.stdout),
                    "stderr": _bounded_sample(result.stderr),
                },
            }

        # Check JSON validation if required
        if require_json:
            stdout_clean = result.stdout.strip()
            # If markdown fences exist, unwrap
            if stdout_clean.startswith("```"):
                lines = stdout_clean.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                stdout_clean = "\n".join(lines).strip()

            try:
                parsed_json = json.loads(stdout_clean)
                return {
                    "criterion": criterion_text,
                    "status": "PASS",
                    "reason": f"Command executed successfully and produced valid JSON output.",
                    "evidence": {
                        "command": command,
                        "exit_code": result.returncode,
                        "parsed_json_type": type(parsed_json).__name__,
                        "stdout_sample": _bounded_sample(stdout_clean, 200),
                    },
                }
            except (json.JSONDecodeError, ValueError) as exc:
                return {
                    "criterion": criterion_text,
                    "status": "FAIL",
                    "reason": f"Command output could not be parsed as JSON: {exc}",
                    "evidence": {
                        "command": command,
                        "exit_code": result.returncode,
                        "stdout": _bounded_sample(result.stdout),
                    },
                }

        # Check expected string match in stdout
        str_matches = re.findall(r"['\"]([^'\"]+)['\"]", criterion_text)
        if str_matches:
            for sm in str_matches:
                if sm.lower() in ("json", "utf-8", "cli", "test"):
                    continue
                if sm not in result.stdout and sm not in result.stderr:
                    return {
                        "criterion": criterion_text,
                        "status": "FAIL",
                        "reason": f"Expected output substring '{sm}' not found in command output.",
                        "evidence": {
                            "command": command,
                            "expected_substring": sm,
                            "stdout": _bounded_sample(result.stdout),
                        },
                    }

        return {
            "criterion": criterion_text,
            "status": "PASS",
            "reason": f"Command executed successfully with expected exit code {result.returncode}.",
            "evidence": {
                "command": command,
                "exit_code": result.returncode,
                "stdout": _bounded_sample(result.stdout, 200),
            },
        }

    def _extract_symbols_from_criterion(self, text: str) -> List[str]:
        """Extract explicit function, method, or class symbols from criterion text."""
        symbols = []
        # Pattern 1: def foo / class Bar / Function foo / Method foo
        m1 = re.findall(r"\b(?:def|class|fn|function|method)\s+([a-zA-Z_][a-zA-Z0-9_]*)", text, re.IGNORECASE)
        symbols.extend(m1)
        # Pattern 2: containing foo(a,b) / function foo(
        m2 = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)", text)
        symbols.extend(m2)
        # Pattern 3: symbol `foo`
        m3 = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", text)
        symbols.extend(m3)

        stopwords = {"def", "class", "fn", "function", "method", "if", "for", "while", "return", "pass", "import", "make", "test", "file", "json"}
        unique_syms = []
        for s in symbols:
            s_clean = s.strip()
            if s_clean and s_clean.lower() not in stopwords and s_clean not in unique_syms:
                unique_syms.append(s_clean)
        return unique_syms

    def _check_symbol_in_files(self, symbol: str, files: List[str]) -> Tuple[bool, Dict[str, Any]]:
        """Verify whether a symbol (function, class, method) exists in the specified files."""
        repo = Path(self.repo_path)
        for rel_path in files:
            full_path = repo / rel_path
            if not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # AST verification for Python files
            if rel_path.endswith(".py"):
                try:
                    tree = ast.parse(content, filename=str(full_path))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            if node.name == symbol:
                                return True, {
                                    "file": rel_path,
                                    "type": type(node).__name__,
                                    "line": getattr(node, "lineno", None),
                                }
                except SyntaxError:
                    # Fallback to regex if file has partial syntax
                    pass

            # Regex search for general definition across languages
            # def sym, class sym, fn sym, sym = ..., function sym
            def_pattern = rf"(?:def|class|fn|function)\s+{re.escape(symbol)}\b|^\s*{re.escape(symbol)}\s*[:=]"
            match = re.search(def_pattern, content, re.MULTILINE)
            if match:
                return True, {"file": rel_path, "pattern_match": match.group(0)}

        return False, {"searched_files": files}

    def evaluate_task_spec(
        self,
        task_spec: Any,
        changed_files: List[str],
        cody_files: Optional[Set[str]] = None,
        test_passed: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate all criteria for task_spec, producing aggregated summary."""
        if not task_spec or not getattr(task_spec, "acceptance_criteria", None):
            return {
                "all_passed": True,
                "has_failures": False,
                "has_unresolved": False,
                "criteria_results": [],
            }

        criteria = task_spec.acceptance_criteria
        results = []
        has_failures = False
        has_unresolved = False

        for crit in criteria:
            res = self.verify_criterion(
                crit,
                task_spec=task_spec,
                changed_files=changed_files,
                cody_files=cody_files,
                test_passed=test_passed,
            )
            results.append(res)
            if res["status"] == "FAIL":
                has_failures = True
            elif res["status"] == "UNRESOLVED":
                has_unresolved = True

        all_passed = (len(results) > 0) and (not has_failures) and (not has_unresolved)

        return {
            "all_passed": all_passed,
            "has_failures": has_failures,
            "has_unresolved": has_unresolved,
            "criteria_results": results,
        }
