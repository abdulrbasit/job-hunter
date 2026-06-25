# Setup

## Agent mode (recommended)

Requirements: Python 3.12+, VS Code, Git, and either Claude Code or Codex.

```bash
uv tool install job-hunter-kit
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
job-hunter doctor
```

Open workspace in VS Code, then run:

```text
/setup onboard
/setup context
/setup stories
/setup resume
/setup doctor
```

Start first search:

```bash
job-hunter hunt --region primary
job-hunter brief
```

Review candidates with `/job-hunter batch`. Job applications are never submitted automatically.

## LLM API mode

Install optional SDKs:

```bash
uv tool install "job-hunter-kit[llm]"
```

Set `mode: llm-api` in `config/job_hunter.yml`, add only chosen provider key to `.env`, then run:

```bash
job-hunter doctor
job-hunter hunt --region primary
```

Supported keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`.

## GitHub Actions

Create private GitHub repository, push workspace, add required provider/source keys under repository Actions secrets, then run **Find Jobs** manually once. Enable workflow schedule only after manual run passes.

## Optional features

```bash
uv tool install "job-hunter-kit[browser]"  # browser-backed career pages
uv tool install "job-hunter-kit[secrets]"  # OS keyring
uv tool install "job-hunter-kit[all]"      # everything
```

Useful commands:

```bash
job-hunter dashboard --no-interactive
job-hunter applications list
job-hunter update
job-hunter version
```

Run `job-hunter doctor` after config or package changes.
