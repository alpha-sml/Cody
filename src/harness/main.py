import argparse
import sys
import os
from .config import load_config
from .state import State
from .model.client import get_client
from .tools.registry import ToolRegistry
from .tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool
from .tools.shell import ShellTool
from .tools.git import GitStatusTool, GitDiffTool
from .verification.verifier import Verifier
from .verification.test_runner import TestRunner
from .recovery.recovery import RecoveryManager
from .orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="AI Coding Harness")
    parser.add_argument("--repo", type=str, default=".", help="Path to repository")
    parser.add_argument("--task", type=str, default="", help="Coding task description")
    args = parser.parse_args()

    config = load_config()

    try:
        model_client = get_client(config.model.name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    registry = ToolRegistry()
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(FileSearchTool())
    registry.register(ShellTool())
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())

    test_runner = TestRunner(args.repo)
    verifier = Verifier(test_runner)
    recovery_manager = RecoveryManager(model_client)

    orchestrator = Orchestrator(
        model_client=model_client,
        tool_registry=registry,
        verifier=verifier,
        recovery_manager=recovery_manager,
        max_iterations=config.agent.max_iterations
    )

    state = State(
        task=args.task,
        repo_path=args.repo
    )

    print("Starting harness...")
    final_state = orchestrator.run(state)
    print(f"Finished with status: {final_state.status}")
    print(f"Result: {final_state.final_result}")

if __name__ == "__main__":
    main()
