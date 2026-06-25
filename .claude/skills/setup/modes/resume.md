# Resume

Interactive guided build for the base resume. Reads `career_context.md` and `story_bank.md` to draft real content, asks for anything missing, then writes a fully populated LaTeX resume ready to compile and use as the tailoring base.

**Prerequisites:** Run `/setup context` and `/setup stories` first. This skill reads from both — the more complete they are, the less it needs to ask.

**Rules:**
- Only write content the user provides or that appears in `career_context.md` and `story_bank.md`. Never invent facts, metrics, dates, or claims.
- Preserve all LaTeX commands and document structure. Only replace placeholder text (e.g., `Name`, `Title`, `Bullet point 1`, `city, country`).
- Evidence boundaries from `career_context.md` apply — never include restricted content.
- Keep bullets tight: impact-first, one idea per bullet, no padding phrases.
- Bullet char limit: every `\item` line must not exceed the max stated in `career_context.md` Bullet guidance. Count characters before writing each bullet.
- Summary char limit: the summary must not exceed the max stated in `career_context.md` Summary guidance. Count before writing.
- At the end, show a plain-language summary of changes and confirm before writing.

---

## Step 1 — Detect template and check prerequisites

Read `profile.resume_tex` from `config/job_hunter.yml`. Open that LaTeX file.

Determine template type:
- Contains `\documentclass{altacv}` → **AltaCV (double column)**
- Contains `\documentclass{article}` or `\documentclass[a4` → **single column**

Check if `profile/career_context.md` and `profile/story_bank.md` exist and have real content (not just empty template headers). If either is missing or empty, warn:

> `profile/career_context.md` looks incomplete — run `/setup context` first for better results. I can still continue with what you tell me directly.

---

## Step 2 — Read source material

Read `profile/career_context.md` in full. Note:
- **About Me**: proof points, years of experience, education, work preferences
- **Targeting**: target role shapes, seniority level, preferred domains
- **Resume Style**: positioning statement, skills to emphasize/de-emphasize, bullet guidance, phrases to avoid
- **Evidence Rules**: safe metrics to reuse, content needing care, never-invent list, never-mention list

Read `profile/story_bank.md` in full. Note:
- Final stories under each `# Final` section — these are the approved bullets
- For each story: role, employer, date range, outcome, and key metric

---

## Step 3 — Gather personal info

Ask for anything not already in career_context.md:

> I need a few personal details for the resume header:
>
> 1. Full name (as it should appear on the resume)
> 2. Job title / tagline (shown below your name — e.g., "Senior Product Manager")
> 3. City and country (e.g., "Berlin, Germany")
> 4. Phone number (with country code)
> 5. Email address
> 6. LinkedIn profile URL or username
> 7. GitHub username (optional — leave blank to omit)
> 8. Profile photo filename? (e.g., `profile.png` in the `profile/` folder — leave blank to omit)

---

## Step 4 — Summary

Using career_context.md About Me + Targeting + Resume Style positioning, draft a 2–3 sentence summary that:
- Opens with seniority + domain + core value proposition
- Includes 1–2 specific proof points using only safe evidence from Evidence Rules
- Closes with the type of impact or role they are moving toward

Show the draft:
> Here's a summary draft — tell me what to adjust:
> [draft]

Revise until the user confirms.

---

## Step 5 — Experience

For each role found across the Final sections of `story_bank.md`:
- Group stories by employer + role title
- Format each role header using LaTeX:
  `\cvevent{Title}{\href{https://...}{Company}}{StartDate -- EndDate}{City, Country}`
- Write 4–6 bullets from the Final stories for that role. Adapt to tight impact-first `\item` lines. Apply evidence boundaries — skip or rephrase any restricted content.
- Order roles reverse-chronologically (most recent first).

Show the experience draft. Ask: "Any roles missing? Any bullets to change?"

