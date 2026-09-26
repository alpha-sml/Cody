from typing import List, Dict, Any
import json

class ContextManager:
    def __init__(self):
        self.repository_tree: str = ""
        self.relevant_files: List[str] = []
        self.file_contents: Dict[str, str] = {}
        self.tool_results: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    def set_tree(self, tree: str):
        self.repository_tree = tree

    def add_relevant_file(self, path: str):
        if path not in self.relevant_files:
            self.relevant_files.append(path)

    def add_file_content(self, path: str, content: str):
        self.file_contents[path] = content

    def add_tool_result(self, result: Dict[str, Any]):
        self.tool_results.append(result)

    def add_error(self, error: str):
        self.errors.append(error)

    def get_context_dict(self) -> Dict[str, Any]:
        return {
            "repository_tree": self.repository_tree,
            "relevant_files": self.relevant_files,
            "file_contents": self.file_contents,
            "tool_results": self.tool_results[-5:], # Keep last 5 for context bounding
            "errors": self.errors[-5:]
        }
    
    def get_context_str(self) -> str:
        return json.dumps(self.get_context_dict(), indent=2)

    def clear(self):
        self.repository_tree = ""
        self.relevant_files = []
        self.file_contents = {}
        self.tool_results = []
        self.errors = []
