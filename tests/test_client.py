import json
import pytest
from unittest.mock import patch, MagicMock
from src.harness.model.providers.deepseek import DeepSeekClient
from src.harness.model.providers.qwen import QwenClient
from src.harness.model.boundary import validate_action, extract_json

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
    client = DeepSeekClient(api_key="fake", model_name="deepseek-chat")
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
    client = DeepSeekClient(api_key="fake", model_name="deepseek-chat")
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
    import requests
    client = DeepSeekClient(api_key="fake", model_name="deepseek-chat")
    with patch('requests.post', side_effect=requests.exceptions.Timeout):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_timeout"

def test_deepseek_client_provider_error():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-chat")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"

def test_deepseek_client_malformed_response():
    client = DeepSeekClient(api_key="fake", model_name="deepseek-chat")
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
    import requests
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

import os
from src.harness.model.client import get_client, validate_model_name
from src.harness.model.providers.mock import MockClient


@pytest.fixture(autouse=True)
def clean_env_for_client_tests():
    """Ensure no leaked env vars between tests."""
    keys = ["AI_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY", "CODY_PROVIDER", "CODY_MODEL", "MOCK_MODEL"]
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
    client = get_client("deepseek-chat", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "eval-key"


def test_get_client_ai_api_key_takes_priority():
    """AI_API_KEY takes priority over provider-specific keys."""
    os.environ["AI_API_KEY"] = "eval-key"
    os.environ["DEEPSEEK_API_KEY"] = "ds-key"
    client = get_client("deepseek-chat", "deepseek")
    assert client.api_key == "eval-key"


def test_get_client_provider_key_fallback():
    """Provider-specific key works when AI_API_KEY is absent."""
    os.environ["DEEPSEEK_API_KEY"] = "ds-key"
    client = get_client("deepseek-chat", "deepseek")
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
        get_client("deepseek-chat", "deepseek")


def test_validate_model_name_rejects_placeholder():
    """Placeholder model names must fail fast."""
    with pytest.raises(ValueError, match="placeholder"):
        validate_model_name("<CONFIRMED_DEEPSEEK_MODEL>")


def test_validate_model_name_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_model_name("")


def test_validate_model_name_accepts_real():
    assert validate_model_name("deepseek-chat") == "deepseek-chat"


def test_get_client_env_overrides(monkeypatch):
    """CODY_PROVIDER and CODY_MODEL env vars override arguments."""
    os.environ["AI_API_KEY"] = "key"
    os.environ["CODY_PROVIDER"] = "mock"
    client = get_client("deepseek-chat", "deepseek")
    assert isinstance(client, MockClient)


def test_credentials_never_logged(capsys):
    """API key value must never appear in stdout/stderr."""
    os.environ["AI_API_KEY"] = "super-secret-key-12345"
    client = get_client("deepseek-chat", "deepseek")
    output = capsys.readouterr()
    assert "super-secret-key-12345" not in output.out
    assert "super-secret-key-12345" not in output.err


def test_approved_providers_accepted_with_ai_api_key():
    """Both DeepSeek and Qwen are approved evaluation providers."""
    os.environ["AI_API_KEY"] = "eval-key"
    ds = get_client("deepseek-chat", "deepseek")
    assert isinstance(ds, DeepSeekClient)

    qw = get_client("qwen-max", "qwen")
    assert isinstance(qw, QwenClient)


def test_qwen_default_model_fallback():
    """When switching to qwen without specifying model, default to qwen-plus."""
    os.environ["AI_API_KEY"] = "eval-key"
    qw = get_client("deepseek-chat", "qwen")
    assert isinstance(qw, QwenClient)
    assert qw.model_name == "qwen-plus"


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