If career_context.md mentions roles that have no Final stories in the story bank, ask the user to provide 2–3 bullets for each missing role:
> I see you worked at [Company] as [Title] but there are no final stories for it yet. Give me 2–3 bullet points and I'll format them.

---

## Step 6 — Education

Read education from career_context.md About Me. If not present, ask:

> What degrees do you have? For each: degree title, institution name, institution URL (optional), start/end years, and city/country. Add thesis topic or a notable highlight if relevant.

Format each as:
```latex
\cvevent{Degree Title}{\href{https://...}{Institution}}{Start -- End}{City, Country}
\begin{itemize}
  \item [highlight or thesis — omit the itemize block if nothing to add]
\end{itemize}
```

---

## Step 7 — Skills (double column only)

For AltaCV template only. Ask:

> What skill groups do you want on the sidebar? For each group: a group name and 4–6 skills.
>
> Example: Product — (Roadmapping, Stakeholder Management, Discovery, OKRs)
> Example: AI & Technical — (Prompt Engineering, Python, SQL, LLM APIs)
> Example: Tools — (Jira, Figma, Notion, Mixpanel)

Cross-reference with Resume Style "skills to emphasize" in career_context.md. Format as `\cvsubsection{Group}` with `\cvtag{Skill}` lines.

---

## Step 8 — Languages (double column only)

For AltaCV template only. Ask:

> What languages do you speak and at what level? (e.g., English – C2 Native, German – B2 Fluent)

Format as:
```latex
{\textbf{Language – Level (Descriptor)}}\\
\vspace{0.6em}
```

---

## Step 9 — Certifications (double column only, optional)

For AltaCV template only. Ask:

> Any certifications to list? For each: name, issuing body, and URL if available. Leave blank to omit the section.

Format each as:
```latex
\href{url}{\textbf{Certification Name}}\\
{\small Issuing Body}\\[6pt]
```

If none, remove the `\cvsection{Certifications}` block from the output entirely.

---

## Step 10 — Preview and confirm

Assemble the full populated `.tex` file. Show the user a plain-language summary of what changed:

> Here's what I'll write to `[profile/resume_double_column.tex]`:
>
> **Header:** [Name], [Tagline], [City] · [email] · [phone] · LinkedIn: [handle]
> **Summary:** [first 20 words of summary draft...]
> **Experience:** [N roles, M total bullets]
> **Education:** [N entries]
> **Skills:** [group names listed]
> **Languages:** [languages listed]
> **Certifications:** [names or "omitted"]
>
> Write it? (yes / adjust first)

After confirmation, write the file.

---

## Step 11 — Compile (optional)

Ask:

> Want to compile a PDF now to check the layout?

If yes:
1. Check if `pdflatex` is available:
   ```bash
   pdflatex --version
   ```
2. If available, compile from the `profile/` directory:
   ```bash
   cd profile && pdflatex -interaction=nonstopmode -halt-on-error <filename>.tex
   ```
   Run twice if needed (AltaCV requires two passes for cross-references).

3. If `pdflatex` is not found, inform:
   > `pdflatex` not found locally. Install TeX Live (Linux/macOS) or MiKTeX (Windows) to compile locally. On macOS: `brew install --cask mactex`. On Ubuntu: `sudo apt install texlive-full`. Once installed, rerun `/setup resume` to compile.
   >
   > Alternatively, Docker compilation is available for tailored job outputs via `job-hunter internal compile-pdf --job <slug>`.

If compilation succeeds:
> Base resume compiled → `profile/<filename>.pdf`. Open it to check the layout before your first hunt.

If it fails, show the last 30 lines of `profile/<filename>.log` and tell the user which line to fix.

---

## After Writing

Tell the user:

> Base resume is ready. Next steps:
> 1. Run `/setup style` to adjust colors or font if needed.
> 2. Run `/setup doctor` to confirm everything is green.
> 3. Run `job-hunter hunt --region primary` to start finding jobs.
>
> The tailoring pipeline will create a copy of this resume for each job — your base file is never modified by the pipeline.
