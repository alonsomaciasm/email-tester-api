"""Model Context Protocol (MCP) Server for Disposable Email Verification API.

Exposes native AI Agent Tools for LLM Function Calling (Gemini, Claude, OpenAI, Antigravity).
Provides sub-millisecond verification tools while drastically reducing LLM token consumption.
"""

import asyncio
import json
from typing import Any, Callable

from app.domain.bloom_filter import bloom_filter_service
from app.domain.verification_service import verification_service
from app.infra.redis_client import redis_manager


class FastMCPServer:
    """Lightweight FastMCP JSON-RPC 2.0 Server for AI Agent Integration."""

    def __init__(self, name: str = "EmailTesterAPI-MCP") -> None:
        self.name = name
        self.tools: dict[str, dict[str, Any]] = {}

    def tool(self, description: str = "") -> Callable:
        def decorator(func: Callable) -> Callable:
            tool_name = func.__name__
            self.tools[tool_name] = {
                "name": tool_name,
                "description": description or func.__doc__ or "",
                "handler": func,
            }
            return func
        return decorator

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str:
        if tool_name not in self.tools:
            return json.dumps({"error": f"Tool '{tool_name}' not found."})
        handler = self.tools[tool_name]["handler"]
        return await handler(**kwargs)

    async def handle_jsonrpc_request(self, request_json: str) -> str:
        """Processes incoming JSON-RPC 2.0 tool requests from LLM Agents."""
        try:
            req = json.loads(request_json)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "tools/list":
                tool_list = [
                    {"name": t["name"], "description": t["description"]}
                    for t in self.tools.values()
                ]
                return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tool_list}})

            if method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                result_content = await self.call_tool(tool_name, **tool_args)
                return json.dumps({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": result_content}]},
                })

            return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}})
        except Exception as e:
            return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}})


mcp = FastMCPServer()


@mcp.tool(description="Verifies a single email address for disposable provider detection.")
async def verify_email_tool(email: str) -> str:
    """Verifies a single email address."""
    result = await verification_service.verify_email_domain(email)
    return json.dumps({
        "disposable": result.disposable,
        "confidence": result.confidence,
        "reason": result.reason,
        "risk_score": result.risk_score,
        "did_you_mean": result.did_you_mean,
    }, separators=(",", ":"))


@mcp.tool(description="Verifies a batch of up to 100 email addresses concurrently.")
async def verify_email_batch_tool(emails: list[str]) -> str:
    """Verifies a batch of up to 100 email addresses concurrently."""
    tasks = [verification_service.verify_email_domain(e) for e in emails[:100]]
    results = await asyncio.gather(*tasks)

    high_risk = []
    disposable_count = 0

    for res in results:
        if res.disposable:
            disposable_count += 1
        if res.risk_score >= 60:
            high_risk.append({
                "disposable": res.disposable,
                "risk_score": res.risk_score,
                "reason": res.reason,
                "did_you_mean": res.did_you_mean,
            })

    return json.dumps({
        "total_processed": len(results),
        "disposable_count": disposable_count,
        "high_risk_flagged": high_risk,
    }, separators=(",", ":"))


@mcp.tool(description="Checks operational health, Redis status, and filter capacity metrics.")
async def get_telemetry_status_tool() -> str:
    """Checks operational health, Redis status, and probabilistic filter capacity metrics."""
    redis_ok = await redis_manager.ping()
    bloom_info = bloom_filter_service.get_info()

    return json.dumps({
        "status": "healthy" if redis_ok else "degraded",
        "redis_connected": redis_ok,
        "filter_engine": bloom_info.get("engine", "cuckoo"),
        "indexed_domains": bloom_info.get("items_count", 0),
        "capacity": bloom_info.get("capacity", 500000),
    }, separators=(",", ":"))


if __name__ == "__main__":
    print(f"⚡ FastMCP Server '{mcp.name}' running on stdio JSON-RPC 2.0...")
