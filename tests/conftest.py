import os
import pytest

@pytest.fixture(autouse=True)
def isolate_test_environment():
    """Ensure all test modules execute with a clean, isolated environment.

    Strips ambient CODY_* and harness configuration variables that may be set
    in the evaluator's outer terminal session, guaranteeing test hermeticity.
    """
    keys_to_clean = [
        "CODY_PROVIDER",
        "CODY_MODEL",
        "CODY_LOCKED_MODEL",
        "CODY_TASK",
        "MOCK_MODEL",
        "DEEPSEEK_BASE_URL",
        "QWEN_BASE_URL",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys_to_clean}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
