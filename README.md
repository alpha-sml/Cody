# AI Coding Harness Base

## Purpose
A strong, extensible base repository for building an autonomous coding agent harness around a foundation model during a hackathon.

## Architecture
The harness features an Orchestrator loop communicating with a Foundation Model. It manages Context, executes Tools, Verifies changes via tests, and invokes a Recovery module if tests fail.

## Installation
```bash
export AI_API_KEY="..." # Your API Key
make setup
```

## Running
```bash
make run
```
You can also run directly with arguments:
```bash
./venv/bin/python -m src.harness.main --repo . --task "Add a new feature"
```

## Testing
```bash
make test
```

## Configuration
See `config/config.yaml` to change model or agent limits.

## Extensions for Hackathon
- Improve context management (chunking, RAG)
- Expand toolset
- Enhance model prompt parsing
- Refine recovery strategies
