import json
import re
from typing import Dict, Any, Optional, List

def validate_action(action: Any, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not isinstance(action, dict):
        return {
            "action": "error",
            "error_type": "invalid_model_action",
            "message": "Model action must be a JSON object"
        }

    action_type = action.get("action")
    if action_type == "tool_call":
        tool = action.get("tool")
        args = action.get("arguments")
        if not isinstance(tool, str) or not tool.strip() or not isinstance(args, dict):
            return {
                "action": "error",
                "error_type": "invalid_model_action",
                "message": "tool_call requires non-empty string 'tool' and dict 'arguments'"
            }
        
        if tools is not None:
            tool_schema = next((t for t in tools if t.get("name") == tool), None)
            if not tool_schema:
                return {
                    "action": "error",
                    "error_type": "unknown_tool",
                    "message": f"Tool '{tool}' is not available."
                }
            
            props = tool_schema.get("parameters", {}).get("properties", {})
            required = tool_schema.get("parameters", {}).get("required", [])
            for req in required:
                if req not in args:
                    return {
                        "action": "error",
                        "error_type": "missing_argument",
                        "message": f"Tool '{tool}' missing required argument: '{req}'"
                    }
            for arg_name, arg_val in args.items():
                if arg_name not in props:
                    return {
                        "action": "error",
                        "error_type": "invalid_argument",
                        "message": f"Tool '{tool}' received unknown argument: '{arg_name}'"
                    }
                expected_type = props[arg_name].get("type")
                if expected_type:
                    valid = True
                    if expected_type == "string" and not isinstance(arg_val, str):
                        valid = False
                    elif expected_type == "integer" and not isinstance(arg_val, int):
                        valid = False
                    elif expected_type == "number" and not isinstance(arg_val, (int, float)):
                        valid = False
                    elif expected_type == "boolean" and not isinstance(arg_val, bool):
                        valid = False
                    elif expected_type == "array" and not isinstance(arg_val, list):
                        valid = False
                    elif expected_type == "object" and not isinstance(arg_val, dict):
                        valid = False
                    if not valid:
                        return {
                            "action": "error",
                            "error_type": "invalid_argument_type",
                            "message": f"Argument '{arg_name}' must be {expected_type}"
                        }
                
    elif action_type == "finish":
        if "result" not in action or not isinstance(action.get("result"), str):
            return {
                "action": "error",
                "error_type": "invalid_model_action",
                "message": "finish action requires a 'result' string"
            }
    elif action_type == "error":
        if not isinstance(action.get("error_type"), str) or not isinstance(action.get("message"), str):
            return {
                "action": "error",
                "error_type": "invalid_model_action",
                "message": "error requires string 'error_type' and 'message'"
            }
    else:
        return {
            "action": "error",
            "error_type": "invalid_model_action",
            "message": f"Unknown action: {action_type}"
        }
    return action


def extract_json(text: str) -> Dict[str, Any]:
    if not text or not text.strip():
        return {
            "action": "error",
            "error_type": "empty_response",
            "message": "Model returned an empty response."
        }

    json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if len(json_blocks) > 1:
        return {
            "action": "error",
            "error_type": "multiple_actions",
            "message": "Model returned multiple JSON blocks. Only one action is allowed."
        }
    elif len(json_blocks) == 1:
        try:
            parsed = json.loads(json_blocks[0])
            if not isinstance(parsed, dict):
                 return {
                    "action": "error",
                    "error_type": "invalid_model_action",
                    "message": "Model action must be a JSON object"
                }
            return parsed
        except json.JSONDecodeError:
            pass

    start_idx = text.find('{')
    if start_idx != -1:
        for i in range(len(text) - 1, start_idx - 1, -1):
            if text[i] == '}':
                try:
                    parsed = json.loads(text[start_idx:i+1])
                    if not isinstance(parsed, dict):
                        return {
                            "action": "error",
                            "error_type": "invalid_model_action",
                            "message": "Model action must be a JSON object"
                        }
                    remainder = text[i+1:].strip()
                    if remainder.startswith('{'):
                         return {
                            "action": "error",
                            "error_type": "multiple_actions",
                            "message": "Model returned multiple JSON blocks. Only one action is allowed."
                        }
                    return parsed
                except json.JSONDecodeError:
                    continue

    return {
        "action": "error",
        "error_type": "invalid_model_response",
        "message": "Failed to extract valid JSON action from model response.",
        "raw_response": text
    }
