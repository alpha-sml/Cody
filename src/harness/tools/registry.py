from .base import BaseTool
from typing import Dict, List, Optional

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)

    def get_all_schemas(self) -> List[Dict]:
        return [tool.schema() for tool in self.tools.values()]

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())
