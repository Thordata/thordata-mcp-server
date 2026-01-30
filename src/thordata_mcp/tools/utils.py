"""Shared utilities for tool discovery and management."""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil
from typing import Any

from thordata.tools import ToolRequest


def iter_tool_request_types(max_depth: int = 6) -> list[type[ToolRequest]]:
    """Discover all ToolRequest dataclasses in thordata.tools.
    
    This function recursively walks through the thordata.tools module to find
    all ToolRequest subclasses. It ensures all submodules are imported so
    ToolRequest subclasses are discoverable via introspection.
    
    Args:
        max_depth: Maximum recursion depth (default: 6)
        
    Returns:
        List of ToolRequest subclasses, sorted by module and qualname
    """
    import thordata.tools as tools_module

    # Ensure all thordata.tools submodules are imported so ToolRequest subclasses
    # are discoverable via introspection. Without this, many tasks won't appear.
    if hasattr(tools_module, "__path__"):
        for mod in pkgutil.walk_packages(tools_module.__path__, tools_module.__name__ + "."):
            try:
                importlib.import_module(mod.name)
            except Exception:
                # Best-effort: some modules may be optional or have extra deps.
                # We ignore import failures to keep server robust.
                pass

    out: list[type[ToolRequest]] = []
    seen: set[int] = set()

    def walk(obj: Any, depth: int = 0) -> None:
        if depth > max_depth:
            return
        for _, member in inspect.getmembers(obj):
            if inspect.isclass(member):
                if member is ToolRequest:
                    continue
                if issubclass(member, ToolRequest) and dataclasses.is_dataclass(member):
                    mid = id(member)
                    if mid in seen:
                        continue
                    seen.add(mid)
                    out.append(member)
                else:
                    walk(member, depth + 1)

    walk(tools_module)
    out.sort(key=lambda t: f"{t.__module__}.{t.__qualname__}")
    return out


def tool_key(t: type[ToolRequest]) -> str:
    """Generate tool key from ToolRequest class.
    
    Args:
        t: ToolRequest subclass
        
    Returns:
        Tool key in format: module.qualname
    """
    return f"{t.__module__}.{t.__qualname__}"


def tool_group_from_key(key: str) -> str:
    """Infer a coarse group from tool_key (based on module name)."""
    # Expected: thordata.tools.<group>.<Namespace>.<Tool>
    # Example: thordata.tools.ecommerce.Amazon.ProductByAsin
    parts = key.split(".")
    try:
        i = parts.index("tools")
    except ValueError:
        return "other"
    if i + 1 < len(parts):
        return parts[i + 1]
    return "other"


def matches_any_prefix_or_exact(value: str, allowlist: list[str]) -> bool:
    """Return True if value equals or startswith any allowlist entry."""
    for item in allowlist:
        it = item.strip()
        if not it:
            continue
        if value == it or value.startswith(it):
            return True
    return False


def tool_schema(t: type[ToolRequest]) -> dict[str, Any]:
    """Generate tool schema from ToolRequest class.

    Args:
        t: ToolRequest subclass

    Returns:
        Dictionary containing tool schema information
    """
    fields: dict[str, Any] = {}
    for name, f in t.__dataclass_fields__.items():  # type: ignore[attr-defined]
        fields[name] = {
            "type": getattr(getattr(f.type, "__name__", None), "lower", lambda: str(f.type))(),
            "default": None if f.default is dataclasses.MISSING else f.default,
        }

    key = tool_key(t)
    spider_name = getattr(t, "SPIDER_NAME", None)

    # Generate a friendly name: prefer SPIDER_NAME, fallback to class name
    name = spider_name or key.split(".")[-1]

    return {
        "name": name,  # Add name field for better UX
        "tool_key": key,  # Use "tool_key" for consistency with API
        "key": key,  # Keep "key" for backward compatibility
        "spider_id": getattr(t, "SPIDER_ID", None),
        "spider_name": spider_name,
        "group": tool_group_from_key(key),
        "fields": fields,
    }
