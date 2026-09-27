import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


class TestRunner:
    # Tell pytest this is not a test suite
    __test__ = False

    def __init__(
        self,
        repo_path: str,
        test_command: str = "make test",
        timeout: int = 120,
        explicit_test_command: Optional[str] = None,
    ):
        self.repo_path = repo_path
        self.test_command = test_command
        self.timeout = timeout
        self.explicit_test_command = explicit_test_command

    def discover_test_command(self) -> Dict[str, Any]:
        """Discover the appropriate test command with confidence and source metadata.

        Priority:
          1. Explicit configured test command
          2. Makefile test target
          3. package.json scripts.test
          4. Python project configuration (pyproject.toml, pytest.ini, setup.cfg, tests/)
          5. Cargo (Cargo.toml)
          6. Go (go.mod)
          7. Maven (pom.xml)
          8. Gradle (build.gradle, build.gradle.kts)
          9. Final fallback
        """
        # Priority 1: Explicitly configured test command
        if self.explicit_test_command:
            return {
                "command": self.explicit_test_command.strip(),
                "source": "explicit_config",
                "confidence": "high",
            }
        # If test_command is passed and not the default "make test", treat as explicit
        if self.test_command and self.test_command.strip() != "make test":
            return {
                "command": self.test_command.strip(),
                "source": "explicit_config",
                "confidence": "high",
            }

        repo_path = Path(self.repo_path)

        # Priority 2: Makefile test target
        makefile = repo_path / "Makefile"
        if makefile.is_file():
            try:
                content = makefile.read_text(encoding="utf-8", errors="replace")
                if re.search(r"^\s*test\s*:", content, re.MULTILINE) or re.search(r"^\s*\.PHONY:.*\btest\b", content, re.MULTILINE):
                    return {
                        "command": "make test",
                        "source": "Makefile",
                        "confidence": "high",
                    }
            except OSError:
                pass

        # Priority 3: package.json scripts.test
        pkg_json = repo_path / "package.json"
        if pkg_json.is_file():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict):
                    scripts = data.get("scripts", {})
                    if isinstance(scripts, dict) and "test" in scripts:
                        return {
                            "command": "npm test",
                            "source": "package.json",
                            "confidence": "high",
                        }
            except (OSError, json.JSONDecodeError):
                pass

        # Priority 4: Python project configuration
        pyproject = repo_path / "pyproject.toml"
        if pyproject.is_file():
            try:
                content = pyproject.read_text(encoding="utf-8", errors="replace")
                if "[tool.pytest" in content or "pytest" in content:
                    return {
                        "command": "pytest",
                        "source": "pyproject.toml",
                        "confidence": "high",
                    }
            except OSError:
                pass

        pytest_ini = repo_path / "pytest.ini"
        if pytest_ini.is_file():
            return {
                "command": "pytest",
                "source": "pytest.ini",
                "confidence": "high",
            }

        setup_cfg = repo_path / "setup.cfg"
        if setup_cfg.is_file():
            try:
                content = setup_cfg.read_text(encoding="utf-8", errors="replace")
                if "pytest" in content.lower():
                    return {
                        "command": "pytest",
                        "source": "setup.cfg",
                        "confidence": "high",
                    }
            except OSError:
                pass

        tox_ini = repo_path / "tox.ini"
        if tox_ini.is_file():
            try:
                content = tox_ini.read_text(encoding="utf-8", errors="replace")
                if "pytest" in content.lower():
                    return {
                        "command": "pytest",
                        "source": "tox.ini",
                        "confidence": "high",
                    }
                return {
                    "command": "tox",
                    "source": "tox.ini",
                    "confidence": "high",
                }
            except OSError:
                pass

        # Check tests/ or test/ directory with evidence of python test files
        for t_dir_name in ["tests", "test"]:
            t_dir = repo_path / t_dir_name
            if t_dir.is_dir():
                try:
                    py_files = list(t_dir.glob("**/test_*.py")) + list(t_dir.glob("**/*_test.py")) + list(t_dir.glob("**/*.py"))
                    if py_files:
                        return {
                            "command": "pytest",
                            "source": "tests_dir",
                            "confidence": "medium",
                        }
                except OSError:
                    pass

        # Check root test files matching standard conventions
        try:
            root_tests = list(repo_path.glob("test_*.py")) + list(repo_path.glob("*_test.py"))
            if root_tests:
                return {
                    "command": "pytest",
                    "source": "root_test_files",
                    "confidence": "medium",
                }
        except OSError:
            pass

        # Priority 5: Cargo
        if (repo_path / "Cargo.toml").is_file():
            return {
                "command": "cargo test",
                "source": "Cargo.toml",
                "confidence": "high",
            }

        # Priority 6: Go
        if (repo_path / "go.mod").is_file():
            return {
                "command": "go test ./...",
                "source": "go.mod",
                "confidence": "high",
            }

        # Priority 7: Maven
        if (repo_path / "pom.xml").is_file():
            mvn_cmd = "./mvnw test" if (repo_path / "mvnw").is_file() else "mvn test"
            return {
                "command": mvn_cmd,
                "source": "pom.xml",
                "confidence": "high",
            }

        # Priority 8: Gradle
        if (repo_path / "build.gradle").is_file() or (repo_path / "build.gradle.kts").is_file():
            gradle_cmd = "./gradlew test" if (repo_path / "gradlew").is_file() else "gradle test"
            return {
                "command": gradle_cmd,
                "source": "build.gradle",
                "confidence": "high",
            }

        # Priority 9: Final fallback
        return {
            "command": self.test_command,
            "source": "fallback",
            "confidence": "low",
        }

    def _discover_test_command(self) -> str:
        return self.discover_test_command()["command"]

    def run_tests(self) -> Dict[str, Any]:
        discovery = self.discover_test_command()
        cmd_str = discovery["command"]
        try:
            from ..tools.env import sanitized_env
            cmd = shlex.split(cmd_str)
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=sanitized_env()
            )
            return {
                "status": "success" if result.returncode == 0 else "failure",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "discovery": discovery,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "Test run timed out",
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "discovery": discovery,
            }
        except FileNotFoundError as e:
            return {
                "status": "error",
                "error": f"Command not found: {cmd_str} ({e})",
                "exit_code": 127,
                "stdout": "",
                "stderr": str(e),
                "discovery": discovery,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "discovery": discovery,
            }

