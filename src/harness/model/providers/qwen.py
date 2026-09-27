import os
import requests
from typing import List, Dict, Any, Optional
from ..base import BaseModelClient
from ..boundary import extract_json, validate_action

_QWEN_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

class QwenClient(BaseModelClient):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        base_url = os.environ.get("QWEN_BASE_URL", _QWEN_DEFAULT_BASE_URL).rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
        }

        if tools:
            openai_tools = []
            for t in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}})
                    }
                })
            payload["tools"] = openai_tools

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                try:
                    choices = data.get("choices", [])
                    if not choices:
                        return {"action": "error", "error_type": "model_api_error", "message": "No choices in API response"}

                    message = choices[0].get("message", {})
                    if not message:
                        return {"action": "error", "error_type": "model_api_error", "message": "No message in API response"}

                    tool_calls = message.get("tool_calls")
                    if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                        tc = tool_calls[0]
                        if tc.get("type") == "function":
                            func = tc.get("function", {})
                            import json
                            try:
                                args = json.loads(func.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                args = {}
                            return validate_action({
                                "action": "tool_call",
                                "tool": func.get("name"),
                                "arguments": args
                            }, tools=tools)

                    text = message.get("content")
                    if text and isinstance(text, str):
                        parsed = extract_json(text)
                        return validate_action(parsed, tools=tools)

                    return {"action": "error", "error_type": "model_api_error", "message": "No valid tool_calls or content found"}
                except Exception as e:
                    return {"action": "error", "error_type": "model_api_error", "message": f"Invalid response structure: {str(e)}"}
            else:
                return {"action": "error", "error_type": "model_api_error", "message": f"API error: {response.status_code} {response.text}"}
        except requests.Timeout:
            return {"action": "error", "error_type": "model_api_timeout", "message": "API request timed out"}
        except Exception as e:
            return {"action": "error", "error_type": "model_api_error", "message": f"API exception: {str(e)}"}
