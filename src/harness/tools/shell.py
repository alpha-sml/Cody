from .base import BaseTool
import subprocess
from typing import Any, Dict


def _bounded_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    if len(output) > 10000:
        return output[:10000] + "\n...[TRUNCATED]"
    return output

class ShellTool(BaseTool):
    name = "shell"
    description = "Execute a shell command in the repository workspace."
    category = "MUTATING"

    def __init__(self, repo_path: str, timeout: int = 30):
        self.repo_path = repo_path
        self.timeout = timeout

    def execute(self, command: str, **kwargs: Any) -> Dict[str, Any]:
        if not command or not isinstance(command, str) or not command.strip():
            return self.error_result("Command must be a non-empty string", exit_code=-1)

        cmd_str = command.strip()

        try:
            import shlex
            from .env import sanitized_env
            env = sanitized_env()

            # Check if shell metacharacters are present
            shell_metachars = {"|", "&", ";", ">", "<", "$", "\n", "`"}
            needs_shell = any(c in cmd_str for c in shell_metachars)

            if needs_shell:
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env
                )
            else:
                try:
                    args = shlex.split(cmd_str)
                    result = subprocess.run(
                        args,
                        shell=False,
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        env=env
                    )
                except (ValueError, FileNotFoundError) as split_exc:
                    # Fallback to shell if split fails
                    result = subprocess.run(
                        cmd_str,
                        shell=True,
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        env=env
                    )

            stdout = _bounded_output(result.stdout)
            stderr = _bounded_output(result.stderr)
            if result.returncode != 0:
                error = stderr.strip() or f"Command exited with code {result.returncode}"
                return self.error_result(
                    error,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=result.returncode
                )

            return self.success_result(stdout=stdout, stderr=stderr, exit_code=result.returncode)
        except subprocess.TimeoutExpired as e:
            stdout = _bounded_output(e.stdout)
            stderr = _bounded_output(e.stderr)
            return self.error_result(
                "Command timed out",
                stdout=stdout,
                stderr=stderr,
                exit_code=-1
            )
        except Exception as e:
            return self.error_result(str(e), exit_code=-1)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object", 
            "properties": {
                "command": {"type": "string"}
            }, 
            "required": ["command"]
        }
