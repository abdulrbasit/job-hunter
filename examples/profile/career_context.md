# Career Context — John Doe (fictional example)
# All details below are invented. Replace everything with your own.

## About Me

- Current role: Senior Backend Engineer at FinFlow GmbH, Hamburg — real-time payments and ledger infrastructure
- Experience summary: 8 years in fintech and payments infrastructure; built and operated high-throughput transaction systems processing millions of events daily; comfortable owning services end-to-end from design through production operations
- Education: BSc Computer Science, University of Hamburg (2012–2016)
- Strongest proof points: Redesigned core ledger service to handle 10x traffic growth without additional infrastructure; reduced P99 latency on the settlement pipeline from 800ms to under 120ms; led migration of 6 legacy services from a monolith to independently deployable services
- Work I want more of: Technically deep infrastructure problems, distributed systems design, mentoring junior engineers, open-source adjacent work
- Work I want less of: Feature work with no systems depth, on-call-heavy roles without investment in reliability tooling, pure maintenance mode on aging codebases

## Targeting

- Target role shapes: Staff Engineer at a scale-up, Senior Backend Engineer with scope to move toward Staff at a larger org, Principal Engineer at a smaller company
- Target level: IC; not actively looking for engineering management, but open to a tech lead role with limited direct reports (up to 3)
- Strategic companies: Payments infrastructure, cloud tooling, developer platforms, fintech with genuine engineering challenges
- Preferred domains: Distributed systems, event streaming, financial infrastructure, database internals, observability tooling
- Dealbreakers that need judgment: No pure web/CRUD work at agencies; not interested in roles that are 80% meetings; wary of companies where infrastructure is not a first-class concern; no relocations outside Germany for now
- Role-shape notes: Open to Hamburg, Berlin, or fully remote; English-language teams strongly preferred but German-speaking is fine

## Resume Style

- Positioning: Backend engineer who specialises in high-throughput, low-latency systems — known for reducing complexity while improving reliability
- Tailoring priority: Lead with systems impact (latency, throughput, reliability), then scope (team size, service ownership), then language/stack match; de-emphasise soft skills unless the JD explicitly calls for them
- Skills to emphasize: Go, Rust, Kafka, PostgreSQL, Kubernetes, distributed systems design, observability (OpenTelemetry, Prometheus), service migrations
- Skills to de-emphasize: Early frontend work (React, one project 2016), Android internship (pre-career), generic Agile/Scrum involvement
- Proof-point priorities: Performance improvements with before/after numbers first, then scale anchors (events/sec, service count), then team and mentoring scope
- Summary guidance: 2 sentences max; opens with domain and years; mentions one concrete technical proof point; no filler phrases
- Bullet guidance: Lead with the outcome or the system change, then the approach, then the scope; avoid passive voice; preferred verbs: redesigned, reduced, shipped, migrated, eliminated, owned
- Evidence boundaries: Only use latency and throughput figures listed in Evidence Rules; service counts and team sizes are always safe
- Phrases or claims to avoid: "passionate about clean code", "full-stack" (not accurate), "10x engineer", any latency figure not in Evidence Rules

## Cover Letter Style

- Voice: Direct and technical; no marketing language; sounds like an engineer who knows what they want and has done the work to know it fits
- Salutation preference: "Dear [Name]," if known; "Hi [Team] Engineering Team," for startups; never "To Whom It May Concern"
- Opening preference: Open with a specific technical observation about their stack or a known engineering challenge at the company, then connect it to a concrete proof point
- Evidence preference: One strong technical result in paragraph one; don't repeat the entire resume
- Structure preference: 3 paragraphs — technical hook + proof point / relevant experience + why this specific company / brief close; under 220 words
- Closing preference: Express interest in the technical problem, not in "the opportunity"; don't beg for a response
- Phrases to avoid: "I am excited to apply", "I am a fast learner", "I thrive in fast-paced environments", "I would be a great addition"
- Evidence boundaries: Same as resume — only use verified latency and throughput figures

## LinkedIn Positioning

