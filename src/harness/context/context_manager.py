from typing import List, Dict, Any

class ContextManager:
    def __init__(self):
        self.context: List[str] = []

    def add_context(self, text: str):
        self.context.append(text)

    def get_context(self) -> str:
        return "\n".join(self.context)

    def clear(self):
        self.context = []
