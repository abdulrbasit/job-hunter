## What this does

<!-- One paragraph. What changes and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / source adapter
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Other:

## How to test

<!-- Steps to verify the change works. Include any relevant commands. -->

## Checklist

- [ ] Tests pass: `uv run pytest tests/ -q --tb=short`
- [ ] Lint clean: `uv run ruff check job_hunter tests`
- [ ] Formatted: `uv run ruff format --check job_hunter tests`
- [ ] Types pass: `uv run ty check job_hunter tests`
- [ ] No secrets, PDFs, or personal data committed
- [ ] `DATA_CONTRACT.md` updated if any config/state paths changed
- [ ] Workspace template synced if `SETUP.md` changed: `python scripts/sync_workspace_template.py`
