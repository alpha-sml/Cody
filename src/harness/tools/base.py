from abc import ABC, abstractmethod
from typing import Any, Dict


ToolResult = Dict[str, Any]
ToolSchema = Dict[str, Any]

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    category: str = "READ_ONLY"

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        pass

    @abstractmethod
    def get_parameters_schema(self) -> ToolSchema:
        pass

    def success_result(self, **data: Any) -> ToolResult:
        return {"status": "success", **data}

    def error_result(self, error: str, **data: Any) -> ToolResult:
        return {"status": "error", "error": error, **data}

    def schema(self) -> ToolSchema:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.get_parameters_schema()
        }
