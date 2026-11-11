# Notice — build plan

## 1. Repo structure

```
.
├── backend/                     Python 3.12+, FastAPI
│   ├── notice/
│   │   ├── config.py            env-driven settings
│   │   ├── db.py                engine/session
│   │   ├── models.py            SQLAlchemy models (single source of truth for the schema)
│   │   ├── security.py          password hashing, JWT
│   │   ├── api/                 routers: auth, projects, documents, contract, review, events, deadlines, audit
│   │   ├── ingestion/           extractors (pdf/docx/xlsx/eml/msg/whatsapp/image+OCR), item splitting, chunking
│   │   ├── retrieval/           local embedder + pgvector search (no data leaves the box)
│   │   ├── contract/            clause splitter, rule extraction service, rule approval
│   │   ├── deadlines/           deterministic deadline engine + calendars (IE/UK holidays, shutdowns)
│   │   ├── record/              append-only project event log + audit log (hash-chained)
│   │   ├── llm/                 provider interface: ClaudeProvider (Anthropic SDK) + OfflineProvider
│   │   ├── agents/              base Agent contract, registry, citation validator, one package per agent
│   │   ├── review/              review queue service (approve / edit / dismiss, action log)
│   │   ├── export/              DOCX / PDF export of approved drafts
│   │   └── jobs/                Postgres-backed job queue + worker
│   ├── alembic/                 migrations
│   ├── seed/                    demo project loader
│   └── tests/
├── prompts/                     versioned prompt files: <agent>/<task>.v<N>.md
├── demo_data/riverside/         generated synthetic project (contract, emails, WhatsApp, diaries, drawings, quotes, compliance)
├── evals/notice_agent/          labelled messages + harness that prints precision/recall/clause accuracy
├── web/                         Next.js + TypeScript + Tailwind
├── docker-compose.yml           db (postgres+pgvector), api, worker, web
└── README.md
```

## 2. Data model

All rows carry `project_id` (and through the project, `org_id`) for tenancy. Source material is immutable.

| Table | Purpose / key columns |
|---|---|
| `organisations`, `users`, `memberships` | tenancy; users belong to one org (MVP), role `admin`/`member` |
| `projects` | name, location, contract form, `holiday_region` (IE / GB-ENG / GB-NIR), `working_week` |
| `project_shutdowns` | name, start, end (Christmas, construction holiday) — fed to the deadline engine |
| `parties` | employer, employer's representative, contractor, subcontractors; name, role, email |
| `documents` | kind, source, filename, mime, author, `doc_timestamp`, `sha256` (unique per project), storage path, extracted text, extraction method (text/ocr), metadata. **DB trigger blocks UPDATE of content columns and DELETE.** |
| `items` | atomic messages inside a document (one email, one WhatsApp line-group, one diary entry): author, timestamp, text, `char_start/char_end` into the parent document, sha256. Agents operate on items. |
| `chunks` | retrieval chunks with `embedding vector(384)` (pgvector, HNSW index) |
| `contracts` | the contract document + status `extracting → pending_review → approved` |
| `contract_clauses` | ref (e.g. `10.2`), title, text, char span in the contract document |
| `contract_rules` | structured obligations: `rule_type` (notice / time_bar / payment / retention / variation / eot), clause ref, trigger event, `event_categories`, `period_value`, `period_unit` (working_days / calendar_days / weeks / months), recipient, required form, condition precedent, source quote+span, confidence, **status `proposed → approved/rejected`**, approver |
| `events` | the project's register of potential changes/delays/instructions/disruptions: category, title, trigger date, status, source item, rule |
| `deadlines` | event × rule: trigger date, due date, full computation trace (JSON), status |
| `drafts` | agent-drafted documents (notices…): subject, body, recipient, version, status `draft → approved → exported` |
| `agent_runs` | agent, agent version, prompt version, provider/model, inputs, validated JSON output, tokens, status |
| `review_items` | the single inbox: agent, kind, title, payload, **citations**, confidence, `low_confidence`, status, links to event/draft/rule |
| `review_actions` | every approve / edit / dismiss with before/after JSON (future training & eval data) |
| `project_log` | append-only domain event log (`document.ingested`, `event.created`, `deadline.started`…) |
| `audit_log` | who/what/when/which source; hash-chained (`prev_hash`,`hash`), UPDATE/DELETE blocked by trigger |
| `jobs` | Postgres queue (`FOR UPDATE SKIP LOCKED`) |

Citation shape (used by every agent output):
`{document_id, item_id?, clause_ref?, char_start, char_end, quote}` — validated by code: the quote must be found in the cited source, otherwise the claim is downgraded to low confidence.

## 3. Phase 1 plan (Core + Notice agent)

1. Schema + migration, auth (email/password JWT), orgs/projects.
2. Ingestion: upload API → extract text (pdf → pdftotext/pypdf, OCR fallback via tesseract; docx; xlsx; eml/msg; WhatsApp .txt; images → OCR) → immutable `documents` + split `items` + `chunks` with local embeddings.
3. Contract model: clause splitter, LLM rule extraction (prompt `prompts/contract_extraction/extract_rules.v1.md`, schema-validated) → `proposed` rules → approval UI. Only `approved` rules are used by agents.
4. Deadline engine: pure Python, unit-tested (weekends, IE/UK holidays, shutdowns, calendar vs working days, roll-forward, month ends, leap years).
5. Notice agent: item → classify (change/delay/instruction/disruption/noise) with evidence quotes → link to approved rule(s) → code computes deadline → draft notice in the contract's language → review item with citations + confidence.
6. Review queue UI: filters, side-by-side source passage, edit/approve/dismiss, DOCX/PDF export of approved drafts.
7. Audit log + project log everywhere.
8. Synthetic Riverside Apartments project + seed script; eval harness.

**LLM providers.** `ClaudeProvider` (Anthropic SDK, structured outputs validated against Pydantic schemas) is used when `ANTHROPIC_API_KEY` is set. Otherwise `OfflineProvider` (deterministic rules/templates) runs so the system, tests and eval work without network; the UI shows which provider produced each output.

Phases 2–4 add agents as new packages under `notice/agents/` using the same base contract, tools and review queue.
