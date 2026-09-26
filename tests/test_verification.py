from src.harness.verification.verifier import Verifier
from src.harness.verification.test_runner import TestRunner

def test_verifier_mock():
    class MockRunner(TestRunner):
        def run_tests(self):
            return {"status": "success", "exit_code": 0, "stdout": "pass"}

    verifier = Verifier(MockRunner("."), ".")
    res = verifier.verify()
    assert res["verified"] is True
