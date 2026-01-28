from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from typing import Any


def _serialize_mcp_result(result: Any) -> Any:
    """Convert MCP result (which may contain TextContent/Image) to JSON-serializable format."""
    if result is None:
        return None
    if isinstance(result, dict):
        return {k: _serialize_mcp_result(v) for k, v in result.items()}
    if isinstance(result, list):
        return [_serialize_mcp_result(item) for item in result]
    # Handle MCP TextContent and Image objects
    if hasattr(result, "text"):  # TextContent
        return {"type": "text", "content": result.text}
    if hasattr(result, "data") and hasattr(result, "format"):  # Image
        import base64
        return {
            "type": "image",
            "format": result.format,
            "data": base64.b64encode(result.data).decode() if isinstance(result.data, bytes) else result.data,
        }
    # Handle bytes
    if isinstance(result, bytes):
        import base64
        return {"type": "bytes", "data": base64.b64encode(result).decode()}
    # Primitive types
    if isinstance(result, (str, int, float, bool)):
        return result
    # Fallback: convert to string
    return str(result)


def create_debug_routes(mcp: FastMCP) -> list[Route]:
    """
    Create debug routes for testing tools via HTTP.
    Useful for local dev or checking if tools are registered.
    """
    
    async def list_tools_handler(request: Request) -> JSONResponse:
        """List all registered tools."""
        tools = await mcp.list_tools()
        data = [
            {
                "name": t.name, 
                "description": t.description or ""
            } for t in tools
        ]
        return JSONResponse({"tools": data})

    async def call_tool_handler(request: Request) -> JSONResponse:
        """Call a tool by name with input parameters."""
        try:
            body = await request.json()
            tool_name = body.get("name")
            tool_input = body.get("input", {})
            
            if not tool_name:
                return JSONResponse({"error": "Missing 'name' field"}, status_code=400)
            
            # Call the tool via MCP
            # FastMCP.call_tool returns either:
            # - Sequence[ContentBlock] (list of content blocks)
            # - dict[str, Any] (direct dict result)
            result = await mcp.call_tool(tool_name, tool_input)
            
            # Handle ContentBlock sequence (extract text/images)
            if isinstance(result, (list, tuple)):
                text_parts = []
                image_parts = []
                
                for block in result:
                    # Check if it's a TextContent object (Pydantic model)
                    if hasattr(block, "text") and hasattr(block, "type"):
                        # Direct TextContent object
                        text_parts.append(block.text)
                    # Check if it's an Image object
                    elif hasattr(block, "data") and hasattr(block, "format"):
                        import base64
                        image_parts.append({
                            "type": "image",
                            "format": block.format,
                            "data": base64.b64encode(block.data).decode() if isinstance(block.data, bytes) else block.data,
                        })
                    # Handle string (might be JSON or text)
                    elif isinstance(block, str):
                        text_parts.append(block)
                    # Handle dict (direct result)
                    elif isinstance(block, dict):
                        # This shouldn't happen in a list, but handle it
                        return JSONResponse(block)
                    else:
                        # Unknown type - try to extract text from string representation
                        block_str = str(block)
                        # If it's a TextContent string representation like "TextContent(type='text', text='...')"
                        # Try to extract the text field
                        import re
                        match = re.search(r"text=['\"](.*?)['\"]", block_str, re.DOTALL)
                        if match:
                            text_parts.append(match.group(1))
                        else:
                            text_parts.append(block_str)
                
                # If we have text content, try to parse as JSON
                if text_parts:
                    combined_text = "".join(text_parts)
                    # Try to parse as JSON if it looks like JSON
                    if combined_text.strip().startswith("{"):
                        try:
                            import json
                            parsed = json.loads(combined_text)
                            # If we also have images, include them
                            if image_parts:
                                parsed["images"] = image_parts
                            return JSONResponse(parsed)
                        except json.JSONDecodeError:
                            # Not valid JSON, return as text
                            return JSONResponse({
                                "type": "text",
                                "content": combined_text,
                                "images": image_parts if image_parts else None
                            })
                    else:
                        # Plain text
                        return JSONResponse({
                            "type": "text",
                            "content": combined_text,
                            "images": image_parts if image_parts else None
                        })
                
                # Only images, no text
                if image_parts:
                    return JSONResponse({"images": image_parts})
                
                # Fallback
                return JSONResponse({"content": [str(b) for b in result]})
            
            # Handle dict result (our tools return ok_response/error_response dicts)
            serialized = _serialize_mcp_result(result)
            return JSONResponse(serialized)
        except Exception as e:
            import traceback
            return JSONResponse({"error": str(e), "traceback": traceback.format_exc()}, status_code=500)

    async def health_check(request: Request) -> JSONResponse:
        """Health check endpoint."""
        return JSONResponse({"status": "ok", "server": "thordata-mcp", "ready": True})

    return [
        Route("/debug/tools", list_tools_handler, methods=["GET"]),
        Route("/debug/tools/list", list_tools_handler, methods=["GET", "POST"]),
        Route("/debug/tools/call", call_tool_handler, methods=["POST"]),
        Route("/debug/healthz", health_check, methods=["GET"]),
        Route("/health", health_check, methods=["GET"]),
    ]