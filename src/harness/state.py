from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class TaskSpec(BaseModel):
    """Normalized task representation for evaluation input."""
    title: str = ""
    description: str = ""
    acceptance_criteria: List[str] = Field(default_factory=list)
    referenced_files: List[str] = Field(default_factory=list)
    referenced_symbols: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    expected_behavior: List[str] = Field(default_factory=list)
    verification_hints: List[str] = Field(default_factory=list)
    source: str = "cli"  # cli | stdin | env
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def summary(self) -> str:
        """Single-line summary for prompts."""
        return self.title or self.description[:200] or "(no task)"

    @classmethod
    def from_text(cls, task_text: str, source: str = "cli") -> "TaskSpec":
        """Deterministic extraction of task sections, criteria, files, and symbols."""
        import re

        clean_text = task_text.strip()
        if not clean_text:
            return cls(source=source)

        lines = clean_text.splitlines()
        first_line = lines[0].strip() if lines else ""
        title = first_line[:200]

        # Section header patterns
        section_headers = {
            "acceptance_criteria": re.compile(r"^\s*(?:###?\s*)?acceptance criteria\s*:?\s*$", re.IGNORECASE),
            "expected_behavior": re.compile(r"^\s*(?:###?\s*)?expected behavior\s*:?\s*$", re.IGNORECASE),
            "referenced_files": re.compile(r"^\s*(?:###?\s*)?(?:files|referenced files|files to change)\s*:?\s*$", re.IGNORECASE),
            "referenced_symbols": re.compile(r"^\s*(?:###?\s*)?(?:symbols|referenced symbols)\s*:?\s*$", re.IGNORECASE),
            "constraints": re.compile(r"^\s*(?:###?\s*)?constraints\s*:?\s*$", re.IGNORECASE),
            "verification_hints": re.compile(r"^\s*(?:###?\s*)?(?:verification|verification hints)\s*:?\s*$", re.IGNORECASE),
        }

        current_section = None
        parsed_sections: Dict[str, List[str]] = {k: [] for k in section_headers}

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Check if this line is a section header
            matched_header = False
            for sec_name, pattern in section_headers.items():
                if pattern.match(line_stripped):
                    current_section = sec_name
                    matched_header = True
                    break

            if matched_header:
                continue

            # If inside a recognized section, parse list items
            if current_section:
                # Check for bullet points or numbered lists: '-', '*', '1.', '1)', etc.
                item_match = re.match(r"^(?:[-*•]|\d+[.)])\s*(.+)$", line_stripped)
                if item_match:
                    item_text = item_match.group(1).strip()
                    if item_text:
                        parsed_sections[current_section].append(item_text)
                elif not line.startswith(" ") and not line.startswith("\t") and line_stripped.endswith(":"):
                    # New unknown section header
                    current_section = None
                else:
                    # Multi-line item or plain text in section
                    if parsed_sections[current_section]:
                        parsed_sections[current_section][-1] += " " + line_stripped
                    else:
                        parsed_sections[current_section].append(line_stripped)

        # Extract file paths across the entire text: e.g. path/to/file.ext or file.ext
        file_candidates = re.findall(r"\b(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b", clean_text)
        extracted_files = []
        for fc in file_candidates:
            # Filter non-file patterns like version numbers "3.11" or urls
            if not fc.endswith(".") and not re.match(r"^\d+\.\d+$", fc) and fc not in extracted_files:
                extracted_files.append(fc)

        # Merge files extracted from section and from text
        for f in parsed_sections["referenced_files"]:
            clean_f = f.strip().strip("`'\"")
            if clean_f and clean_f not in extracted_files:
                extracted_files.append(clean_f)

        # Extract symbol names (e.g. def foo, class Bar, symbol(arg), CamelCase or snake_case >= 3 chars)
        extracted_symbols = []
        for s in parsed_sections["referenced_symbols"]:
            clean_s = s.strip().strip("`'\"")
            if clean_s and clean_s not in extracted_symbols:
                extracted_symbols.append(clean_s)

        func_matches = re.findall(r"\b(?:def|class|fn|function)\s+([a-zA-Z_][a-zA-Z0-9_]*)", clean_text)
        call_matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)", clean_text)
        for sym in func_matches + call_matches:
            if sym not in ("def", "class", "fn", "function", "if", "for", "while", "return", "pass", "import") and sym not in extracted_symbols:
                extracted_symbols.append(sym)

        return cls(
            title=title,
            description=clean_text,
            acceptance_criteria=parsed_sections["acceptance_criteria"],
            referenced_files=extracted_files,
            referenced_symbols=extracted_symbols,
            constraints=parsed_sections["constraints"],
            expected_behavior=parsed_sections["expected_behavior"],
            verification_hints=parsed_sections["verification_hints"],
            source=source,
        )

class State(BaseModel):
    task: str = ""
    task_spec: Optional[TaskSpec] = None
    repo_path: str = ""
    status: str = "init"
    phase: str = "INITIALIZE"
    plan: List[str] = []
    current_step: Optional[str] = None
    structured_plan: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    tool_history: List[Dict[str, Any]] = Field(default_factory=list)
    plan_step_history: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_repository: Dict[str, Any] = Field(default_factory=dict)
    evaluation_report: Dict[str, Any] = Field(default_factory=dict)
    changed_files: List[str] = Field(default_factory=list)
    verification_results: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    iteration: int = 0
    recovery_attempts: int = 0
    final_result: Optional[str] = None
