import json
import pytest
from app.api.mcp_server import get_telemetry_status_tool, mcp, verify_email_batch_tool, verify_email_tool


@pytest.mark.asyncio
async def test_mcp_verify_email_tool_disposable() -> None:
    res_str = await verify_email_tool("user@mailinator.com")
    data = json.loads(res_str)

    assert "disposable" in data
    assert "risk_score" in data
    assert data["disposable"] is True
    assert data["risk_score"] >= 85


@pytest.mark.asyncio
async def test_mcp_verify_email_tool_clean() -> None:
    res_str = await verify_email_tool("user@gmail.com")
    data = json.loads(res_str)

    assert "disposable" in data
    assert data["disposable"] is False
    assert data["risk_score"] == 0


@pytest.mark.asyncio
async def test_mcp_verify_email_batch_tool() -> None:
    emails = ["user1@gmail.com", "user2@mailinator.com", "user3@outlook.com"]
    res_str = await verify_email_batch_tool(emails)
    data = json.loads(res_str)

    assert data["total_processed"] == 3
    assert "disposable_count" in data
    assert "high_risk_flagged" in data


@pytest.mark.asyncio
async def test_mcp_telemetry_status_tool() -> None:
    res_str = await get_telemetry_status_tool()
    data = json.loads(res_str)

    assert "status" in data
    assert "capacity" in data


@pytest.mark.asyncio
async def test_mcp_jsonrpc_protocol() -> None:
    # Test tools/list
    list_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    list_res_str = await mcp.handle_jsonrpc_request(list_req)
    list_data = json.loads(list_res_str)

    assert list_data["id"] == 1
    assert "result" in list_data
    assert len(list_data["result"]["tools"]) == 3

    # Test tools/call
    call_req = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "verify_email_tool", "arguments": {"email": "test@gmail.com"}},
    })
    call_res_str = await mcp.handle_jsonrpc_request(call_req)
    call_data = json.loads(call_res_str)

    assert call_data["id"] == 2
    assert "result" in call_data
    tool_text = call_data["result"]["content"][0]["text"]
    tool_json = json.loads(tool_text)
    assert tool_json["disposable"] is False
