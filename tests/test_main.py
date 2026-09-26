from types import SimpleNamespace
import sys

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
    output = capsys.readouterr().out
    assert "Starting harness for task: Fix the auth flow" in output
    assert "Finished with status: success" in output


def test_cli_requires_task(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["cody"])

    with pytest.raises(SystemExit) as exit_info:
        main_module.main()

    assert exit_info.value.code == 1
    assert "Error: --task argument is required." in capsys.readouterr().out
