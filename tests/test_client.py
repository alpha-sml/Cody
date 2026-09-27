import os
import pathlib
import re
import requests
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from src.harness.model.boundary import validate_action, extract_json
from src.harness.model.client import get_client, validate_model_name
from src.harness.model.providers.deepseek import DeepSeekClient
from src.harness.model.providers.mock import MockClient
from src.harness.model.providers.qwen import QwenClient
from src.harness import main as main_module
from src.harness.state import TaskSpec


def test_validate_action_unknown_tool():
    tools = [{"name": "known_tool", "parameters": {"properties": {}}}]
    action = {"action": "tool_call", "tool": "unknown_tool", "arguments": {}}
    res = validate_action(action, tools=tools)
    assert res["action"] == "error"
    assert res["error_type"] == "unknown_tool"

def test_validate_action_missing_arguments():
    tools = [{
        "name": "my_tool",
        "parameters": {
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"]
        }
    }]
    action = {"action": "tool_call", "tool": "my_tool", "arguments": {}}
    res = validate_action(action, tools=tools)
    assert res["action"] == "error"
    assert res["error_type"] == "missing_argument"

def test_validate_action_invalid_argument_structure():
    tools = [{
        "name": "my_tool",
        "parameters": {
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"]
        }
    }]
    action = {"action": "tool_call", "tool": "my_tool", "arguments": {"arg1": "val", "arg2": "extra"}}
    res = validate_action(action, tools=tools)
    assert res["action"] == "error"
    assert res["error_type"] == "invalid_argument"

def test_extract_json_malformed():
    res = extract_json('```json\n{malformed: true}\n```')
    assert res["action"] == "error"
    assert res["error_type"] == "invalid_model_response"

def test_extract_json_prose_surrounding():
    res = extract_json('Here is the json you requested:\n```json\n{"action": "finish", "result": "ok"}\n```\nHope this helps!')
    assert res["action"] == "finish"
    assert res["result"] == "ok"

def test_extract_json_empty():
    res = extract_json('   ')
    assert res["action"] == "error"
    assert res["error_type"] == "empty_response"

def test_extract_json_multiple_actions():
    text = '```json\n{"action": "finish", "result": "1"}\n```\n```json\n{"action": "finish", "result": "2"}\n```'
    res = extract_json(text)
    assert res["action"] == "error"
    assert res["error_type"] == "multiple_actions"

def test_validate_action_invalid_argument_type():
    tools = [{
        "name": "my_tool",
        "parameters": {
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"]
        }
    }]
    action = {"action": "tool_call", "tool": "my_tool", "arguments": {"arg1": 123}}
    res = validate_action(action, tools=tools)
    assert res["action"] == "error"
    assert res["error_type"] == "invalid_argument_type"

def test_deepseek_client_function_call_parsing():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "file_write",
                                "arguments": "{\"path\": \"test.py\", \"content\": \"print('hello')\"}"
                            }
                        }
                    ]
                }
            }
        ]
    }
    tools = [{"name": "file_write", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}]
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt", tools=tools)
    assert action == {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.py", "content": "print('hello')"}}

def test_deepseek_client_json_text_parsing():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "```json\n{\"action\": \"finish\", \"result\": \"done\"}\n```"
                }
            }
        ]
    }
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt")
    assert action == {"action": "finish", "result": "done"}

def test_deepseek_client_timeout():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-v4-flash")
    with patch('requests.post', side_effect=requests.exceptions.Timeout):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_timeout"

def test_deepseek_client_provider_error():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"

def test_deepseek_client_malformed_response():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []} # No choices
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"

def test_qwen_client_function_call_parsing():
    client = QwenClient(api_key="fake", model_name="qwen-max")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "file_write",
                                "arguments": "{\"path\": \"test.py\", \"content\": \"print('hello')\"}"
                            }
                        }
                    ]
                }
            }
        ]
    }
    tools = [{"name": "file_write", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}]
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt", tools=tools)
    assert action == {"action": "tool_call", "tool": "file_write", "arguments": {"path": "test.py", "content": "print('hello')"}}

