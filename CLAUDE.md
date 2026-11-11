# CLAUDE.md — Tracewright (AI agent-based testing tool)

## Project overview

An AI-powered integration testing tool that generates, maintains, and runs Playwright tests grounded in business context (requirements documents, bug history, and later codebase analysis and UI exploration). The system derives tests from what the business **intends** — requirements, acceptance criteria, and past defects — with full traceability from every test back to its source.

**The moat is NOT the agent loop.** Playwright v1.56+ ships its own Planner/Generator/Healer agents, and "AI writes Playwright tests" is now a commodity. Our defensible surface is:

1. **Requirement-grounded planning**: tests derived from documents and bug history, not from crawling a live app. Coverage is measured against requirements, not pages visited.
2. **Full traceability**: every test card links to an acceptance criterion, business rule, or bug. When a test fails, the report says "AC-3 of REQ-1234 failed, regression of BUG-987" — not "click on .discount-input failed."
3. **Two-axis versioning**: source-artifact versions vs. target-environment versions, with runtime test filtering per environment. No competitor does this well.

**Primary ICP**: regulated industries (banking, healthcare, medical devices, gov contractors). These are the customers who actually HAVE versioned requirements PDFs and formal bug exports, and who MUST demonstrate requirement-to-test traceability for audits. The traceability_links table is a compliance artifact for them, not a nice-to-have.

**Strategic posture**: build on top of the Playwright ecosystem (MCP server, agent definitions, standard test output) wherever possible instead of reinventing it. Our value-add sits ABOVE that layer: ingestion, knowledge base, requirement-grounded planning, traceability, versioning.

**Open-source-first policy**: prefer open-source, self-hostable tools everywhere. Paid/cloud services are allowed only where open source is genuinely insufficient, and always behind a config flag with an open-source default. The only unavoidable external dependency in V1 is the LLM API itself.

---

## Architecture — three-tier evidence model

Tests are generated from three tiers of evidence, combined and weighted by confidence. The system gracefully degrades — a customer with rich docs gets deep requirement-traced tests; a customer with nothing but a URL still gets useful exploratory coverage (v2).

### Tier 1: Documents (strongest signal — drives traceability) — V1

- Source: uploaded PDFs (requirements, specs), Word docs, Excel bug exports
- Produces: acceptance-criterion-level test cases with full traceability
- Best at: business rules, negative paths, compliance, regression from bug history
- Limitation: only as good as the documentation

### Tier 2: Codebase (fills gaps, grounds in real behavior) — v2

- Source: Git repo access — route handlers, validation schemas, DB models, feature flags, auth middleware, PR history
- Produces: API integration tests, input boundary tests, access control tests, scenario variants
- Limitation: shows what IS built, not what SHOULD be built

### Tier 3: UI exploration (fallback when other tiers are weak) — v2

- Source: live app URL with auth context
- Produces: smoke-level flow tests, reachability coverage
- Limitation: can't validate business logic correctness
- Note: Playwright's own planner agent essentially IS this tier. When we build Tier 3, evaluate wrapping/extending Playwright's planner agent definition rather than writing our own explorer.

### How tiers combine

Every "testable thing" gets tagged with which tier(s) contributed. Agreement between tiers raises confidence; disagreement triggers a clarification flag for human review. The Planner builds a unified coverage map, picks the highest-confidence source for each testable thing, and generates test cards with source attribution.

**IMPORTANT V1 clarification — live-app access is required even in a Tier-1-only release.** Documents tell us WHAT to test, but not what the button is labeled, what the route is, or what the DOM looks like. A Generator working from documents alone will hallucinate locators and produce a wall of red on first run. Therefore V1 includes a narrow slice of live-app access:

- NOT for planning/exploration (that stays v2)
- ONLY for the Generator's locator-verification pass and page-object registry construction (see Generator below)
- Via the Playwright MCP server against the customer's staging URL with a pre-captured auth session

---

## Agent architecture — planner → generator → healer

