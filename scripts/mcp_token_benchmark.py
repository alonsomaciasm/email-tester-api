"""MCP LLM Token Savings Empirical Benchmark Script.

Quantifies LLM Token Footprint reduction when AI Agents query disposable email verification
via native MCP Tools (JSON-RPC minified) vs traditional HTTP Web/API parsing.
Exports results to docs/mcp_token_savings.csv.
"""

import csv
import json
import os
import tiktoken

# Initialize standard OpenAI / LLM tokenizers
enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Returns exact token count for string using cl100k_base tokenizer."""
    return len(enc.encode(text))


# Sample 1: Traditional Verbose HTTP API Response (JSON with full metadata & OpenAPI schemas)
TRADITIONAL_HTTP_SINGLE_RESPONSE = json.dumps({
    "email": "user_491@mailinator.com",
    "domain": "mailinator.com",
    "disposable": True,
    "confidence": "medium",
    "reason": "heuristic",
    "risk_score": 85,
    "mx_records": ["mail.mailinator.com"],
    "mx_provider": "Custom MX",
    "did_you_mean": None,
    "processed_at": "2026-08-17T20:25:00.000Z",
    "request_id": "c81b37bd-4dcd-4958-b0a0-6ac163a92e9d",
    "audit_trail": {
        "client_ip_hash": "0100a7c695fbb157",
        "security_action": "BLOCKED",
        "l1_cache_hit": False,
        "l2_cache_hit": True
    }
}, indent=2)

# Sample 2: Compact Minified MCP Tool Response
MCP_TOOL_SINGLE_RESPONSE = json.dumps({
    "disposable": True,
    "confidence": "medium",
    "reason": "heuristic",
    "risk_score": 85,
    "did_you_mean": None
}, separators=(",", ":"))

# Sample 3: Traditional Verbose HTTP Batch Response (20 items)
TRADITIONAL_HTTP_BATCH_RESPONSE = json.dumps({
    "total_processed": 20,
    "results": [
        {
            "email": f"user_{i}@mailinator.com" if i % 2 == 0 else f"user_{i}@gmail.com",
            "domain": "mailinator.com" if i % 2 == 0 else "gmail.com",
            "disposable": i % 2 == 0,
            "confidence": "high",
            "reason": "known_provider" if i % 2 == 0 else "clean",
            "risk_score": 100 if i % 2 == 0 else 0,
            "mx_records": ["mx.mailinator.com"] if i % 2 == 0 else ["gmail-smtp-in.l.google.com"],
            "mx_provider": "Custom MX" if i % 2 == 0 else "Google Workspace",
            "did_you_mean": None,
            "request_id": f"req_{i}_abc123"
        }
        for i in range(20)
    ]
}, indent=2)

# Sample 4: Minified MCP Tool Batch Response (High-Risk summary only)
MCP_TOOL_BATCH_RESPONSE = json.dumps({
    "total_processed": 20,
    "disposable_count": 10,
    "high_risk_flagged": [
        {"domain": "mailinator.com", "disposable": True, "risk_score": 100, "reason": "known_provider"}
        for _ in range(10)
    ]
}, separators=(",", ":"))


def run_token_benchmark() -> list[dict]:
    benchmarks = [
        {
            "Workload / Query Type": "Single Email Verification",
            "Traditional HTTP Tokens": count_tokens(TRADITIONAL_HTTP_SINGLE_RESPONSE),
            "MCP Tool Tokens": count_tokens(MCP_TOOL_SINGLE_RESPONSE),
        },
        {
            "Workload / Query Type": "Batch Verification (20 Emails)",
            "Traditional HTTP Tokens": count_tokens(TRADITIONAL_HTTP_BATCH_RESPONSE),
            "MCP Tool Tokens": count_tokens(MCP_TOOL_BATCH_RESPONSE),
        },
    ]

    for b in benchmarks:
        trad = b["Traditional HTTP Tokens"]
        mcp = b["MCP Tool Tokens"]
        savings_percent = ((trad - mcp) / trad) * 100.0
        b["Token Reduction (%)"] = f"{savings_percent:.1f}%"
        b["Token Savings Ratio"] = f"{trad / mcp:.2f}x menor"

    return benchmarks


def export_csv(benchmarks: list[dict]) -> None:
    os.makedirs("docs", exist_ok=True)
    filepath = "docs/mcp_token_savings.csv"

    fieldnames = [
        "Workload / Query Type",
        "Traditional HTTP Tokens",
        "MCP Tool Tokens",
        "Token Reduction (%)",
        "Token Savings Ratio",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(benchmarks)

    print(f"✅ LLM Token Benchmark Complete. CSV exported: {filepath}")


if __name__ == "__main__":
    results = run_token_benchmark()
    print("\n📊 LLM Token Consumption Benchmark Results:\n")
    print(json.dumps(results, indent=2))
    export_csv(results)