def test_qwen_client_json_text_parsing():
    client = QwenClient(api_key="fake", model_name="qwen-max")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "```json\n{\"action\": \"finish\", \"result\": \"done\"}\n```"
                }
            }
        ]
    }
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt")
    assert action == {"action": "finish", "result": "done"}

def test_qwen_client_timeout():
    client = QwenClient(api_key="fake", model_name="qwen-max")
    with patch('requests.post', side_effect=requests.exceptions.Timeout):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_timeout"

def test_qwen_client_provider_error():
    client = QwenClient(api_key="fake", model_name="qwen-max")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"

def test_qwen_client_malformed_response():
    client = QwenClient(api_key="fake", model_name="qwen-max")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []} # No choices
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"


@pytest.fixture(autouse=True)
def clean_env_for_client_tests():
    """Ensure no leaked env vars between tests."""
    keys = [
        "AI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY",
        "CODY_PROVIDER", "CODY_MODEL", "MOCK_MODEL",
        "CODY_LOCKED_MODEL",
        "DEEPSEEK_BASE_URL", "QWEN_BASE_URL",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def test_get_client_with_ai_api_key():
    """AI_API_KEY is the primary credential (evaluator interface)."""
    os.environ["AI_API_KEY"] = "eval-key"
    client = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "eval-key"
    assert client.model_name == "deepseek-v4-flash"


def test_get_client_ai_api_key_takes_priority():
    """AI_API_KEY takes priority over provider-specific keys."""
    os.environ["AI_API_KEY"] = "eval-key"
    os.environ["DEEPSEEK_API_KEY"] = "ds-key"
    client = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "eval-key"


def test_get_client_provider_key_fallback():
    """Provider-specific key works when AI_API_KEY is absent."""
    os.environ["DEEPSEEK_API_KEY"] = "ds-key"
    client = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "ds-key"


def test_get_client_explicit_qwen():
    os.environ["QWEN_API_KEY"] = "qw-key"
    client = get_client("qwen-max", "qwen")
    assert isinstance(client, QwenClient)
    assert client.api_key == "qw-key"


def test_get_client_explicit_mock():
    client = get_client("any-model", "mock")
    assert isinstance(client, MockClient)


def test_get_client_case_insensitive():
    os.environ["QWEN_API_KEY"] = "qw-key"
    client = get_client("qwen-max", " QWEN ")
    assert isinstance(client, QwenClient)


def test_get_client_unsupported():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_client("model", "unsupported")


def test_get_client_missing_credentials():
    """Clear error when no API key is set."""
    with pytest.raises(ValueError, match="No API key found"):
        get_client("deepseek-v4-flash", "deepseek")


def test_validate_model_name_rejects_placeholder():
    """Placeholder model names must fail fast."""
    with pytest.raises(ValueError, match="placeholder"):
        validate_model_name("<CONFIRMED_DEEPSEEK_MODEL>")


def test_validate_model_name_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_model_name("")


def test_validate_model_name_accepts_real():
    assert validate_model_name("deepseek-v4-flash") == "deepseek-v4-flash"
    assert validate_model_name("deepseek-chat") == "deepseek-chat"


def test_get_client_env_overrides(monkeypatch):
    """CODY_PROVIDER and CODY_MODEL env vars override arguments."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "mock"
    client = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(client, MockClient)


def test_credentials_never_logged(capsys):
    """API key value must never appear in stdout/stderr."""
    os.environ["AI_API_KEY"] = "super-secret-key-12345"
    _ = get_client("deepseek-v4-flash", "deepseek")
    output = capsys.readouterr()
    assert "super-secret-key-12345" not in output.out
    assert "super-secret-key-12345" not in output.err


def test_approved_providers_accepted_with_ai_api_key():
    """Both DeepSeek and Qwen are approved evaluation providers."""
    os.environ["AI_API_KEY"] = "eval-key"
    ds = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(ds, DeepSeekClient)
    assert ds.model_name == "deepseek-v4-flash"

    qw = get_client("qwen-max", "qwen")
    assert isinstance(qw, QwenClient)
    assert qw.model_name == "qwen-max"


def test_deepseek_default_model():
    """DeepSeek defaults to deepseek-v4-flash when model_name is omitted."""
    os.environ["AI_API_KEY"] = "eval-key"
    client = get_client("", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-v4-flash"


def test_qwen_default_model():
    """When switching to qwen without specifying model, default to qwen-plus."""
    os.environ["AI_API_KEY"] = "eval-key"
    qw_empty = get_client("", "qwen")
    assert isinstance(qw_empty, QwenClient)
    assert qw_empty.model_name == "qwen-plus"


def test_unsupported_model_provider_combination_rejected():
    """Evaluation mode rejects mismatched model/provider combinations and never silently substitutes."""
    os.environ["AI_API_KEY"] = "eval-key"
    with pytest.raises(ValueError, match="Invalid model 'deepseek-v4-flash' for provider 'qwen'"):
        get_client("deepseek-v4-flash", "qwen")

    with pytest.raises(ValueError, match="Invalid model 'qwen-plus' for provider 'deepseek'"):
        get_client("qwen-plus", "deepseek")


def test_locked_evaluation_model_rejects_arbitrary_override(monkeypatch):
    """Prescribed / locked evaluation model cannot be overridden by arbitrary model."""
    monkeypatch.setenv("AI_API_KEY", "eval-key")
    monkeypatch.setenv("CODY_LOCKED_MODEL", "deepseek-v4-flash")
    # Matching model is accepted
    client = get_client("deepseek-v4-flash", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-v4-flash"

    # Conflicting arbitrary model is rejected
    with pytest.raises(ValueError, match="evaluation model is locked"):
        get_client("deepseek-custom-model", "deepseek")


def test_cody_provider_env_switches_default():
    """CODY_PROVIDER=qwen switches provider and defaults model to qwen-plus when model is omitted."""
    os.environ["AI_API_KEY"] = "eval-key"
    os.environ["CODY_PROVIDER"] = "qwen"
    client = get_client("", "deepseek")
    assert isinstance(client, QwenClient)
    assert client.model_name == "qwen-plus"


def test_cody_model_env_overrides_default():
    """CODY_MODEL explicitly overrides default for both providers with valid family models."""
    os.environ["AI_API_KEY"] = "eval-key"
    os.environ["CODY_MODEL"] = "deepseek-coder"
    client = get_client("", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-coder"

    os.environ["CODY_PROVIDER"] = "qwen"
    os.environ["CODY_MODEL"] = "qwen-turbo"
    client2 = get_client("", "deepseek")
    assert isinstance(client2, QwenClient)
    assert client2.model_name == "qwen-turbo"


def test_missing_required_api_key_configuration(monkeypatch):
    """Missing required API credentials raises clear ValueError."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.setenv("MOCK_MODEL", "false")
    with pytest.raises(ValueError, match="No API key found"):
        get_client("deepseek-v4-flash", "deepseek")


@pytest.mark.parametrize("bad_provider", ["openai", "anthropic", "gemini", "llama"])
def test_unsupported_providers_rejected(bad_provider):
    """Evaluation rejects all providers outside deepseek and qwen."""
    with pytest.raises(ValueError, match="Unknown provider"):
        get_client("model", bad_provider)


def test_unsupported_provider_rejected_even_in_mock_mode():
    """Mock mode cannot bypass approved provider validation."""
    os.environ["MOCK_MODEL"] = "true"
    os.environ["CODY_PROVIDER"] = "openai"
    with pytest.raises(ValueError, match="Unknown provider"):
        get_client("model", "openai")


def test_provider_precedence_matrix(monkeypatch):
    """CLI overrides environment, which overrides config file defaults."""
    captured = {}
    def mock_get_client(model_name, provider):
        captured["model_name"] = model_name
        captured["provider"] = provider
        return object()

    monkeypatch.setattr(main_module, "get_client", mock_get_client)
    monkeypatch.setattr(main_module, "Orchestrator", lambda **kwargs: type("M", (), {"run": lambda self, state: state})())

    # Case 1: Config defaults when no CLI and no env
    monkeypatch.delenv("CODY_PROVIDER", raising=False)
    monkeypatch.delenv("CODY_MODEL", raising=False)
    monkeypatch.setattr(main_module, "_resolve_task", lambda args: TaskSpec(title="t", description="t", source="cli"))
    fake_cfg = SimpleNamespace(
        model=SimpleNamespace(provider="deepseek", name="deepseek-v4-flash"),
        agent=SimpleNamespace(timeout_seconds=30, test_command="make test", max_iterations=15, max_recovery_attempts=3)
    )
    monkeypatch.setattr(main_module, "load_config", lambda: fake_cfg)

    monkeypatch.setattr(sys, "argv", ["cody"])
    main_module.main()
    assert captured["provider"] == "deepseek"
    assert captured["model_name"] == "deepseek-v4-flash"

    # Case 2: Env overrides config
    monkeypatch.setenv("CODY_PROVIDER", "qwen")
    monkeypatch.setenv("CODY_MODEL", "qwen-turbo")
    monkeypatch.setattr(sys, "argv", ["cody"])
    main_module.main()
    assert captured["provider"] == "qwen"
    assert captured["model_name"] == "qwen-turbo"

    # Case 3: CLI overrides both Env and Config
    monkeypatch.setattr(sys, "argv", ["cody", "--provider", "deepseek", "--model", "deepseek-chat"])
    main_module.main()
    assert captured["provider"] == "deepseek"
    assert captured["model_name"] == "deepseek-chat"


@pytest.mark.skipif(not os.environ.get("REAL_API_TEST"), reason="Opt-in real provider test requiring credentials")
def test_real_provider_smoke_test(monkeypatch):
    """Only executed when explicitly requested with REAL_API_TEST=1 and real keys.

    Auto-loads credentials from .env when provider-specific env vars were wiped
    by the autouse fixture (so REAL_API_TEST=1 alone is sufficient).
    Precedence: AI_API_KEY > DEEPSEEK_API_KEY / QWEN_API_KEY > .env file values.
    """


    env_file = pathlib.Path(__file__).parent.parent / ".env"
    env_values: dict = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
            if m:
                env_values[m.group(1)] = m.group(2).strip()

    # Restore only keys wiped by the autouse fixture; never clobber already-set vars
    for key in ("AI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY"):
        if not os.environ.get(key) and env_values.get(key):
            monkeypatch.setenv(key, env_values[key])

    for provider in ["deepseek", "qwen"]:
        client = get_client("", provider=provider)
        response = client.generate("Respond with json containing action finish and result pong.")
        assert isinstance(response, dict), f"{provider}: expected dict, got {type(response)}"
        assert "action" in response, f"{provider}: missing 'action' key: {response}"


# ---------------------------------------------------------------------------
# TASK 2 — Provider inference and resolution
# ---------------------------------------------------------------------------

def test_infer_provider_from_deepseek_model():
    """No CODY_PROVIDER set; deepseek-* model name infers deepseek provider."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_MODEL"] = "deepseek-chat"
    # Pass empty provider arg to exercise inference path
    client = get_client("", "deepseek")  # arg provider is the config default
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-chat"


def test_infer_provider_from_qwen_model():
    """No CODY_PROVIDER set; qwen-* model name infers qwen provider."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_MODEL"] = "qwen-turbo"
    client = get_client("", "deepseek")  # arg provider is the config default
    assert isinstance(client, QwenClient)
    assert client.model_name == "qwen-turbo"


