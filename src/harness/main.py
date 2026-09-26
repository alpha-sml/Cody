import argparse
import sys
from .config import load_config
from .state import State
from .model.client import get_client
from .tools.registry import ToolRegistry
from .tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool, RepoTreeTool
from .tools.shell import ShellTool
from .tools.git import GitStatusTool, GitDiffTool
from .verification.verifier import Verifier
from .verification.test_runner import TestRunner
from .recovery.recovery import RecoveryManager
from .context.context_manager import ContextManager
from .planner import Planner
from .orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="AI Coding Harness MVP")
    parser.add_argument("--repo", type=str, default=".", help="Path to repository")
    parser.add_argument("--task", type=str, default="", help="Coding task description")
    args = parser.parse_args()

    if not args.task:
        print("Error: --task argument is required.")
        sys.exit(1)

    config = load_config()

    try:
        model_client = get_client(config.model.name)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    registry = ToolRegistry()
    registry.register(FileReadTool(args.repo))
    registry.register(FileWriteTool(args.repo))
    registry.register(FileSearchTool(args.repo))
    registry.register(RepoTreeTool(args.repo))
    registry.register(ShellTool(args.repo, timeout=config.agent.timeout_seconds))
    registry.register(GitStatusTool(args.repo))
    registry.register(GitDiffTool(args.repo))

    test_runner = TestRunner(args.repo)
    verifier = Verifier(test_runner, args.repo)
    recovery_manager = RecoveryManager(model_client)
    context_manager = ContextManager()
    planner = Planner(model_client)

    orchestrator = Orchestrator(
        model_client=model_client,
        tool_registry=registry,
        verifier=verifier,
        recovery_manager=recovery_manager,
        context_manager=context_manager,
        planner=planner,
        max_iterations=config.agent.max_iterations,
        max_recovery_attempts=config.agent.max_recovery_attempts
    )

    state = State(
        task=args.task,
        repo_path=args.repo
    )

    print(f"Starting harness for task: {args.task}")
    final_state = orchestrator.run(state)
    print(f"Finished with status: {final_state.status}")
    print(f"Final Result: {final_state.final_result}")

if __name__ == "__main__":
    main()
