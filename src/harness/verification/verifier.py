from .test_runner import TestRunner
from typing import Dict, Any

class Verifier:
    def __init__(self, test_runner: TestRunner):
        self.test_runner = test_runner

    def verify(self) -> Dict[str, Any]:
        result = self.test_runner.run_tests()
        if result["status"] == "success" and result["exit_code"] == 0:
            return {"verified": True, "details": result}
        else:
            return {"verified": False, "details": result}
