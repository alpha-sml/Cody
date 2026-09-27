"""Shared subprocess environment sanitization.

Every subprocess Cody launches to execute target-repository commands MUST use
``sanitized_env()`` so that evaluator credentials are never leaked to the
target code.
"""

import os
from typing import Dict

# Keys that must be stripped from subprocess environments used to run
# target-repository commands.  Cody's own model-API calls read these
# directly from ``os.environ`` — they are NOT affected.
_SENSITIVE_KEYS = frozenset([
    "AI_API_KEY",
    "DEEPSEEK_API_KEY",
    "QWEN_API_KEY",
])

_SENSITIVE_PREFIXES = (
    "ANTIGRAVITY_",
)


def sanitized_env() -> Dict[str, str]:
    """Return a copy of ``os.environ`` with all credential keys removed."""
    env = os.environ.copy()
    for key in list(env.keys()):
        k_upper = key.upper()
        if k_upper in _SENSITIVE_KEYS or any(k_upper.startswith(p) for p in _SENSITIVE_PREFIXES):
            env.pop(key, None)
    return env
