from .base import BaseTool, ToolResult
import os
import subprocess
from typing import Dict, Any, Optional


def _bounded_output(output: Optional[str]) -> str:
    if not output:
        return ""
    if isinstance(output, bytes):
        output = output.decode(errors="replace")
    return output[:10000] + ("\n...[TRUNCATED]" if len(output) > 10000 else "")


def safe_path(repo_path: str, target: str) -> str:
    # Resolve symlinks before checking containment to prevent workspace escapes.
    abs_repo = os.path.realpath(repo_path)
    abs_target = os.path.realpath(os.path.join(repo_path, target))
    if os.path.commonpath([abs_repo, abs_target]) != abs_repo:
        raise ValueError(f"Path {target} is outside workspace {repo_path}")
    return abs_target

class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read a file from the repository with optional line ranges."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, path: str, start_line: int = 1, end_line: Optional[int] = None, **kwargs: Any) -> ToolResult:
        try:
            if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
                raise ValueError("start_line must be a positive integer")
            if end_line is not None:
                if isinstance(end_line, bool) or not isinstance(end_line, int) or end_line < 1:
                    raise ValueError("end_line must be a positive integer or None")
                if end_line < start_line:
                    raise ValueError("end_line must be greater than or equal to start_line")

            safe_p = safe_path(self.repo_path, path)
            with open(safe_p, "r") as f:
                lines = f.readlines()

            if lines and start_line > len(lines):
                raise ValueError("start_line is beyond the end of the file")

            end = end_line if end_line is not None else len(lines)
            content = "".join(lines[start_line - 1 : end])

            # bounded reads
            if len(content) > 10000:
                content = content[:10000] + "\n...[TRUNCATED]"

            return self.success_result(content=content)
        except Exception as e:
            return self.error_result(str(e))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"}
            },
            "required": ["path"]
        }

class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Write or overwrite content to a file."
    category = "MUTATING"

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            safe_p = safe_path(self.repo_path, path)
            os.makedirs(os.path.dirname(safe_p), exist_ok=True)
            with open(safe_p, "w") as f:
                f.write(content)
            return self.success_result(path=path)
        except Exception as e:
            return self.error_result(str(e))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }

class FileSearchTool(BaseTool):
    name = "file_search"
    description = "Recursive text search in the repository."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, pattern: str, directory: str = ".", **kwargs: Any) -> ToolResult:
        try:
            safe_dir = safe_path(self.repo_path, directory)
            # Use grep for search, ignoring binary and obvious dirs
            cmd = ["grep", "-rnI", "--exclude-dir=.git", "--exclude-dir=venv", "--exclude-dir=__pycache__", "--", pattern, safe_dir]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode > 1:
                error = result.stderr.strip() or f"grep failed with exit code {result.returncode}"
                return self.error_result(error, exit_code=result.returncode, stderr=result.stderr)

            output = _bounded_output(result.stdout)

            return self.success_result(results=output)
        except Exception as e:
            return self.error_result(str(e))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "directory": {"type": "string"}
            },
            "required": ["pattern"]
        }

class RepoTreeTool(BaseTool):
    name = "repo_tree"
    description = "Show the repository directory structure."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, directory: str = ".", depth: int = 2, **kwargs: Any) -> ToolResult:
        try:
            if isinstance(depth, bool) or not isinstance(depth, int):
                return self.error_result("depth must be an integer")
            if depth < 0:
                return self.error_result("depth must be non-negative")
            if depth > 100:
                return self.error_result("depth must not exceed 100")

            safe_dir = safe_path(self.repo_path, directory)
            cmd = ["find", safe_dir, "-maxdepth", str(depth), "-not", "-path", "*/.git/*", "-not", "-path", "*/venv/*", "-not", "-path", "*/__pycache__/*"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                error = result.stderr.strip() or f"find failed with exit code {result.returncode}"
                return self.error_result(error, exit_code=result.returncode, stderr=result.stderr)
            return self.success_result(tree=result.stdout)
        except Exception as e:
            return self.error_result(str(e))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "depth": {"type": "integer"}
            }
        }

class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "Apply a targeted unified diff patch to an existing repository file."
    category = "MUTATING"

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, path: str, patch: str, **kwargs: Any) -> ToolResult:
        patch_file = None
        original_content = None
        safe_p = None

        def restore_original() -> Optional[str]:
            if safe_p is None or original_content is None:
                return None
            try:
                with open(safe_p, "wb") as target_file:
                    target_file.write(original_content)
            except OSError as exc:
                return f" Could not restore the target file: {exc}"
            return None

        try:
            safe_p = safe_path(self.repo_path, path)
            if not os.path.isfile(safe_p):
                return self.error_result(f"File {path} does not exist. Cannot patch.")

            with open(safe_p, "rb") as target_file:
                original_content = target_file.read()

            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.write(patch)
                patch_file = f.name

            try:
                cmd = ["patch", "-f", safe_p, "-i", patch_file]
                result = subprocess.run(
                    cmd,
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )

                stdout = _bounded_output(result.stdout)
                stderr = _bounded_output(result.stderr)

                return self.success_result(path=path, stdout=stdout, stderr=stderr)
            except subprocess.CalledProcessError as exc:
                stdout = _bounded_output(exc.stdout)
                stderr = _bounded_output(exc.stderr)
                restore_error = restore_original()
                return self.error_result(
                    "Patch failed to apply cleanly." + (restore_error or ""),
                    exit_code=exc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
            except subprocess.TimeoutExpired as exc:
                restore_error = restore_original()
                return self.error_result(
                    "Patch operation timed out." + (restore_error or ""),
                    exit_code=-1,
                    stdout=_bounded_output(exc.stdout),
                    stderr=_bounded_output(exc.stderr),
                )
            except OSError as exc:
                restore_error = restore_original()
                return self.error_result(
                    f"Patch command failed: {exc}" + (restore_error or ""),
                    exit_code=-1,
                )
            except Exception:
                restore_original()
                raise
            finally:
                if patch_file and os.path.exists(patch_file):
                    os.remove(patch_file)

        except Exception as e:
            return self.error_result(str(e))

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "patch": {"type": "string"}
            },
            "required": ["path", "patch"]
        }
