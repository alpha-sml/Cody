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
export AI_API_KEY="your-key"
make setup
```

## Running
```bash
make run ARGS="--task 'Add new route'"
```
Or directly:
```bash
python -m src.harness.main --task "Fix authentication bug"
```

## Testing
```bash
make test
```

## Mock Mode
To test locally without an API key, use the deterministic mock model:
```bash
MOCK_MODEL=true make run ARGS="--task 'test_write'"
```

## Configuration
`config/config.yaml` contains limits for iterations, recovery attempts, and model selection.
