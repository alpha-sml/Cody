import requests
from typing import List, Dict, Any, Optional
from ..base import BaseModelClient
from ..boundary import extract_json, validate_action

class GoogleClient(BaseModelClient):
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": "SYSTEM: " + system_prompt}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {"contents": contents}

        if tools:
            function_declarations = []
            for tool in tools:
                function_declarations.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}})
                })
            payload["tools"] = [{"functionDeclarations": function_declarations}]

        try:
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
            if response.status_code == 200:
                data = response.json()
                try:
                    candidates = data.get('candidates', [])
                    if not candidates:
                        return {"action": "error", "error_type": "model_api_error", "message": "No candidates in API response"}

                    content = candidates[0].get('content', {})
                    if not content:
                        return {"action": "error", "error_type": "model_api_error", "message": "No content in API response"}

                    parts = content.get('parts', [])
                    if not parts:
                        return {"action": "error", "error_type": "model_api_error", "message": "No parts in API response"}

                    for part in parts:
                        if 'functionCall' in part:
                            fc = part['functionCall']
                            if not isinstance(fc, dict):
                                return {"action": "error", "error_type": "model_api_error", "message": "Malformed functionCall structure"}

                            args = fc.get("args")
                            if args is None:
                                args = {}

                            return validate_action({
                                "action": "tool_call",
                                "tool": fc.get("name"),
                                "arguments": args
                            }, tools=tools)

                    if 'text' in parts[0] and isinstance(parts[0]['text'], str):
                        text = parts[0]['text']
                        parsed = extract_json(text)
                        return validate_action(parsed, tools=tools)

                    return {"action": "error", "error_type": "model_api_error", "message": "No valid functionCall or text found"}
                except (KeyError, IndexError, TypeError) as e:
                    return {"action": "error", "error_type": "model_api_error", "message": f"Invalid response structure from API: {str(e)}"}
            else:
                return {"action": "error", "error_type": "model_api_error", "message": f"API error: {response.status_code} {response.text}"}
        except requests.Timeout:
            return {"action": "error", "error_type": "model_api_timeout", "message": "API request timed out"}
        except Exception as e:
            return {"action": "error", "error_type": "model_api_error", "message": f"API exception: {str(e)}"}
