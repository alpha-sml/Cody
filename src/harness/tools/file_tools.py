from .base import BaseTool
import os
import subprocess
from typing import Dict, Any, Optional

def safe_path(repo_path: str, target: str) -> str:
    # Ensure target is within repo_path
    abs_repo = os.path.abspath(repo_path)
    abs_target = os.path.abspath(os.path.join(repo_path, target))
    if not abs_target.startswith(abs_repo):
        raise ValueError(f"Path {target} is outside workspace {repo_path}")
    return abs_target

class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read a file from the repository with optional line ranges."

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, path: str, start_line: int = 1, end_line: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        try:
            safe_p = safe_path(self.repo_path, path)
            with open(safe_p, "r") as f:
                lines = f.readlines()
            
            end = end_line if end_line else len(lines)
            content = "".join(lines[start_line - 1 : end])
            
            # bounded reads
            if len(content) > 10000:
                content = content[:10000] + "\n...[TRUNCATED]"
                
            return {"status": "success", "content": content}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
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

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def execute(self, path: str, content: str, **kwargs) -> Dict[str, Any]:
        try:
            safe_p = safe_path(self.repo_path, path)
            os.makedirs(os.path.dirname(safe_p), exist_ok=True)
            with open(safe_p, "w") as f:
                f.write(content)
            return {"status": "success", "path": path}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
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

    def execute(self, pattern: str, directory: str = ".", **kwargs) -> Dict[str, Any]:
        try:
            safe_dir = safe_path(self.repo_path, directory)
            # Use grep for search, ignoring binary and obvious dirs
            cmd = ["grep", "-rnI", "--exclude-dir=.git", "--exclude-dir=venv", "--exclude-dir=__pycache__", pattern, safe_dir]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            output = result.stdout
            if len(output) > 10000:
                output = output[:10000] + "\n...[TRUNCATED]"
                
            return {"status": "success", "results": output}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
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

    def execute(self, directory: str = ".", depth: int = 2, **kwargs) -> Dict[str, Any]:
        try:
            safe_dir = safe_path(self.repo_path, directory)
            cmd = ["find", safe_dir, "-maxdepth", str(depth), "-not", "-path", "*/.git/*", "-not", "-path", "*/venv/*", "-not", "-path", "*/__pycache__/*"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return {"status": "success", "tree": result.stdout}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object", 
            "properties": {
                "directory": {"type": "string"},
                "depth": {"type": "integer"}
            }
        }
