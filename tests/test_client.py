import json
import pytest
from unittest.mock import patch, MagicMock
from src.harness.model.providers.google import GoogleClient
from src.harness.model.boundary import validate_action, extract_json

def test_google_client_function_call_parsing():
    client = GoogleClient(api_key="fake", model_name="gemini-1.5-pro")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "file_write",
                                "args": {
                                    "path": "test.py",
                                    "content": "print('hello')"
                                }
                            }
                        }
                    ]
                }
            }
        ]
    }

    # We must provide tool schemas for validation to succeed without error
    tools = [{
        "name": "file_write",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }]

    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt", tools=tools)

    assert action == {
        "action": "tool_call",
        "tool": "file_write",
        "arguments": {
            "path": "test.py",
            "content": "print('hello')"
        }
    }

def test_google_client_json_text_parsing():
    client = GoogleClient(api_key="fake", model_name="gemini-1.5-pro")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '```json\n{"action": "finish", "result": "done"}\n```'
                        }
                    ]
                }
            }
        ]
    }

    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt")

    assert action == {
        "action": "finish",
        "result": "done"
    }

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

def test_google_client_timeout():
    import requests
    client = GoogleClient(api_key="fake", model_name="gemini")
    with patch('requests.post', side_effect=requests.exceptions.Timeout):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_timeout"

def test_google_client_provider_error():
    client = GoogleClient(api_key="fake", model_name="gemini")
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test")
    assert action["action"] == "error"
    assert action["error_type"] == "model_api_error"

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
