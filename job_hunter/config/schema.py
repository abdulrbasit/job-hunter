"""Config schema validation helper."""

from __future__ import annotations

import json

import yaml

from job_hunter.config.paths import ROOT


def check() -> int:
    """Validate config/job_hunter.yml exists, parses, and matches its schema."""
    config_dir = ROOT / "config"
    config_path = config_dir / "job_hunter.yml"
    schema_path = config_dir / "schemas" / "job_hunter.schema.json"
    if not config_path.exists():
        print("Missing config file: config/job_hunter.yml")
        return 1
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"Invalid YAML in config/job_hunter.yml: {exc}")
        return 1
    if schema_path.exists():
        try:
            import jsonschema

            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=data, schema=schema)
        except Exception as exc:
            print(f"Config schema validation failed: {exc}")
            return 1
    print("config/job_hunter.yml ok")
    return 0
