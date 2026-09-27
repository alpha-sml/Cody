"""Shared subprocess environment sanitization.

Every subprocess Cody launches to execute target-repository commands MUST use
``sanitized_env()`` so that evaluator credentials are never leaked to the
target code.
"""

import os
from typing import Dict

# Substrings and prefixes that identify sensitive runtime credentials,
# tokens, cloud secrets, or IDE metadata.
_SENSITIVE_SUBSTRINGS = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "AUTH_TOKEN",
    "BEARER",
)

_SENSITIVE_PREFIXES = (
    "ANTIGRAVITY_",
    "GITHUB_",
    "GH_",
    "AWS_",
    "GCP_",
    "AZURE_",
)


def sanitized_env() -> Dict[str, str]:
    """Return a copy of ``os.environ`` with all credential keys removed."""
    env = os.environ.copy()
    for key in list(env.keys()):
        k_upper = key.upper()
        if (
            any(sub in k_upper for sub in _SENSITIVE_SUBSTRINGS)
            or any(k_upper.startswith(p) for p in _SENSITIVE_PREFIXES)
        ):
            env.pop(key, None)
    return env