Treat the agent trio as commodity plumbing. Where Playwright's official agent definitions (Markdown instruction files + MCP tools, regenerated via `npx playwright init-agents`) can be customized to our needs, use them as the substrate — especially for the Healer. Our custom logic is the RAG grounding, test-card metadata, and traceability injection.

### Planner agent (ours, RAG-grounded) — V1

- Retrieves business context from the knowledge base (hybrid search over pgvector + relational links)
- Does NOT explore the live app in V1
- Produces a structured test plan where every test card has:
  - Natural-language description
  - The acceptance criterion it covers
  - Related bugs it regresses against
  - Expected preconditions and user flow
  - **A setup-requirements manifest**: what test data must exist for this test (test user with role X, discount code in state Y, order in state Z). The customer fulfills these via fixtures; we do not silently assume data exists.
  - Source tier attribution with confidence score
- Flags ambiguous requirements as "needs clarification" rather than generating low-confidence tests
- Explicitly reports coverage gaps: "2 ACs from your doc have no test coverage"
- Output is a reviewable artifact (markdown/JSON), NOT hidden state

### Generator agent — V1

Runs in two phases, both against the live staging app via Playwright MCP:

**Phase 1 — App model / page-object registry (once per app, refreshed on demand):**
- Walk the flows referenced by approved test cards
- Build a shared page-object registry (one LoginPage, one CheckoutPage — not five slightly different ones per test)
- Record which locators resolve and how (role-based preferred)

**Phase 2 — Test generation (per approved test card):**
- Read the approved test plan card + setup manifest
- Generate TypeScript Playwright test code against the shared page-object registry
- **Verify every locator resolves to exactly one element against the live app before committing code.** Never emit an unverified locator.
- Locator strategy: role-based (getByRole, accessibility-tree-first). KNOWN LIMITATION: apps with poor accessibility markup break this. Fallback order: (1) getByRole, (2) getByTestId if the app has test ids, (3) CSS with an explicit stability warning attached to the test card, (4) emit a "recommend adding data-testid to element X" suggestion for the customer.
- Follows Page Object Model (POM) pattern
- Output is standard Playwright code the customer checks into git — no vendor lock-in
- Each test file includes metadata comments linking back to test card ID and source artifacts

### Healer agent — v2 (evaluate Playwright's official healer as the base)

- Runs after test failures in CI
- Fixes only locator/timing failures (selector drift, DOM changes, waits)
- **Outcome re-verification rule**: after healing, the Healer must confirm the test still validates the test card's expected OUTCOME — not merely that the run went green. A locator failure is often a symptom of a real regression (the button is gone because the feature broke); healing that masks a bug is worse than a red build.
- **Heal-frequency tracking**: every heal increments a counter on the test card. A test healed ≥3 times in 30 days escalates to human review regardless of pass status. "Which tests were healed, and how often do they break again" is a first-class dashboard metric.
- Logic/assertion failures are NEVER auto-healed — they escalate to the Planner with failure context
- Retry budget: 3 healing attempts per step, 10-minute global timeout per test. If exceeded, fail and file a ticket.

### Auth and test-session strategy — V1 (do not defer this)

Staging environments sit behind SSO, magic links, 2FA. The plan:
- One-time interactive auth capture: customer logs in once through a guided Playwright session; we persist storage state (cookies/localStorage) per environment
- Storage state is reused by the Generator's verification pass and by generated tests (standard Playwright `storageState` fixture)
- Storage state refresh flow when sessions expire
- Never store raw credentials; storage-state files are encrypted at rest per tenant

### Human-in-the-loop gates — with review-burden budgets

"Humans approve, machines execute" only works if review is FAST. A 50-page spec can yield 300+ chunks and 80+ test cards; if the QA lead spends 4 hours reviewing before seeing any tests, we've replaced test-writing with test-reviewing and the value prop dies.

1. **Ingestion review**: only chunks BELOW the confidence threshold are surfaced for mandatory review. Above-threshold chunks are auto-approved with a full undo trail and are still browsable. Bulk actions: approve-all-in-section, bulk reject.
2. **Planner review**: interactive cards with source traceability — approve, edit, or reject per test. Bulk approve by section/priority.
3. **Healer escalation** (v2): logic failures and heal-frequency breaches surface to the customer.

