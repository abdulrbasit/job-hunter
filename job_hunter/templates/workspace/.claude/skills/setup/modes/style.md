# Style Resume

Single responsibility: read `profile.resume_tex` from `config/job_hunter.yml`, detect the selected resume template type, offer available style options from the preamble, and apply the chosen values to that file.

## Token Rules

- Inspect only the LaTeX preamble before `\begin{document}`.
- Present available color/font options, not the full resume.
- Print only the changed setting names.

## Steps

1. Read `profile.resume_tex` from `config/job_hunter.yml`, then read that LaTeX file. Determine template type:
   - Contains `\documentclass{altacv}` → **AltaCV (double column)**
   - Contains `\documentclass{article}` → **single column**

2. Extract available options from the preamble:
   - **AltaCV:** Look for `\definecolor` lines. Present color role names and current hex values.
   - **Both:** Look for commented-out `\usepackage{<fontname>}` lines. Present available font names.

3. Ask the user which color(s) or font to change and to what value.

4. Apply changes:
   - **Color:** Replace the hex value in the matching `\definecolor` line.
   - **Font:** Comment out the active `\usepackage{<font>}` line; uncomment the chosen font's line.

5. Print: `Resume styled. Run job-hunter compile-pdf --job <slug> to recompile.`

## Rules

- Never add new `\definecolor` or `\usepackage` lines — only edit existing ones.
- Never touch anything outside the preamble.
- If a font the user requests is not already commented-out in the preamble, say so and list only what is available.
