from types import SimpleNamespace
import sys
import os

import pytest

from src.harness import main as main_module


def test_cli_task_and_repo_reach_initial_state(monkeypatch, tmp_path, capsys):
    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            captured["orchestrator"] = kwargs

        def run(self, state):
            captured["state"] = state
            state.status = "success"
            state.final_result = "ok"
            return state

    monkeypatch.setattr(main_module, "get_client", lambda *args: object())
    monkeypatch.setattr(main_module, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cody", "--repo", str(tmp_path), "--task", "Fix the auth flow"],
    )

    main_module.main()

    assert captured["state"].task == "Fix the auth flow"
    assert captured["state"].repo_path == str(tmp_path)
    assert captured["state"].task_spec is not None
    assert captured["state"].task_spec.source == "cli"
    output = capsys.readouterr().out
    assert "Starting harness for task:" in output
    assert "Finished with status: success" in output


def test_cli_missing_task_no_stdin_exits(monkeypatch, capsys):
    """When no --task, no CODY_TASK, and stdin is empty, must exit with error."""
    import io
    monkeypatch.setattr(sys, "argv", ["cody"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.delenv("CODY_TASK", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    assert exit_info.value.code == 1
    assert "No task provided" in capsys.readouterr().out


def test_cli_task_from_env(monkeypatch, tmp_path, capsys):
    """CODY_TASK env var provides task when --task is absent."""
    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass
        def run(self, state):
            captured["state"] = state
            state.status = "success"
            state.final_result = "ok"
            return state

    monkeypatch.setattr(main_module, "get_client", lambda *args: object())
    monkeypatch.setattr(main_module, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path)])
    monkeypatch.setenv("CODY_TASK", "Fix from env")

    main_module.main()

    assert captured["state"].task == "Fix from env"
    assert captured["state"].task_spec.source == "env"


def test_cli_task_from_stdin(monkeypatch, tmp_path, capsys):
    """Piped stdin provides task when --task and CODY_TASK are absent."""
    import io
    captured = {}

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass
        def run(self, state):
            captured["state"] = state
            state.status = "success"
            state.final_result = "ok"
            return state

    monkeypatch.setattr(main_module, "get_client", lambda *args: object())
    monkeypatch.setattr(main_module, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(sys, "argv", ["cody", "--repo", str(tmp_path)])
    monkeypatch.delenv("CODY_TASK", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Fix the auth flow from stdin"))

    main_module.main()

    assert captured["state"].task == "Fix the auth flow from stdin"
    assert captured["state"].task_spec.source == "stdin"


def test_cli_provider_override(monkeypatch, tmp_path, capsys):
    captured = {}
    def mock_get_client(model_name, provider):
        captured["model_name"] = model_name
        captured["provider"] = provider
        return object()

    monkeypatch.setattr(main_module, "get_client", mock_get_client)
    monkeypatch.setattr(main_module, "Orchestrator", lambda **kwargs: type("M", (), {"run": lambda self, state: state})())

    monkeypatch.setattr(
        sys,
        "argv",
        ["cody", "--task", "test task", "--provider", "qwen", "--model", "qwen-turbo"],
    )

    main_module.main()

    assert captured["provider"] == "qwen"
    assert captured["model_name"] == "qwen-turbo"
