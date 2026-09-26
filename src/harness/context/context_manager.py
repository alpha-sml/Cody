from typing import List, Dict, Any, Optional, Set
import json
import re
import os


class ContextManager:
    def __init__(self, max_files: int = 10):
        self.max_files = max_files
        self.repository_tree: str = ""
        self.relevant_files: List[str] = []
        self.file_contents: Dict[str, str] = {}
        self.file_priorities: Dict[str, int] = {}
        self.task_files: Set[str] = set()
        self.task_symbols: Set[str] = set()
        self.tool_results: List[Dict[str, Any]] = []
        self.verification_results: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.git_status: str = ""
        self.git_diff: str = ""

    def set_task(self, task_text: str):
        """Extract explicit files and symbols from task description."""
        if not task_text:
            return
        # Extract explicit file paths: e.g. path/to/file.ext or file.ext
        files = re.findall(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+", task_text)
        self.task_files.update(f.strip() for f in files if not f.endswith("."))

        # Extract identifier symbols (CamelCase or snake_case >= 3 chars)
        symbols = re.findall(r"\b(?:[A-Z][a-zA-Z0-9]+|[a-z_][a-z0-9_]{2,})\b", task_text)
        # Filter common words
        common_words = {"the", "and", "for", "with", "this", "that", "from", "when", "then", "have", "make", "task", "file", "code"}
        self.task_symbols.update(s for s in symbols if s.lower() not in common_words)

    def _determine_priority(self, path: str, content: str = "") -> int:
        """Score priority based on task relevance.

        100: Explicit filename mentioned in task
        80: Symbols/classes mentioned in task
        60: Mutated / changed files
        40: Search result matches
        20: Default / incidental read
        """
        base = os.path.basename(path)
        if path in self.task_files or base in self.task_files or any(tf in path for tf in self.task_files):
            return 100
        if any(sym in path or (content and sym in content) for sym in self.task_symbols):
            return 80
        return 20

    def add_relevant_file(self, path: str, priority: Optional[int] = None):
        if priority is None:
            priority = self._determine_priority(path)

        if path not in self.relevant_files:
            self.relevant_files.append(path)
            self.file_priorities[path] = priority

            # Bounded working set: evict lowest priority file
            if len(self.relevant_files) > self.max_files:
                self._evict_lowest_priority()
        else:
            # Upgrade priority if higher
            self.file_priorities[path] = max(self.file_priorities.get(path, 0), priority)

    def _evict_lowest_priority(self):
        """Evict file with the lowest priority score, using FIFO for ties."""
        min_prio = min(self.file_priorities.get(f, 20) for f in self.relevant_files)
        # Find oldest file with min priority
        evict_target = None
        for f in self.relevant_files:
            if self.file_priorities.get(f, 20) == min_prio:
                evict_target = f
                break
        if evict_target:
            self.relevant_files.remove(evict_target)
            self.file_priorities.pop(evict_target, None)
            self.file_contents.pop(evict_target, None)

    def set_tree(self, tree: str):
        self.repository_tree = tree[:5000] + ("\n...[TRUNCATED]" if len(tree) > 5000 else "")

    def add_file_content(self, path: str, content: str, priority: Optional[int] = None):
        if priority is None:
            priority = self._determine_priority(path, content)
        self.add_relevant_file(path, priority=priority)
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
        elif tool == "file_search" and "results" in res:
            self.tool_results.append(result)
            if len(self.tool_results) > 5:
                self.tool_results.pop(0)
            # Extract matched files and register them with search priority 40
            matches = re.findall(r"^([^:\n]+):", res["results"], re.MULTILINE)
            for m in matches[:5]:
                self.add_relevant_file(m.strip(), priority=40)
        elif tool in ["file_write", "apply_patch"]:
            path = args.get("path")
            if path:
                self.add_relevant_file(path, priority=60)
            self.tool_results.append(result)
            if len(self.tool_results) > 5:
                self.tool_results.pop(0)
        elif tool == "git_status":
            self.git_status = str(res.get("output", ""))[:5000]
        elif tool == "git_diff":
            self.git_diff = str(res.get("output", ""))[:10000]
        else:
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
        self.file_priorities = {}
        self.task_files = set()
        self.task_symbols = set()
        self.tool_results = []
        self.verification_results = []
        self.errors = []
        self.git_status = ""
        self.git_diff = ""

