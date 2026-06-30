# Onboard

Interactive first-time setup for users with Claude Code or Codex. Detects the setup mode and routes to the appropriate flow.

> **No Claude Code or Codex?** Close this and open `SETUP_AGENT.md` or `SETUP_LLM_API.md` in your workspace. Those files are self-contained guides you can follow in any text editor or browser AI session.

**Rules:**
- Ask one topic at a time. Wait for the user's answer before proceeding.
- Detect and flag any template placeholder values — never treat them as configured.

---

## Step 1 — Detect Setup Mode

Ask:

> Welcome to Job Hunter onboarding. Two modes are available:
>
> **A — Agent mode** (Claude Code or Codex subscription)
> You review jobs interactively each day. Claude Code or Codex handles scoring, tailoring, and cover letters. No LLM API keys required.
>
> **B — LLM API mode** (Claude Code or Codex + LLM API keys)
> Full autonomous pipeline: scoring, tailoring, cover letters, and PDFs run automatically via Python and GitHub Actions.
>
> Which mode? Type **A** or **B**.

- **A** → execute `.claude/skills/setup/modes/onboard_agent.md` inline.
- **B** → execute `.claude/skills/setup/modes/onboard_llm_api.md` inline.
