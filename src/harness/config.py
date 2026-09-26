import os
import yaml
from pydantic import BaseModel, Field

class ModelConfig(BaseModel):
    name: str
    provider: str
    max_tokens: int = 8192

class AgentConfig(BaseModel):
    max_iterations: int = 15
    timeout_seconds: int = 300
    max_recovery_attempts: int = 3
    test_command: str = "make test"

class HarnessConfig(BaseModel):
    model: ModelConfig
    agent: AgentConfig

def load_config(path: str = "config/config.yaml") -> HarnessConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return HarnessConfig(**data)
