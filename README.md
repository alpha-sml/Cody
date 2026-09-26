# Cody: Autonomous AI Coding Harness (Hackathon MVP)

## Purpose
A strong, reliable, and extensible MVP architecture for an autonomous coding agent harness. Designed to be the foundation for the AI Coding Harness Hackathon.

## Architecture
- **State**: Typed state tracking tasks, plans, and history.
- **Orchestrator**: A state-machine loop (Initialize → Plan → Execute → Verify → Recover).
- **Tools**: Workspace-bounded tools (`file_write`, `file_read`, `shell`, `git_diff`).
- **Context Manager**: Structured context maintenance (avoids huge whole-repo dumps).
- **Verifier**: First-class verification via actual tool execution (`make test`).
- **Recovery Manager**: Captures test failures and triggers replanning loop.

## Setup
```bash
make setup
```

Run commands from the repository root. The default configuration is loaded from
`config/config.yaml` and uses `make test` for verification. For a live provider,
set the configured provider's required credentials before starting the harness:

```bash
export AI_API_KEY="your-key"
```

## Running
```bash
make run ARGS="--task 'Add new route'"
```
Or directly:
```bash
PYTHONPATH=. ./venv/bin/python -m src.harness.main --task "Fix authentication bug"
```

`make run` passes `ARGS` directly to the CLI. The supported task input is the
required `--task` option; `--repo PATH` optionally selects the repository being
worked on. The received task is placed into the initial `State` and follows the
normal planner, execution, verification, recovery, and completion-gate path.

## Testing
```bash
make test
```

## Mock Mode
To test locally without an API key, use the deterministic mock model:
```bash
MOCK_MODEL=true make run ARGS="--task 'test_write'"
```

Mock mode avoids provider credentials and is deterministic for local smoke tests.

The CLI prints an `Evaluation` JSON summary after each run. It includes the task,
configured provider/model, planner/execution/recovery call counts, tool and
verification counts, recovery attempts, changed files, test result, completion
status, final status, and bounded errors. It never includes API keys.

## Configuration
`config/config.yaml` contains limits for iterations, recovery attempts, and model selection.
Successful completion requires passing verification plus repository evidence of
the task, such as an expected tracked or untracked change. Pre-existing changes
are captured as the baseline and are not attributed to Cody; unexpected changes
or missing meaningful evidence route through recovery instead of declaring success.