**Instrument review time per artifact as a first-class product metric from day one.** If median review time isn't well under the manual test-authoring baseline, the product doesn't work regardless of how good the AI is.

---

## Document analysis pipeline (open-source stack, simplified)

Design principle: **do not rebuild what the parsers already do.** Docling and MinerU already handle reading order, heading detection, header/footer stripping, and table structure. Our pipeline builds only the deltas: multi-page table merge, cross-reference resolution, semantic classification, stable IDs, confidence scoring.

### Parser lineup (all open source)

- **Primary parser (everything native)**: **Docling** (MIT, IBM) — PDFs, DOCX, PPTX, HTML, images. CPU-local. Use its TableFormer for tables. This replaces the previous Docling + Unstructured + Camelot trio — one parser, fewer failure modes.
- **Scanned / hard documents**: **MinerU** (AGPL — check license implications for our distribution model; if AGPL is a problem, use **PaddleOCR-VL** instead, Apache 2.0). Both are VLM-based and significantly outperform classic OCR pipelines on 2026 benchmarks. Needs GPU for speed.
- **Last-resort OCR fallback**: Tesseract (Apache 2.0) — CPU-only environments.
- **Excel**: openpyxl (MIT) + pandas (BSD).
- **Word (when semantic structure matters)**: python-docx (MIT) — explicit Heading 1/2 structure is free.
- **DROPPED from previous design**: Camelot (Ghostscript dependency, aging, struggles on modern PDFs — TableFormer + a flagged-table second-opinion covers it), Unstructured (Docling now covers its formats), classic PaddleOCR PP-Structure (superseded by VLM parsers).
- **Cloud OCR (config flag, OFF by default)**: an optional `parsing.backend = "cloud"` path (e.g., Mistral OCR or Gemini Flash) for customers who accept it. Note the honest framing: chunks already go to an LLM API for classification, so "OCR must be local" is a preference, not a hard privacy line — but open-source-local stays the default.

### Stage 1: Triage (no LLM, milliseconds)

- Per-page classification: native text vs scanned (pypdf/pdfplumber — extracted text < 50 chars on a non-blank page ⇒ scanned)
- Detect: language, encoding, password protection, page count
- Reject oversized docs with confirmation prompt
- Output: page manifest with type, language, word count per page

### Stage 2: Layout extraction (no LLM)

- Native pages → Docling. Scanned pages → MinerU (or PaddleOCR-VL).
- Tables: trust the primary parser's structure. On low table confidence, run a second-opinion pass (VLM on the table image) and compare; disagreement → human review flag. No permanent parallel Camelot pass.
- Output: structured intermediate JSON — typed blocks (heading, paragraph, list_item, table, figure_caption) with positional metadata. PERSIST this artifact — expensive to produce.

### Stage 3: Structure recovery (no LLM — deltas only)

- Verify/repair the parser's heading tree only where it's obviously wrong (numbering vs font-signal conflicts)
- Reassemble multi-page tables: same column count + same column widths + no intervening prose ⇒ merge, keep original header
- Resolve cross-references: "see section 3.4.2" → store original text + resolved link target
- Output: clean document tree — sections nested, blocks typed, references resolved

### Stage 4: Semantic classification (cheap LLM)

- Tag each block with closed vocabulary: `acceptance_criterion`, `business_rule`, `glossary_term`, `example`, `out_of_scope`, `metadata`
- `out_of_scope` drops 30–50% of typical requirement docs (revision history, stakeholder lists, document control)
- Watch for ambiguity between example and rule; tag context `example_of` linking to the actual rule
- Cheap model only (Haiku-class) — this is structured classification, not reasoning

### Stage 5: Normalization + content-based stable IDs (no LLM)

