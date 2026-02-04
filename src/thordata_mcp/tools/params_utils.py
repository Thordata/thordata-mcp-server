"""Common parameter normalization utilities for thordata MCP tools."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from thordata_mcp.utils import error_response


def normalize_params(params: Any, tool_name: str, action: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalize params to dictionary with clear error messages.
    
    This function handles the common case where Cursor might pass params as a string
    instead of a dictionary object, and provides helpful error messages.
    
    Args:
        params: The params value passed to the tool
        tool_name: Name of the tool for error reporting
        action: Optional action name for error reporting
        
    Returns:
        Normalized params dictionary
        
    Raises:
        ValueError: If params cannot be normalized to a dictionary
    """
    if params is None:
        return {}
    
    if isinstance(params, dict):
        return params
    
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            if not isinstance(parsed, dict):
                raise ValueError("Parsed JSON is not a dictionary")
            return parsed
        except json.JSONDecodeError as e:
            error_msg = (
                f"Invalid JSON in params: {e}. "
                f"Params should be a dictionary object, not a string. "
                f"Example: params={{'url': 'https://example.com'}}. "
                f"Received: {params[:100]}{'...' if len(params) > 100 else ''}"
            )
            raise ValueError(error_msg)
    
    # Handle other types (list, number, etc.)
    error_msg = (
        f"params must be a dictionary object, not {type(params).__name__}. "
        f"Example: params={{'url': 'https://example.com'}}. "
        f"Received: {str(params)[:100]}{'...' if len(str(params)) > 100 else ''}"
    )
    raise ValueError(error_msg)


def create_params_error(tool_name: str, action: str, params: Any, error_message: str) -> Dict[str, Any]:
    """
    Create a standardized error response for parameter validation errors.
    
    Args:
        tool_name: Name of the tool
        action: Action being performed
        params: The invalid params value
        error_message: Detailed error message
        
    Returns:
        Error response dictionary
    """
    return error_response(
        tool=tool_name,
        input={"action": action, "params": params},
        error_type="validation_error",
        code="E4001",
        message=error_message,
    )


def create_json_error(tool_name: str, action: str, params: str, error_detail: str) -> Dict[str, Any]:
    """
    Create a standardized error response for JSON parsing errors.
    
    Args:
        tool_name: Name of the tool
        action: Action being performed
        params: The invalid JSON string
        error_detail: JSON parsing error detail
        
    Returns:
        Error response dictionary
    """
    error_message = (
        f"Invalid JSON in params: {error_detail}. "
        f"Use dictionary format: params={{'url': 'https://example.com'}} "
        f"or valid JSON string: params='{{\"url\":\"https://example.com\"}}'. "
        f"Received: {params[:100]}{'...' if len(params) > 100 else ''}"
    )
    
    return error_response(
        tool=tool_name,
        input={"action": action, "params": params},
        error_type="json_error",
        code="E4002",
        message=error_message,
    )