# Setup

One-time onboarding for a fresh workspace. Run `job-hunter doctor` first to see what is missing, then follow the steps below.

## Steps

1. **Verify config files exist**

   ```bash
   job-hunter config check
   ```

   Required: `config/job_hunter.yml`.

2. **Set API keys**

   Add fixed-name secrets in GitHub Actions or in your local environment:
   - LLM providers: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`
   - Search providers: `BRAVE_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`, `FIRECRAWL_API_KEY`
   - Job boards: `RAPIDAPI_KEY`, `JOOBLE_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_API_KEY`, `REED_API_KEY`

3. **Configure search regions**

   Edit `config/job_hunter.yml`: set at least one enabled region, job titles, deterministic exclusions, scoring thresholds, and LLM provider/model choices.

4. **Verify profile files**

   Place your resume, story bank, and career context in `profile/`:
   - The resume selected by `profile.resume_tex` in `config/job_hunter.yml`
   - `profile/story_bank.md`
   - `profile/career_context.md` for about-me notes, targeting, resume style, cover-letter style, LinkedIn positioning, outreach tone, and calibration

5. **Run health check**

   ```bash
   job-hunter doctor
   ```

   All items should report green before running a hunt.

## Notes

- This skill does not change git history.
- No keys or personal data should be committed.
- Re-run `/setup doctor` after each change to confirm the fix took effect.