- Convert to canonical schema; capture provenance (source file, page, section path, line numbers); store raw text alongside structured extraction
- **Stable IDs are content-based, NOT positional.** The previous `REQ-{doc_version}-{section}-{ordinal}` scheme breaks the moment a customer inserts a section in v2.4 and everything renumbers — killing traceability and the diff agent.
  - Each chunk gets a permanent `logical_id` (opaque, e.g. `REQ-a1b2c3`) minted on first appearance
  - On re-upload of a new doc version, match new chunks to existing logical_ids via embedding similarity + fuzzy text match + section-path hints; carry the SAME logical_id forward with new version metadata
  - Unmatched new chunks mint new logical_ids; unmatched old chunks are marked removed-in-version
  - Human-readable display ID (`REQ v2.4 §4.2`) is derived metadata, never identity

### Stage 6: Embed and index (embedding model only)

- Embed at multiple granularities: chunk, parent section, full-document summary
- **Hybrid search**: keyword + vector similarity + reranker. Requirements use exact terminology where keyword match beats semantic similarity.
  - V1 keyword side: Postgres native full-text (`tsvector`/`ts_rank`) — good enough to start, zero extra infra. Note honestly: this is NOT true BM25.
  - Upgrade path when retrieval quality demands it: ParadeDB `pg_search` (BM25 in Postgres) or VectorChord-bm25. Both open source.
- Store in pgvector (same Postgres, just an extension)
- **Embedding dimension is a config value, not hardcoded.** Do not bake `vector(1536)` into migrations; read dim from config so switching embedding models isn't a table rewrite. Default: an open-weight embedding model (e.g., BGE-M3 or similar) to honor open-source-first; API embeddings behind the same config flag.

### Confidence scoring (runs across all stages)

- Every stage emits confidence per chunk
- Low-confidence sources: OCR score below threshold, ambiguous classification, unresolved references, table structural inconsistencies
- Chunks below threshold → human review queue before the Planner sees them; above threshold → auto-approved with undo trail

### Excel bug export handling

- Structured data — no LLM needed for parsing
- Column mapper: one-time UI step mapping customer headers to canonical schema (Severity vs Priority vs Sev). LLM-assisted suggestion, customer confirms. Store mapping per export format.
- Extractable fields: ID, title, description, severity, component, status, root cause, fix version, linked story
- Filter and weight precisely: "all Sev 1–2 bugs in Payments closed in last 6 months"

### LLM cost

- Per-tenant daily budgets enforced in the LLM wrapper. Every call tagged with tenant + feature.
- Do NOT quote per-document cost figures to customers; Planner reasoning over hundreds of chunks with a strong model dominates and varies widely.
- Future: local open-weight models (Qwen-class via Ollama/vLLM) for classification at zero marginal cost — consistent with open-source-first.

---

## Codebase analysis — six extraction targets (v2, unchanged design)

Static analysis by default. Extraction order: routes → validation schemas → DB models → auth → feature flags → git history. Skip implementation details, existing test code, generated code, dependencies. Every extraction emits the same unified schema shape as document chunks (`source: "code"`, `tier: 2`), so the Planner reasons over one deduplicated list. (Full details preserved from prior design; implement in v2.)

---

## Versioning model — two axes (the moat; design carefully)

### Axis 1: Source artifact version (what SHOULD be tested)
Requirements doc version, bug export version, code version. Increments when business intent changes.

### Axis 2: Target environment version (what's THERE to test against)
Environment name, deployed code version, applicable doc version, bug cutoff, URL, feature flags. Increments on every deployment. Manifest is itself versioned with an audit log.

### Version applicability — structured, not free-text

The previous `applicable_envs_rule: "code_version >= 2.4"` free-text expression is a trap: customers use version strings like `release-2.2-lts` that don't compare naturally against `2.4`. Replace with structured fields:

```json
{
  "applicability": {
    "min_code_version": "2.4",
    "max_code_version": null,
    "env_allowlist": null,
    "env_denylist": ["customer-acme"]
  }
}
```

