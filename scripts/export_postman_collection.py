#!/usr/bin/env python3
"""Postman Collection Exporter for Disposable Email Verification API.

Converts FastAPI OpenAPI schema into a ready-to-import Postman Collection (v2.1.0).
"""

import json
from pathlib import Path
from typing import Any

from app.main import app


def convert_openapi_to_postman(openapi_schema: dict[str, Any]) -> dict[str, Any]:
    """Generates Postman v2.1.0 collection structure from OpenAPI schema."""
    collection = {
        "info": {
            "name": openapi_schema.get("info", {}).get("title", "Disposable Email Verification API"),
            "description": openapi_schema.get("info", {}).get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
        "variable": [
            {
                "key": "baseUrl",
                "value": "http://localhost:8000",
                "type": "string",
            },
            {
                "key": "apiKey",
                "value": "dev-local-secret-api-key",
                "type": "string",
            },
        ],
    }

    items = []
    paths = openapi_schema.get("paths", {})

    for path_url, methods in paths.items():
        for method_name, spec in methods.items():
            if method_name in ("get", "post", "put", "delete", "patch"):
                summary = spec.get("summary", f"{method_name.upper()} {path_url}")
                description = spec.get("description", "")

                request_item: dict[str, Any] = {
                    "name": summary,
                    "request": {
                        "method": method_name.upper(),
                        "header": [
                            {"key": "X-API-Key", "value": "{{apiKey}}", "type": "text"},
                            {"key": "Content-Type", "value": "application/json", "type": "text"},
                        ],
                        "url": {
                            "raw": "{{baseUrl}}" + path_url,
                            "host": ["{{baseUrl}}"],
                            "path": [p for p in path_url.split("/") if p],
                        },
                        "description": description,
                    },
                }

                # Add sample request body if POST
                if method_name == "post":
                    if path_url == "/v1/verify-email":
                        request_item["request"]["body"] = {
                            "mode": "raw",
                            "raw": json.dumps({"email": "user@mailinator.com"}, indent=2),
                        }
                    elif path_url == "/v1/verify-batch":
                        request_item["request"]["body"] = {
                            "mode": "raw",
                            "raw": json.dumps(
                                {"emails": ["user1@gmail.com", "user2@tempmail.com", "user3@gmai.com"]}, indent=2
                            ),
                        }

                items.append(request_item)

    collection["item"] = items
    return collection


def main() -> None:
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)

    openapi_schema = app.openapi()
    postman_coll = convert_openapi_to_postman(openapi_schema)

    postman_path = output_dir / "postman_collection.json"
    with open(postman_path, "w", encoding="utf-8") as f:
        json.dump(postman_coll, f, indent=2)

    print(f"✅ Postman Collection exported to: {postman_path}")


if __name__ == "__main__":
    main()
