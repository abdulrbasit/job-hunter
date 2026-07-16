"""Config schema validation helper."""

from __future__ import annotations

import yaml

from job_hunter.config.paths import ROOT


def check() -> int:
    """Validate config/job_hunter.yml exists, parses, and matches its schema."""
    config_dir = ROOT / "config"
    config_path = config_dir / "job_hunter.yml"
    if not config_path.exists():
        print("Missing config file: config/job_hunter.yml")
        return 1
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"Invalid YAML in config/job_hunter.yml: {exc}")
        return 1
    from job_hunter.config.service import validate_job_hunter_yaml

    errors = validate_job_hunter_yaml(data, ROOT)
    if errors:
        print(f"Config schema validation failed: {'; '.join(errors)}")
        return 1
    print("config/job_hunter.yml ok")
    return 0
