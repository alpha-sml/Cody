from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseModelClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generate structured action.
        Returns a dict representing the action to take.
        """
        pass
