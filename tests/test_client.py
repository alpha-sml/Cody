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
from src.harness.model.client import get_client
from src.harness.model.providers.mock import MockClient

def test_get_client_default():
    # Should default to deepseek
    os.environ["AI_API_KEY"] = "fake"
    client = get_client("model_name")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "fake"
    os.environ.pop("AI_API_KEY", None)

def test_get_client_explicit_deepseek():
    os.environ["DEEPSEEK_API_KEY"] = "ds_key"
    client = get_client("model_name", "deepseek")
    assert isinstance(client, DeepSeekClient)
    assert client.api_key == "ds_key"
    os.environ.pop("DEEPSEEK_API_KEY", None)

def test_get_client_explicit_qwen():
    os.environ["QWEN_API_KEY"] = "qw_key"
    client = get_client("model_name", "qwen")
    assert isinstance(client, QwenClient)
    assert client.api_key == "qw_key"
    os.environ.pop("QWEN_API_KEY", None)

def test_get_client_explicit_mock():
    client = get_client("model_name", "mock")
    assert isinstance(client, MockClient)

def test_get_client_case_insensitive():
    os.environ["QWEN_API_KEY"] = "qw_key"
    client = get_client("model_name", " QWEN ")
    assert isinstance(client, QwenClient)
    assert client.api_key == "qw_key"
    os.environ.pop("QWEN_API_KEY", None)

def test_get_client_unsupported():
    # Should reject unsupported provider even when no API key exists
    with pytest.raises(ValueError, match="Unknown provider"):
        get_client("model_name", "unsupported")
