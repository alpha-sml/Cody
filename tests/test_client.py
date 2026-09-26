import json
import pytest
from unittest.mock import patch, MagicMock
from src.harness.model.client import GoogleClient

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
    
    with patch('requests.post', return_value=mock_response):
        action = client.generate("test prompt")
        
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
