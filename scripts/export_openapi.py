#!/usr/bin/env python3
"""OpenAPI Specification Exporter.

Exports the active FastAPI OpenAPI schema as openapi.json and openapi.yaml
for API documentation portals, SDK generation, and Postman import.
"""

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from app.main import app


def export_spec() -> None:
    openapi_schema = app.openapi()
    output_dir = Path("docs")
    output_dir.mkdir(exist_ok=True)

    json_path = output_dir / "openapi.json"
    yaml_path = output_dir / "openapi.yaml"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False)

    print(f"✅ OpenAPI JSON exported to: {json_path}")
    print(f"✅ OpenAPI YAML exported to: {yaml_path}")


if __name__ == "__main__":
    export_spec()
