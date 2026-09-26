from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseModelClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, tools: List[Dict[str, Any]] = None) -> str:
        pass
