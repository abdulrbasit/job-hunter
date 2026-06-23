# Style Resume

Interactive styling for the active resume template. Lets the user change colors, fonts, font size, and layout options one at a time — or all at once if they want a full refresh.

**Rules:**
- Detect the template type first — available options differ between AltaCV (double column) and the single-column article template.
- Never add new LaTeX commands or packages that are not already present or commented out in the file.
- Only edit the preamble (everything before `\begin{document}`).
- Apply one change at a time and show exactly what line will change before writing.
- After all changes are applied, print a short summary and remind the user to recompile.

---

## Step 1 — Detect template

Read `profile.resume_tex` from `config/job_hunter.yml`. Open that LaTeX file.

- Contains `\documentclass{altacv}` → **AltaCV (double column)**
- Contains `\documentclass{article}` → **single column**

---

## Step 2 — Show change menu

Tell the user what can be changed for their template, then ask what they want:

**AltaCV (double column):**

> Your resume is the **AltaCV double-column** layout. Here's what you can change:
>
> 1. **Colors** — heading/name color, accent color (dates), body text color, job title color
> 2. **Font** — choose a font family (sans-serif or serif)
> 3. **Font size** — base document font size (8pt – 11pt; default 9pt)
> 4. **Column ratio** — how wide the main (left) column is relative to the sidebar
> 5. **Paper format** — A4 or US Letter
>
> What would you like to change? (type a number, multiple numbers, or "all")

**Single column:**

> Your resume is the **single-column** layout. Here's what you can change:
>
> 1. **Font** — choose a font family (sans-serif or serif)
> 2. **Font size** — base document font size (10pt, 11pt, 12pt; default 11pt)
> 3. **Section rule color** — the horizontal rule under each section heading
> 4. **Paper format** — A4 or US Letter
>
> What would you like to change? (type a number, multiple numbers, or "all")

---

## Colors (AltaCV only)

Read the six `\definecolor` lines from the preamble:
```
PrimaryColor   — headings, name, tagline
SecondaryColor — secondary headings
ThirdColor     — tertiary headings
BodyColor      — body text
EmphasisColor  — job titles in experience entries
AccentColor    — dates, company names
```

Show the current hex values and offer two paths:

### Option A — Color preset

> Choose a named color scheme, or enter hex values manually (Option B):
>
> 1. **Dark Navy** (default) — headings `#1B2A4E`, accent `#7A8DA8`
> 2. **Classic Black** — headings `#000000`, accent `#555555`
> 3. **Midnight Blue** — headings `#1A237E`, accent `#5C6BC0`
> 4. **Slate** — headings `#37474F`, accent `#78909C`
> 5. **Forest** — headings `#1B5E20`, accent `#66BB6A`
> 6. **Burgundy** — headings `#4A0010`, accent `#B03050`
> 7. **Warm Charcoal** — headings `#2C2C2C`, accent `#9E7B5A`
> 8. **Manual** — I'll enter hex values myself

Preset mappings:
- Headings preset → set PrimaryColor, SecondaryColor, ThirdColor, EmphasisColor all to the headings hex
- Accent preset → set AccentColor to the accent hex
- BodyColor is always kept at `#1A1A1A` (near-black) unless the user explicitly changes it

### Option B — Manual hex

Ask the user which color role(s) they want to change and what hex value(s) to use.

Replace only the hex portion in the matching `\definecolor` lines:
```
\definecolor{PrimaryColor}{HTML}{<NEW_HEX>}
```

---

## Font (both templates)

**AltaCV:** Look for the `%FONT OPTIONS` block. Show the available font names and which one (if any) is currently active (uncommented).

Available options:
- `roboto` — modern, clean sans-serif (popular for tech resumes)
- `lato` — rounded, friendly sans-serif
- `sourcesanspro` — neutral, highly readable sans-serif
- `noto-sans` — open, international-friendly sans-serif
- `FiraSans` — geometric, distinctive sans-serif
- `CormorantGaramond` — elegant serif for traditional sectors
- `charter` — readable old-style serif
- `lmodern` — LaTeX default (Latin Modern)

Ask:

> Which font would you like? (or "none" to use the LaTeX default)

To apply:
1. Comment out the currently active font line (if any).
2. Uncomment the chosen font's line.
3. If the chosen font is not in the list, say so and list only what is available — never add new packages.

**Single column:** Same process — comment out the currently active `\usepackage{...}` line, uncomment the chosen one.

Available options for single column (from the `%FONT OPTIONS` block):
- `FiraSans` — geometric sans-serif
- `roboto` — modern sans-serif
- `noto-sans` — default active
- `sourcesanspro` — neutral sans-serif
- `CormorantGaramond` — elegant serif
- `charter` — readable serif

---

## Font size (both templates)

**AltaCV:** The font size is the first option in `\documentclass[<SIZE>pt,a4paper,...]`.

Valid sizes: `8pt`, `9pt` (default), `10pt`, `10.5pt`, `11pt`

Ask:

> Current font size: **9pt**. AltaCV works best at 9pt–10pt for one-page resumes. What size would you like?

Replace the size value in the `\documentclass` line only.

**Single column:** The font size is the second option in `\documentclass[a4,<SIZE>pt]{article}`.

Valid sizes: `10pt`, `11pt` (default), `12pt`

Ask:

> Current font size: **11pt**. What size would you like? (10pt, 11pt, 12pt)

Replace the size value in the `\documentclass` line only.

---

## Column ratio (AltaCV only)

Find the line: `\columnratio{0.70}`

Ask:

> Current column ratio: **0.70** (main column takes 70% of the width, sidebar 30%).
>
> Options:
> - `0.65` — slightly wider sidebar (more room for skills/tags)
> - `0.68` — balanced
> - `0.70` — default
> - `0.72` — slightly narrower sidebar
> - `0.75` — wide main column, compact sidebar

Replace the value in `\columnratio{...}` only.

---

## Section rule color (single column only)

Find the line containing `\color{black}\titlerule` in the `\titleformat{\section}` block.

Ask:

> Current section rule color: **black**. Common alternatives:
> - `black` (default)
> - a hex color — enter as `[HTML]{RRGGBB}` (e.g., `[HTML]{1B2A4E}` for dark navy)
> - a named LaTeX color: `gray`, `darkgray`, `blue`, `teal`

Replace the `\color{black}` in that line only.

---

## Paper format (both templates)

**AltaCV:** Find `a4paper` in `\documentclass[...,a4paper,...]`.
Replace with `letterpaper` for US Letter.

**Single column:** Find `a4` in `\documentclass[a4,...]{article}`.
Replace with `a4paper` (correct name) or `letterpaper`.

Ask:

> Paper format: **A4** or **US Letter**?

---

## Apply and confirm

Before writing, show each change as a before/after line:

```
Colors:
  \definecolor{PrimaryColor}{HTML}{1B2A4E}  →  \definecolor{PrimaryColor}{HTML}{1A237E}

Font:
  % \usepackage[sfdefault]{lato}             →  \usepackage[sfdefault]{lato}
  \usepackage[sfdefault]{noto-sans}          →  % \usepackage[sfdefault]{noto-sans}

Font size:
  \documentclass[9pt,a4paper,...]           →  \documentclass[10pt,a4paper,...]
```

Ask: "Apply these changes? (yes / adjust)"

After writing, print:

```
Resume styled.
Changed: [list what changed]
To see the result: run /setup resume → compile, or run pdflatex profile/<filename>.tex
```
