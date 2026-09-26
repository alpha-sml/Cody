import subprocess
import shlex
from typing import Dict, Any
from pathlib import Path

class TestRunner:
    def __init__(self, repo_path: str, test_command: str = "make test", timeout: int = 120):
        self.repo_path = repo_path
        self.test_command = test_command
        self.timeout = timeout

    def _discover_test_command(self) -> str:
        repo_path = Path(self.repo_path)
        if (repo_path / "Makefile").exists():
            # Simplistic check if 'test' target exists
            try:
                content = (repo_path / "Makefile").read_text()
                if "test:" in content or "test :" in content or ".PHONY: test" in content:
                    return "make test"
            except Exception:
                pass

        if (repo_path / "package.json").exists():
            return "npm test"
        if (repo_path / "Cargo.toml").exists():
            return "cargo test"
        if (repo_path / "go.mod").exists():
            return "go test ./..."
        if (repo_path / "pom.xml").exists():
            return "mvn test"
        if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
            return "gradle test"
        if (repo_path / "pytest.ini").exists() or (repo_path / "tests").is_dir() or (repo_path / "test").is_dir():
            return "pytest"

        return self.test_command

    def run_tests(self) -> Dict[str, Any]:
        cmd_str = self._discover_test_command()
        try:
            cmd = shlex.split(cmd_str)
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return {
                "status": "success",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Test run timed out", "exit_code": -1, "stdout": "", "stderr": ""}
        except Exception as e:
            return {"status": "error", "error": str(e), "exit_code": -1, "stdout": "", "stderr": ""}