def test_explicit_deepseek_provider_and_model():
    """Explicit CODY_PROVIDER=deepseek with matching model."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "deepseek"
    os.environ["CODY_MODEL"] = "deepseek-v4-flash"
    client = get_client("", "")
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-v4-flash"


def test_explicit_qwen_provider_and_model():
    """Explicit CODY_PROVIDER=qwen with matching model."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "qwen"
    os.environ["CODY_MODEL"] = "qwen-max"
    client = get_client("", "")
    assert isinstance(client, QwenClient)
    assert client.model_name == "qwen-max"


def test_explicit_provider_takes_precedence_over_inference():
    """CODY_PROVIDER=deepseek wins even when CODY_MODEL looks like qwen."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "deepseek"
    os.environ["CODY_MODEL"] = "qwen-turbo"  # would infer qwen without explicit provider
    with pytest.raises(ValueError, match="Invalid model 'qwen-turbo' for provider 'deepseek'"):
        get_client("", "")


def test_provider_model_conflict_raises_clear_error():
    """Explicit provider + mismatched explicit model produces a descriptive error."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "qwen"
    os.environ["CODY_MODEL"] = "deepseek-v4-flash"
    with pytest.raises(ValueError, match="Invalid model 'deepseek-v4-flash' for provider 'qwen'"):
        get_client("", "")


