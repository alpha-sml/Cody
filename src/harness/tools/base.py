from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        pass