- Customers declare their version ORDERING explicitly (a simple ordered list or semver-parse rule per tenant, set up once). Never guess ordering from string comparison.
- Versions form a tree, not a line (v2.3.1 child of v2.3). A test introduced in v2.3 applies to all descendants unless explicitly deprecated.

### Test filtering at run-time

1. Look up env's code_version and doc_version from manifest
2. Select test cards where introduced_in_version ≤ env.code_version (per declared ordering)
3. Exclude where deprecated_in_version is set and ≤ env.code_version
4. Apply allowlist/denylist
Single test repository serves all environments; filtering is runtime. No branching tests.

### Document version diffing on re-upload

1. Match chunks by logical_id (content-based matching from Stage 5)
2. Classify each as unchanged / modified / new / removed
3. Re-plan only affected tests; modified sections flag linked tests; new sections generate proposals; removed sections deprecate linked tests (with confirmation)

### Staleness warnings

Dashboard warns: "production deployed v2.4 on May 20, but latest requirements doc is v2.3 from March."

---

## Technology stack

### Backend (Python)

- **Runtime**: Python 3.12
- **Package manager**: uv
- **Web framework**: FastAPI
- **Database**: PostgreSQL 16 + pgvector
- **Object storage**: MinIO (S3-compatible, self-hostable)
- **Task queue**: Redis + **arq** (async, lightweight — Celery is more than V1 needs)
- **ORM**: SQLAlchemy 2.0 + Alembic

### Document parsing (all open source)

- Docling (primary: PDF/DOCX/PPTX/HTML), MinerU or PaddleOCR-VL (scanned), Tesseract (last resort), openpyxl + pandas (Excel), python-docx (Word)
- System deps: poppler, tesseract, libmagic

### LLM layer

- **Primary API**: Anthropic Claude (Sonnet-class for Planner, Haiku-class for classification)
- **Abstraction**: litellm or thin internal wrapper — never wire SDK calls directly throughout the codebase; local open-weight models must be swappable via config
- **Observability**: Langfuse (MIT, self-hostable) from day one — prompts, responses, costs, latency per call
- NOTE: a Claude Max subscription covers Claude Code (development). The PRODUCT's runtime Planner/classifier calls need an Anthropic API key with its own billing. Keep these separate in config.

### Test generation output

- TypeScript + Playwright, POM pattern, role-based locators with the fallback ladder defined above
- Playwright MCP server for the Generator verification pass (V1) and Tier 2/3 exploration (v2)
- Evaluate Playwright's official agent definitions (`npx playwright init-agents`) as the Generator/Healer substrate before writing custom agents

### Frontend

- React + TypeScript + Vite, Tailwind CSS, shadcn/ui
- Key pages: ingestion review, Planner review (interactive cards), environment dashboard, test catalog

### Observability

- Structured JSON logging; OpenTelemetry + Jaeger; Langfuse; Sentry (self-hosted); per-call LLM cost recorder in Postgres tagged by tenant + feature
- **Product metrics from day one**: review time per artifact, % chunks auto-approved, human edits per generated test, locator verification pass rate

### Infrastructure (Docker for local dev)

- PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`), MinIO, Redis, Langfuse, OTel Collector + Jaeger

### Security posture (enterprise buyers ask before pilots)

- Multi-tenant from day one: every DB row has tenant_id
- Per-tenant encryption for uploaded docs and auth storage-state files
- Zero-data-retention agreements with LLM API providers; document the data flow (which content leaves the box, to whom, retained how long)
- Self-hostable deployment story is a sales asset for the regulated ICP — keep everything Docker-composable

---

## Evaluation harness (V1 — we build a testing tool; we test the tool)

- Golden set: 3–5 real-ish requirement docs + one demo app we control (seeded data, known ACs)
- Metrics per pipeline change:
  - % of ACs producing a passing generated test with zero human edits
  - Human edits per generated test
  - Locator verification pass rate
  - Chunk classification accuracy vs hand-labeled golden set
  - Median review time per artifact
- Run the harness on every meaningful prompt/parser/model change. No eval, no merge.

---

## Design decisions locked in

- **Traceability + versioning is the product; the agent loop is plumbing.** Build on Playwright's ecosystem, differentiate above it.
- **Open-source-first**: paid/cloud services only behind config flags with open-source defaults. LLM API is the only unavoidable external dependency.
- **Multi-tenant from day one.**
- **Test code goes in the customer's git repo**: tool writes to a branch, opens PR, customer merges. No vendor lock-in.
- **Authoring-time AI, deterministic runtime**: LLM generates and maintains tests; execution is deterministic Playwright.
- **Never emit an unverified locator.**
- **Content-based stable IDs** — identity survives document renumbering.
- **Structured version applicability** — no free-text version expressions.
- **Review time is a product metric**, not an afterthought.
- **LLM cost guardrails**: per-tenant daily budgets, every call tagged.
- **File-based ingestion primary**; live connectors (Jira, Confluence) are a v2+ add-on.
- **Monorepo**: workspaces for backend, frontend, CLI, test scaffold.

---

## V1 scope — the first prototype

**Success sentence**: "A customer uploads a requirements PDF and a bug Excel export, reviews the flagged extractions in a web UI, approves a test plan with full traceability, and gets back a folder of Playwright tests — with locators verified against their staging app — that run green on their staging environment."

### V1 includes

- PDF + Excel ingestion pipeline (Stages 1–6) with Docling (+ MinerU for scanned pages)
- Semantic classification via LLM API; confidence-gated review (auto-approve above threshold)
- Ingestion review page
- Planner agent generating test plan with setup-requirements manifests per test
- Planner review page with interactive cards, traceability, approve/edit/reject, bulk actions
- **Auth session capture** (one-time guided login → encrypted storage state per environment)
- **Generator Phase 1**: page-object registry built against the live staging app
- **Generator Phase 2**: Playwright TypeScript with live locator verification (never emit unverified locators)
- Per-environment fixture files in the test scaffold; tests read setup manifests from fixtures
- **CI template**: a ready-made GitHub Actions workflow in the scaffold (cheap win — customers run tests in CI on day one)
- Single environment support
- Test metadata with source artifact links (content-based logical IDs)
- Langfuse tracing + review-time/edit-count metrics from day one
- **Evaluation harness + golden set**

### V1 does NOT include

- Tier 2 codebase analysis (v2)
- Tier 3 UI exploration for PLANNING (v2) — note the Generator's verification pass against the live app IS in V1
- Healer agent (v2)
- Multi-environment versioning UI (v2) — but schema and content-based IDs are designed for it NOW
- Live connectors (Jira, Confluence) (v2+)
- Parallel test execution infrastructure (v2+)

---

## Project structure

```
tracewright/
├── CLAUDE.md
├── docker-compose.yml                 # Postgres+pgvector, MinIO, Redis, Langfuse, Jaeger
├── pyproject.toml                     # uv workspaces
│
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py                  # incl. embedding dim, parsing backend flag, LLM keys
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   ├── migrations/
│   │   │   └── session.py
│   │   ├── ingestion/
│   │   │   ├── triage.py             # Stage 1
│   │   │   ├── layout.py             # Stage 2: Docling / MinerU dispatch
│   │   │   ├── structure.py          # Stage 3: deltas only (table merge, xrefs)
│   │   │   ├── classify.py           # Stage 4: LLM classification
│   │   │   ├── normalize.py          # Stage 5: canonical schema
│   │   │   ├── identity.py           # Stage 5: content-based logical_id matching
│   │   │   ├── embed.py              # Stage 6
│   │   │   ├── excel.py              # bug export parser + column mapper
│   │   │   └── confidence.py
│   │   ├── knowledge/
│   │   │   ├── vector_store.py       # pgvector + tsvector hybrid search
│   │   │   ├── graph.py              # traceability links
│   │   │   └── retrieval.py          # RAG retrieval for Planner
│   │   ├── agents/
│   │   │   ├── planner.py
│   │   │   ├── generator/
│   │   │   │   ├── app_model.py      # Phase 1: page-object registry via Playwright MCP
│   │   │   │   ├── codegen.py        # Phase 2: test generation + locator verification
│   │   │   │   └── locators.py       # fallback ladder: role → testid → CSS+warning
│   │   │   ├── healer.py             # v2
│   │   │   └── prompts/
│   │   ├── llm/
│   │   │   ├── client.py             # litellm wrapper; local-model swappable
│   │   │   ├── cost.py               # per-call recorder + per-tenant budgets
│   │   │   └── langfuse.py
│   │   ├── auth_capture/             # storage-state capture, encryption, refresh
│   │   │   └── sessions.py
│   │   ├── versioning/
│   │   │   ├── manifests.py
│   │   │   ├── ordering.py           # per-tenant declared version ordering
│   │   │   ├── diff.py               # logical_id-based doc diffing
│   │   │   └── filtering.py
│   │   ├── api/
│   │   │   ├── upload.py
│   │   │   ├── ingestion.py
│   │   │   ├── plans.py
│   │   │   ├── tests.py
│   │   │   └── environments.py
│   │   └── storage/
│   │       └── files.py
│   ├── tests/
│   └── evals/                         # golden set + eval harness
│       ├── golden/                    # sample docs, labeled chunks, demo-app ACs
│       └── run_evals.py
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── pages/
│       │   ├── IngestionReview.tsx
│       │   ├── PlannerReview.tsx
│       │   ├── EnvironmentDashboard.tsx
│       │   └── TestCatalog.tsx
│       └── components/
│           ├── TestCard.tsx
│           ├── CoverageStats.tsx
│           └── ColumnMapper.tsx
│
├── demo-app/                          # small seeded web app for the eval harness
│
├── test-scaffold/
│   ├── package.json
│   ├── playwright.config.ts
│   ├── .github/workflows/tests.yml    # ready-made CI template
│   ├── page-objects/
│   └── fixtures/                      # per-environment test data
│
└── scripts/
    ├── seed-dev-db.py
    └── test-parse-pdf.py