def test_mock_mode_still_works_with_inference_path():
    """Mock mode works even when CODY_MODEL would infer a real provider."""
    os.environ["MOCK_MODEL"] = "true"
    os.environ["CODY_MODEL"] = "qwen-max"
    client = get_client("", "deepseek")
    assert isinstance(client, MockClient)


def test_existing_defaults_unchanged():
    """When neither CODY_PROVIDER nor CODY_MODEL is set, defaults to deepseek-v4-flash."""
    os.environ["AI_API_KEY"] = "key"
    client = get_client("", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.model_name == "deepseek-v4-flash"


# ---------------------------------------------------------------------------
# TASK 1 — Configurable base URLs
# ---------------------------------------------------------------------------

def test_qwen_base_url_override(monkeypatch):
    """QWEN_BASE_URL is read at call time and replaces the DashScope default."""
    monkeypatch.setenv("QWEN_BASE_URL", "https://custom-qwen.example.com/v1")
    client = QwenClient(api_key="key", model_name="qwen-plus")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"action": "finish", "result": "ok"}'}}]
    }
    captured_url = {}
    def capturing_post(url, **kwargs):
        captured_url["url"] = url
        return mock_response
    monkeypatch.setattr(requests, "post", capturing_post)
    client.generate("hello")
    assert captured_url["url"] == "https://custom-qwen.example.com/v1/chat/completions"