- Audience: Backend and infrastructure engineers, engineering managers at fintech and developer tooling companies, technical recruiters in Germany and remote-EU
- Content pillars: Distributed systems patterns and failure modes; Go and Rust in production; observability and reliability engineering; migration strategies for legacy systems
- Tone: Engineer-to-engineer; specific and opinionated; occasionally posts about things that didn't work as a learning; no inspirational posts
- Profile positioning: Senior backend engineer specialising in payments infrastructure; available for the right Staff or Senior role; building in public occasionally
- Post style: Start with a specific technical incident, pattern, or result; explain what was learned or what changed; no generic life lessons; under 250 words
- Networking targets: Engineering leads and CTOs at Series B–D fintech and infra companies in Germany and Europe, other backend engineers working on similar problems
- Topics to avoid publicly: Specifics of FinFlow's architecture or customers, any ongoing incidents, compensation figures, internal disputes
- Confidential details to never mention: FinFlow's transaction volumes, client names, infrastructure costs, internal service names

## Outreach Tone

- Networking message style: Mention a specific piece of their public technical work (blog post, talk, open-source repo) before anything else; keep it under 4 sentences; no flattery
- Recruiter message style: State what I'm looking for (Staff/Senior Backend, distributed systems, Go/Rust, Germany/remote) before asking what they have; open to a call but not urgent
- Follow-up style: One follow-up only, 7 days after no response; one sentence
- Maximum message length preference: Cold outreach under 100 words; follow-ups under 25 words
- Phrases to avoid: "I hope this finds you well", "I came across your profile", "mutual benefit", "I would love to pick your brain"

## Interview Prep

- Positioning: Open with current scope (payments infrastructure, 8 years), anchor to a concrete systems result, then explain what kind of technical challenge I'm looking for and why this role fits
- Stories to lean on: Ledger service redesign (scalability under load, architectural decision-making); settlement pipeline latency reduction (profiling, root cause, measurable result); monolith-to-services migration (planning, execution, team coordination across 6 services)
- Weak spots to handle carefully: No experience at FAANG or very large eng orgs (largest team was 12 engineers); limited formal CS theory beyond degree coursework; Rust is production-ready but Go is stronger
- Questions to ask interviewers: What does the on-call rotation look like today and what is the team doing to improve it? What's the hardest distributed systems problem the team is currently sitting with? How does technical direction get set — top-down or from the team? What would change if I joined?

## Evidence Rules

- Facts and metrics that are safe to reuse: Ledger service redesign handled 10x traffic growth with no infrastructure changes (FinFlow, 2023); settlement pipeline P99 latency reduced from 800ms to under 120ms (FinFlow, 2022); led migration of 6 services out of the monolith (18-month project, team of 4 engineers)
- Facts that require caution or context: Total transaction volume (not approved for external use — use "millions of events daily" as a floor, never exact); exact uptime SLA figures (say "high availability" unless asked directly); headcount at previous companies beyond what is listed above
- Never invent: Specific throughput numbers beyond what is listed, revenue impact claims, infrastructure cost savings with dollar figures, any named enterprise client
- Never mention: FinFlow's investor details, internal service or project codenames, any named colleague in a way that reflects poorly on them, anything covered by the NDA from the 2022 restructure

## Calibration

- Scores that felt too high: Roles titled "Backend Engineer" at growth-stage companies with no infrastructure scope got over-scored due to title matching; add check for "infrastructure" or "platform" scope signals in the JD
- Scores that felt too low: Staff Engineer roles at companies without an explicit IC track were sometimes under-scored; if the JD describes the scope of a Staff role, score it as one regardless of title
- Companies worth strategic override: NordPay Systems (former colleague now CTO; genuine technical fit), Tributary (open-source Kafka tooling company; mission alignment)
- Examples of good tailoring: Application to StreamCore — led with the settlement latency story, matched their "sub-100ms SLA" language in the JD; cover letter referenced their public blog post on Kafka consumer lag
- Examples of bad tailoring: Application to a web agency — used infrastructure proof points that had no relevance; score should have been filtered well below threshold