```

---

## Database schema (core tables — updated)

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    version_ordering JSONB DEFAULT '[]',  -- declared ordered list of version strings
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE source_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    type TEXT NOT NULL,                -- 'document', 'bug_export', 'codebase_snapshot'
    filename TEXT NOT NULL,
    version TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'processing',
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    artifact_id UUID REFERENCES source_artifacts(id),
    logical_id TEXT NOT NULL,          -- content-based identity, stable across versions
    chunk_type TEXT NOT NULL,
    content TEXT NOT NULL,
    raw_content TEXT,
    display_ref TEXT,                  -- 'REQ v2.4 §4.2' (derived, NOT identity)
    section_path TEXT,
    page_number INT,
    confidence FLOAT DEFAULT 1.0,
    review_status TEXT DEFAULT 'pending',   -- 'auto_approved', 'pending', 'approved', 'rejected', 'needs_clarification'
    reviewed_at TIMESTAMPTZ,
    review_duration_ms INT,            -- review-time metric
    metadata JSONB DEFAULT '{}',
    tsv tsvector,                      -- keyword side of hybrid search
    embedding vector                   -- dimension set per deployment config, not hardcoded
);
CREATE INDEX chunks_tsv_idx ON chunks USING gin(tsv);

CREATE TABLE bugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    artifact_id UUID REFERENCES source_artifacts(id),
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT,
    component TEXT,
    status TEXT,
    root_cause TEXT,
    fix_version TEXT,
    linked_story TEXT,
    closed_at DATE,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE test_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    test_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    preconditions TEXT,
    setup_manifest JSONB DEFAULT '[]',     -- required test data (users, records, states)
    test_type TEXT,
    priority TEXT,
    introduced_in_version TEXT NOT NULL,
    deprecated_in_version TEXT,
    supersedes TEXT[],
    applicability JSONB DEFAULT '{}',      -- structured: min/max version, allow/deny lists
    tier_sources JSONB NOT NULL,
    locator_strategy TEXT,                 -- 'role', 'testid', 'css_warned'
    heal_count INT DEFAULT 0,              -- lifetime heals; ≥3/30d escalates (v2)
    approval_status TEXT DEFAULT 'pending',
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    review_duration_ms INT,
    playwright_code_path TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE traceability_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    test_card_id UUID REFERENCES test_cards(id),
    linked_type TEXT NOT NULL,             -- 'chunk', 'bug'
    linked_logical_id TEXT NOT NULL,       -- links to logical_id, survives doc versions
    link_reason TEXT
);

CREATE TABLE environments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name TEXT NOT NULL,
    url TEXT,
    code_version TEXT NOT NULL,
    doc_version TEXT,
    bug_cutoff DATE,
    feature_flags JSONB DEFAULT '{}',
    auth_state_path TEXT,                  -- encrypted storage-state file in MinIO
    updated_at TIMESTAMPTZ DEFAULT now(),
    revision INT DEFAULT 1
);

CREATE TABLE test_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    environment_id UUID REFERENCES environments(id),
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    total_tests INT, passed INT, failed INT, skipped INT,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE test_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES test_runs(id),
    test_card_id UUID REFERENCES test_cards(id),
    status TEXT NOT NULL,                  -- 'passed', 'failed', 'skipped', 'healed'
    healed BOOLEAN DEFAULT false,
    duration_ms INT,
    error_message TEXT,
    trace_path TEXT,
    screenshot_path TEXT
);
```

