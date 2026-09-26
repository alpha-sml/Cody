from typing import List, Dict, Any
import json

class ContextManager:
    def __init__(self):
        self.repository_tree: str = ""
        self.relevant_files: List[str] = []
        self.file_contents: Dict[str, str] = {}
        self.tool_results: List[Dict[str, Any]] = []
        self.verification_results: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.git_status: str = ""
        self.git_diff: str = ""

    def set_tree(self, tree: str):
        self.repository_tree = tree[:5000] + ("\n...[TRUNCATED]" if len(tree) > 5000 else "")

    def add_relevant_file(self, path: str):
        if path not in self.relevant_files:
            self.relevant_files.append(path)
            # bounded working set
            if len(self.relevant_files) > 10:
                oldest = self.relevant_files.pop(0)
                if oldest in self.file_contents:
                    del self.file_contents[oldest]

    def add_file_content(self, path: str, content: str):
        self.add_relevant_file(path)
        self.file_contents[path] = content[:10000] + ("\n...[TRUNCATED]" if len(content) > 10000 else "")

    def add_tool_result(self, result: Dict[str, Any]):
        tool = result.get("tool")
        args = result.get("args", {})
        res = result.get("result", {})

        if tool == "file_read" and "content" in res:
            path = args.get("path")
            if path:
                lines_info = f" (Lines {args.get('start_line', 1)}-{args.get('end_line', 'EOF')})" if 'start_line' in args else ""
                header = f"--- {path}{lines_info} ---\n"
                self.add_file_content(path, header + res["content"])
        elif tool == "git_status":
            self.git_status = str(res.get("output", ""))[:5000]
        elif tool == "git_diff":
            self.git_diff = str(res.get("output", ""))[:10000]
        else:
            # For file_search or other tools
            self.tool_results.append(result)
            if len(self.tool_results) > 5:
                self.tool_results.pop(0)

    def add_error(self, error: str):
        self.errors.append(error)
        if len(self.errors) > 5:
            self.errors.pop(0)

    def add_verification_result(self, result: Dict[str, Any]):
        self.verification_results.append(result)
        if len(self.verification_results) > 3:
            self.verification_results.pop(0)

    def get_context_dict(self) -> Dict[str, Any]:
        d = {
            "repository_tree": self.repository_tree,
            "relevant_files": self.relevant_files,
            "file_contents": self.file_contents,
            "tool_results": self.tool_results,
            "verification_results": self.verification_results,
            "errors": self.errors
        }
        if self.git_status:
            d["git_status"] = self.git_status
        if self.git_diff:
            d["git_diff"] = self.git_diff
        return d
    
    def get_context_str(self) -> str:
        return json.dumps(self.get_context_dict(), indent=2)

    def clear(self):
        self.repository_tree = ""
        self.relevant_files = []
        self.file_contents = {}
        self.tool_results = []
        self.verification_results = []
        self.errors = []
        self.git_status = ""
        self.git_diff = ""
