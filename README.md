# Cody — AI Coding Harness

Cody is an autonomous AI coding agent that receives a programming task, plans a solution, modifies code, runs tests, verifies results, and recovers from failures — all without human intervention.

## Architecture

```
Task → Planner → Orchestrator → Tools → Verifier → Recovery (if needed) → Complete
```

| Component | Purpose |
|-----------|---------|
| **Orchestrator** | Central loop: PLAN → EXECUTE → VERIFY → RECOVER |
| **Planner** | Generates structured step-by-step plans via the model |
| **Tools** | File I/O, shell, git, search — all sandboxed |
| **Verifier** | Runs target tests, inspects repo changes, validates completion |
| **Recovery** | Classifies failures and generates corrective actions |
| **Context Manager** | Maintains bounded, task-relevant context for model calls |

## Quick Start

### Evaluator Workflow

```bash
git clone <TEAM_REPOSITORY>
cd <TEAM_REPOSITORY>
export AI_API_KEY="<PROVIDED_API_KEY>"
make setup
make run
```

Then provide the task via stdin:
```bash
echo "Fix the authentication flow in login.py" | make run
```

Or use the `CODY_TASK` environment variable:
```bash
export CODY_TASK="Fix the authentication flow"
make run
```

### Local Development

```bash
make setup
export AI_API_KEY="your-key"
make run ARGS="--task 'Fix the authentication flow' --repo /path/to/target"
```

## Configuration

### Model Configuration

Default configuration in `config/config.yaml`:
```yaml
model:
  name: "deepseek-chat"
  provider: "deepseek"
  max_tokens: 8192
```

Override via environment variables (no source code changes needed):
```bash
export CODY_MODEL="custom-model-name"
export CODY_PROVIDER="deepseek"  # or "qwen"
```

Override via CLI flags:
```bash
make run ARGS="--task 'Fix bug' --model qwen-turbo --provider qwen"
```

### Supported Providers

| Provider | API Base | Model Examples |
|----------|----------|----------------|
| `deepseek` | `api.deepseek.com` | `deepseek-chat` |
| `qwen` | `dashscope.aliyuncs.com` | `qwen-max`, `qwen-turbo` |
| `mock` | (local) | Testing only |

## Credential Handling

### Evaluation Mode
- Set `AI_API_KEY` — this is the **primary** credential interface
- Provider-specific keys (`DEEPSEEK_API_KEY`, `QWEN_API_KEY`) are fallbacks for local dev

### Security Boundaries
- API credentials are **never** passed to target-repository subprocesses
- Credentials are **never** logged, printed, or written to files
- All subprocess execution uses `sanitized_env()` which strips sensitive keys
- `.env` is in `.gitignore` — never committed

## Task Input Protocol

Cody accepts tasks via three mechanisms (checked in order):

1. **CLI flag**: `--task "Fix the bug"`
2. **Environment variable**: `CODY_TASK="Fix the bug"`
3. **stdin**: Pipe or type the task interactively

All inputs are normalized to a `TaskSpec`:
```python
TaskSpec(
    title="Fix the bug",
    description="Fix the bug in login.py",
    acceptance_criteria=["Tests pass"],
    source="stdin",  # cli | stdin | env
)
```

## Testing

```bash
make test
```

Test categories:
- **CLI**: startup modes, task resolution, provider override
- **Configuration**: model validation, placeholder rejection
- **API key handling**: priority, fallback, missing credentials
- **Credential isolation**: subprocess env stripping, attack vector tests
- **Tools**: file I/O, shell, git, patch, search, path safety
- **Orchestration**: full loop, recovery, completion gate
- **Evaluation**: end-to-end smoke tests simulating evaluator workflow

## Evaluator Workflow Summary

```
1. git clone → cd → export AI_API_KEY
2. make setup                          # creates venv, installs deps
3. echo "task description" | make run  # launches Cody with task
4. Cody: PLAN → INSPECT → MODIFY → TEST → VERIFY → COMPLETE
5. Evaluation report printed to stdout as JSON
```

## Development

```bash
# Run with mock provider (no API key needed)
export MOCK_MODEL=true
make run ARGS="--task 'Test task'"

# Run specific test file
PYTHONPATH=. ./venv/bin/pytest tests/test_evaluator.py -v
```