def test_qwen_base_url_default_is_dashscope(monkeypatch):
    """Without QWEN_BASE_URL set, DashScope URL is used."""
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)
    client = QwenClient(api_key="key", model_name="qwen-plus")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"action": "finish", "result": "ok"}'}}]
    }
    captured_url = {}
    def capturing_post(url, **kwargs):
        captured_url["url"] = url
        return mock_response
    monkeypatch.setattr(requests, "post", capturing_post)
    client.generate("hello")
    assert "dashscope.aliyuncs.com" in captured_url["url"]


def test_deepseek_base_url_override(monkeypatch):
    """DEEPSEEK_BASE_URL is read at call time and replaces the api.deepseek.com default."""
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom-ds.example.com")
    client = DeepSeekClient(api_key="key", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"action": "finish", "result": "ok"}'}}]
    }
    captured_url = {}
    def capturing_post(url, **kwargs):
        captured_url["url"] = url
        return mock_response
    monkeypatch.setattr(requests, "post", capturing_post)
    client.generate("hello")
    assert captured_url["url"] == "https://custom-ds.example.com/chat/completions"


def test_deepseek_base_url_default(monkeypatch):
    """Without DEEPSEEK_BASE_URL, api.deepseek.com is used."""
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    client = DeepSeekClient(api_key="key", model_name="deepseek-v4-flash")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"action": "finish", "result": "ok"}'}}]
    }
    captured_url = {}
    def capturing_post(url, **kwargs):
        captured_url["url"] = url
        return mock_response
    monkeypatch.setattr(requests, "post", capturing_post)
    client.generate("hello")
    assert "api.deepseek.com" in captured_url["url"]