---

## First two weeks — build order

### Week 1

- [ ] Day 1 — tooling: Python 3.12 (pyenv), uv, Node 20 LTS, pnpm, Docker, repo, Anthropic API key (separate from Claude Max — product runtime needs its own API billing)
- [ ] Day 2 — infra: docker-compose (Postgres+pgvector, MinIO, Redis, Langfuse); verify pgvector; create MinIO bucket
- [ ] Day 3 — parsing PoC: `uv add docling openpyxl python-docx`; parse ONE real requirements PDF end-to-end with Docling, print structured output; eyeball it (this reveals 80% of what the pipeline will face). Try MinerU on a scanned sample; note license fit.
- [ ] Day 4 — LLM + tracing: Langfuse wired; first classification call on a real chunk; verify cost tracking
- [ ] Day 5 — scaffold: FastAPI structure, initial Alembic migrations (config-driven embedding dim), upload endpoint (file → MinIO → arq parsing job), Stage 1 triage live

### Week 2

- [ ] Demo app: pick/build a small seeded web app with known ACs (the eval harness target)
- [ ] Golden set v0: 2 requirement docs, hand-label 50 chunks, write run_evals.py (classification accuracy first)
- [ ] Auth capture spike: guided Playwright login → storage state persisted + reused
- [ ] Generator spike: one approved test card → page-object registry entry → generated test with VERIFIED locators → green run against demo app
- [ ] If the Generator spike works end-to-end on the demo app, the V1 success sentence is de-risked; everything after is breadth

---

## Key principles

1. **Tests come from intent, not observation.** Documents tell you what SHOULD happen; the live app tells you what DOES. The gap is bugs.
2. **Every test traces to a source.** No orphan tests. Traceability links survive document re-versioning (content-based IDs).
3. **Humans approve, machines execute — and review must be cheap.** Auto-approve high confidence, surface only what needs eyes, measure review time.
4. **Deterministic runtime.** AI writes tests; Playwright runs them. No LLM in the execution loop.
5. **Never emit an unverified locator.** Every locator is confirmed against the live app before code is committed.
6. **Healing must preserve intent, not just turn builds green** (v2). Repeated healing is a signal, not a success.
7. **Graceful degradation.** Rich docs → deep tests. Thin docs → still useful coverage. Never "we can't help you."
8. **Staleness is visible.** Every artifact shows freshness; drift is surfaced.
9. **Cost is controlled.** Every LLM call tagged, budgeted, traced. Cheap models for classification, strong models for reasoning.
10. **Open source until necessary.** Paid services only behind config flags with open-source defaults.
11. **Eval before merge.** The golden-set harness gates pipeline changes.
