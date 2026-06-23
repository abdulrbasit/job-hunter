"""Validate config/job_hunter.yml against config/schemas/job_hunter.schema.json."""

import json
import pathlib

import jsonschema
import yaml

schema_path = pathlib.Path("config/schemas/job_hunter.schema.json")
config_path = pathlib.Path("config/job_hunter.yml")

if schema_path.exists() and config_path.exists():
    schema = json.loads(schema_path.read_text())
    data = yaml.safe_load(config_path.read_text())
    jsonschema.validate(data, schema)
    print("ok: job_hunter.yml")
else:
    print("skipped: config/job_hunter.yml or schema not found")
