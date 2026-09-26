from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        pass

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema()
        }
