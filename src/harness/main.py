import argparse
import json
import os
import select
import sys
from .config import load_config
from .state import State, TaskSpec
from .model.client import get_client
from .tools.registry import ToolRegistry
from .tools.file_tools import FileReadTool, FileWriteTool, FileSearchTool, RepoTreeTool, ApplyPatchTool
from .tools.shell import ShellTool
from .tools.git import GitStatusTool, GitDiffTool, GitLogTool
from .tools.code_tools import RunTestTool, InspectProjectTool, FindSymbolTool, FindReferencesTool
from .verification.verifier import Verifier
from .verification.test_runner import TestRunner
from .recovery.recovery import RecoveryManager
from .context.context_manager import ContextManager
from .planner import Planner
from .orchestrator import Orchestrator

_STDIN_TIMEOUT = 300  # seconds to wait for evaluator input


def _read_task_from_stdin(timeout: int = _STDIN_TIMEOUT) -> str:
    """Read task from stdin with timeout. Non-blocking on TTY."""
    if sys.stdin.isatty():
        print("Cody is ready. Enter task description (end with Ctrl-D or empty line):")
    else:
        # Piped input — read immediately
        pass

    lines = []
    try:
        # For piped input, just read all
        if not sys.stdin.isatty():
            task = sys.stdin.read().strip()
            return task

        # Interactive — read lines until empty line or EOF
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
            if not ready:
                break
            line = sys.stdin.readline()
            if not line:  # EOF
                break
            if line.strip() == "":
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass

    return "".join(lines).strip()


def _resolve_task(args) -> TaskSpec:
    """Resolve task from CLI args, env var, or stdin. Returns TaskSpec."""
    task_text = ""
    source = "cli"

    if args.task:
        task_text = args.task
        source = "cli"
    elif os.environ.get("CODY_TASK", "").strip():
        task_text = os.environ["CODY_TASK"].strip()
        source = "env"
    else:
        task_text = _read_task_from_stdin()
        source = "stdin"

    if not task_text:
        print("Error: No task provided. Supply via --task, CODY_TASK env var, or stdin.")
        sys.exit(1)

    return TaskSpec(
        title=task_text.split("\n")[0][:200],
        description=task_text,
        source=source,
    )


def main():
    parser = argparse.ArgumentParser(description="Cody AI Coding Harness")
    parser.add_argument("--repo", type=str, default=".", help="Path to target repository")
    parser.add_argument("--task", type=str, default="", help="Coding task description")
    parser.add_argument("--provider", type=str, default="", help="Override model provider (e.g. deepseek, qwen)")
    parser.add_argument("--model", type=str, default="", help="Override model ID")
    args = parser.parse_args()

    task_spec = _resolve_task(args)

    config = load_config()

    provider = args.provider if args.provider else config.model.provider
    provider = os.environ.get("CODY_PROVIDER", provider).lower().strip()

    if args.model:
        model_name = args.model
    elif os.environ.get("CODY_MODEL", "").strip():
        model_name = os.environ["CODY_MODEL"].strip()
    elif provider == "qwen" and config.model.name in ("deepseek-v4-flash", "deepseek-chat"):
        model_name = "qwen-plus"
    else:
        model_name = config.model.name

    try:
        model_client = get_client(model_name, provider)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    registry = ToolRegistry()
    registry.register(FileReadTool(args.repo))
    registry.register(FileWriteTool(args.repo))
    registry.register(ApplyPatchTool(args.repo))
    registry.register(FileSearchTool(args.repo))
    registry.register(RepoTreeTool(args.repo))
    registry.register(ShellTool(args.repo, timeout=config.agent.timeout_seconds))
    registry.register(GitStatusTool(args.repo))
    registry.register(GitDiffTool(args.repo))
    registry.register(GitLogTool(args.repo))
    registry.register(RunTestTool(args.repo, default_command=config.agent.test_command))
    registry.register(InspectProjectTool(args.repo))
    registry.register(FindSymbolTool(args.repo))
    registry.register(FindReferencesTool(args.repo))

    test_runner = TestRunner(args.repo, test_command=config.agent.test_command)
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
        task=task_spec.description,
        task_spec=task_spec,
        repo_path=args.repo,
        evaluation_report={
            "model_provider": provider,
            "model_name": model_name,
        },
    )

    print(f"Starting harness for task: {task_spec.summary}")
    final_state = orchestrator.run(state)
    print(f"Finished with status: {final_state.status}")
    print(f"Final Result: {final_state.final_result}")
    print(f"Evaluation: {json.dumps(final_state.evaluation_report, sort_keys=True)}")

if __name__ == "__main__":
    main()
