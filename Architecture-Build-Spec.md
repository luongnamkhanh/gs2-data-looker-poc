# The AI Foundation Build Spec

> **What this is.** The reproducible implementation companion to
> `docs/Architecture-Bible.md`. The bible is the *map* (what the system is and why).
> This is the *buildable detail*: the verbatim prompts, the full configuration surface,
> the table DDL, the skill I/O contracts, the frontend contract, and the from-zero
> stand-up sequence. Read alongside the repo: this spec quotes the load-bearing strings
> and schemas and points at `path:line` for everything else.
>
> **Reproducibility claim.** A fresh engineer (or a fresh Claude) with this spec **and the
> repo** can reproduce the agent close to 1:1. With this spec but **without the repo**, you
> can rebuild the same architecture and behavior; you will still re-derive the helper code
> and must supply your own infrastructure and data.
>
> **What this spec deliberately does NOT contain** (and why): real secrets / GUIDs / hosts
> (masked as `<PLACEHOLDER>`; they live in `bundles/shared/variables.yml` and the Databricks
> workspace), and the domain data itself (the 191 models, 170 documents, 840-entity
> glossary). Those are environment- and tenant-specific by design.
>
> As-built 2026-06-23. PII-safe and secret-safe. ASCII hyphens only.

---

## Table of contents

1. [Reproduce checklist](#1-reproduce-checklist)
2. [Configuration surface](#2-configuration-surface)
3. [The prompts (verbatim)](#3-the-prompts-verbatim)
4. [Skill I/O contracts](#4-skill-io-contracts)
5. [Persistent data model (DDL)](#5-persistent-data-model-ddl)
6. [Frontend and SSE contract](#6-frontend-and-sse-contract)
7. [Stand-up sequence (from zero)](#7-stand-up-sequence-from-zero)
8. [Residual gaps](#8-residual-gaps)

---

## 1. Reproduce checklist

To stand up an instance you need:

- **Three Databricks workspaces** (or fewer, collapsing roles): an admin workspace (PII
  profiling), an analytics workspace "DAS" (the factory + embedding build), and a
  business-unit workspace "BU" (the app + Vector Search indices). One DAB bundle per
  workspace (`bundles/factory`, `bundles/app`, `bundles/cost`).
- **Three in-tenant model-serving endpoints**: a chat model (`databricks-claude-sonnet-4-6`
  for the agent; `databricks-claude-opus-4-8` for factory enrichment) and an embedding model
  (`databricks-qwen3-embedding-0-6b`). All in-tenant (PDPL / AI Law 134/2025).
- **A SQL warehouse** in the BU workspace for text-to-SQL.
- **Upstream PII profiling** that produces `prod_mgmt.nedp_mgmt.pii_tag_profile` (+ the
  rule/AI tag tables) for the catalogs you want to expose.
- **Unity Catalog grants**: the app service principal needs read on the exposed mart
  catalogs; per-user masking for the gated scope relies on UC dynamic views + an OBO
  user token.

The exact build commands are in Section 7.

---

## 2. Configuration surface

The single config module is `app/agent/core/config.py`. Every value below has a sensible
default and an environment override; in production the app injects `WAREHOUSE_ID` from the
bound `sql_warehouse` resource and `MART_BRAIN=1` from `app.yaml`.

### 2.1 Core config (`app/agent/core/config.py`)

| Name | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `HOST` | `DBX_HOST` | `<BU_HOST>` | Workspace host the app SDK targets |
| `WAREHOUSE_ID` | `WAREHOUSE_ID` | `<BU_WAREHOUSE_ID>` | SQL warehouse for text-to-SQL (prod: injected from app resource) |
| `LLM_ENDPOINT` | `LLM_ENDPOINT` | `databricks-claude-sonnet-4-6` | Agent chat / tool-calling endpoint |
| `EMBED_ENDPOINT` | `EMBED_ENDPOINT` | `databricks-qwen3-embedding-0-6b` | Embedding endpoint (matches the VS indices) |
| `SCOPE_INDICES` | - | see 2.2 | Per-scope retrieval index list |
| `SCOPE_CATALOGS` | - | see 2.2 | Per-scope SQL catalog universe |
| `ROUTE_C_CATALOGS` | - | `(prod_insight_financial, prod_cur, prod_std)` | Default mart SQL universe |
| `GRAPH_TABLE` | - | `prod_mgmt.ai.smdl_unstructured_relationship` | Doc knowledge-graph edges (system_graph) |
| `DOC_TABLE` | - | `prod_mgmt.ai.smdl_unstructured` | Doc records (doc_lookup, read_document) |
| `MODEL_TABLE` | - | `prod_mgmt.ai.smdl_structured` | Structured SMDL contract |
| `CHUNK_STRUCTURED` | - | `prod_mgmt.ai.chunk_structured` | Structured chunks (view) |
| `CHUNK_UNSTRUCTURED` | - | `prod_mgmt.ai.chunk_unstructured` | Doc chunks |
| `MEMORY_TABLE` | - | `prod_mgmt.ai.app_query_memory` | Verified-SQL semantic memory |
| `HISTORY_TABLE` | - | `prod_mgmt.ai.app_chat_history` | Server-side chat history |
| `USAGE_TABLE` | - | `prod_mgmt.ai.agent_usage` | Per-scope cost metering |
| `DOC_VOLUME_BASE` | `DOC_VOLUME_BASE` | `/Volumes/.../TCP Registration - Documents` | UC Volume base for read_document |
| `READ_DOC_MAX_CHARS` | `READ_DOC_MAX_CHARS` | `20000` | Cap on bytes read from a Volume file |
| `MEM_MIN_SIM` | `MEM_MIN_SIM` | `0.92` | Cosine recall-hit threshold |
| `MEM_MARGIN` | `MEM_MARGIN` | `0.02` | Ambiguity margin vs a different cached SQL |
| `HISTORY_MAX_SESSIONS` | `HISTORY_MAX_SESSIONS` | `30` | Sessions retained per user |
| `RBDBB_GROUPS` | `RBDBB_GROUPS` | `{nedp_bu_db, nedp_admin}` | Groups allowed to select the rbdbb scope |
| `ROW_LIMIT` | `ROW_LIMIT` | `1000` | Mandatory LIMIT clamp on every executed SELECT |
| `ABSTAIN_SCORE` | `ABSTAIN_SCORE` | `0.55` | Docs retrieval abstain threshold |
| `CONTEXT_TURNS` | `CONTEXT_TURNS` | `4` | Conversation turns carried as context |
| `MART_BRAIN` | `MART_BRAIN` | `1` (on) | Agentic mart path vs deterministic single-SELECT fallback |
| `MART_ITERS` / `MART_CALLS` / `MART_SECONDS` | same names | `5` / `6` / `90` | Mart-brain budgets |

Caps defined outside config.py: `TABLE_ROWS_MAX=50`, `RAW_ROWS_MAX=100`
(`answers/__init__.py:6-7`); `COLUMN_LIST_CAP=60` (`chunk_smdl.py:10`); docs-brain
`MAX_ITERATIONS=8` / `MAX_TOOL_CALLS=10` / `MAX_SECONDS=120` / `_TOOL_RESULT_CHARS=8000`
(`brain.py:14-17`). Deep mode (`agent.py`): docs brain `(12, 16, 180)` and k `6 -> 12`;
mart brain `(8, 10, 150)`; deterministic retrieval `(k_struct, k_unstruct)` `(10, 5) -> (20, 12)`,
SQL retries `2 -> 3`. The docs-brain budgets are intentionally code constants, not env
config; only the mart-brain budgets are env-overridable.

### 2.2 Scope maps

`SCOPE_INDICES` (`config.py:14-18`):

```
mart  -> [prod_mgmt.ai.smdl_fs_index, prod_mgmt.ai.smdl_shared_index]
docs  -> [prod_mgmt.ai.smdl_unstructured_index]
rbdbb -> [prod_mgmt.ai.smdl_dec_index, prod_mgmt.ai.smdl_shared_index]
```

`SCOPE_CATALOGS` (`config.py:40-45`):

```
mart  -> (prod_insight_financial, prod_cur, prod_std)
rbdbb -> (prod_v_ext_decdc, prod_cur, prod_std)
```

Catalog -> scope, used by the chunk builder (`scripts/embedding/lib/scope_map.py:9-17`):

```
prod_v_ext_decdc       -> dec
prod_insight_financial -> fs
prod_cur / prod_std    -> shared   (queried alongside every scope)
(default)              -> shared
```

UI scope ids: `mart`, `rbdbb` (gated), `tcp`, `brd`, `vib`. `mart`/`rbdbb` route to the
text-to-SQL path; `tcp`/`brd`/`vib` route to the docs Brain.

### 2.3 Access gating (`app/agent/core/authz.py`)

`BASE_SCOPES = {mart, tcp, brd, vib}` are always granted. `allowed_scopes(user_token)`:
with no token it returns `BASE_SCOPES` only; otherwise it calls `current_user.me()` through
an OBO `WorkspaceClient(host, token, auth_type="pat")`, collects the caller's group display
names, and adds `rbdbb` iff those groups intersect `RBDBB_GROUPS`. It is **fail-closed**
(any exception resets to `BASE_SCOPES`, never raises) and cached for `_TTL = 300.0` seconds
keyed by `hash(user_token)`. The execution-side `run_sql_as_user` (`core/llm.py:74-86`)
also fail-closes: no token -> `PermissionError`.

### 2.4 DAB variables (`bundles/shared/variables.yml`, masked)

| Variable | Configures |
| --- | --- |
| `service_principal` = `<SERVICE_PRINCIPAL_ID>` | The SP both bundles `run_as` in prod |
| `cluster_id` = `<DAS_CLUSTER_ID>` | prod-shared-das cluster (factory + chunk build) |
| `bu_cluster_id` = `<BU_CLUSTER_ID>` | prod-shared-bu cluster (index sync; no serverless) |
| `bu_warehouse_id` = `<BU_WAREHOUSE_ID>` | prod-sql-bu warehouse (the app's text-to-SQL) |

---

## 3. The prompts (verbatim)

The prompts are the highest-value, least-reproducible part of the system. All result rows
are PII-masked (`mask_rows`) before any prompt below sees them; no PII or secrets appear in
any template.

### 3.1 The soul and how it renders (`app/agent/soul/`)

The whole system prompt is one file `soul.md`, read once at import (never hot-reloaded, an
anti-injection measure; editing it requires bumping `soul.sha256` in `manifest.yaml`).
`render(scope)` extracts the bullet block under a per-scope heading inside `## Identity`:

```
_SCOPE_HEADINGS = {"docs": "### Documents scope",
                   "mart": "### Data marts scope",
                   "rbdbb": "### RB DBB mart scope"}
```

`brain.py` uses `render("docs")`; the mart-brain uses `render("mart")` / `render("rbdbb")`.
The `## Won't-do` refusal contract lower in `soul.md` is NOT injected into the model prompt;
it is enforced by code (the `[shield: ...]` annotations) and the red-team tests.

#### 3.1a Documents scope prompt (`soul.md:16-29`)

```
You are VIB Assistant operating in the DOCUMENTS scope (TCP system documentation of Vietnam International Bank).
Work as Plan -> Act (call tools) -> Observe; repeat until you can answer, then answer.
Rules:
- OPEN the final answer with the direct answer to the question (a number, yes/no, or a short list) before any detail.
- Answer in the same language as the question (Vietnamese question -> Vietnamese with full diacritics).
- Ground every claim in tool results. If tools return nothing relevant, say so plainly - never invent systems, relations or documents.
- For questions about relations BETWEEN systems (integrates / depends / monitors / impact / count / negation), prefer the system_graph tool.
- SOURCE ORDER: the curated semantic layer is primary. ALWAYS consult it first (search_docs for content, system_graph for system relationships) - it is reviewed, PII-safe, and links facts across documents. Use read_document only to SUPPLEMENT a specific detail the semantic layer lacks (exact figures, a full section/table), never as your first or only source. Build the answer's backbone from the semantic layer and fold in read_document detail; do not answer from one raw file alone. When the question asks for SPECIFIC facts the snippets do not contain (exact figures, rules, ports/IP ranges, a full list or table, named configs), you MUST call read_document(focus=...) to fetch them before answering - do NOT reply that the detail is unavailable when the file would have it.
- No markdown decorations (##, **).
- FOLLOW-UP questions: build on the conversation so far - reuse facts already established in previous answers and go DEEPER, do not restart from zero; verify with tools anything you are not sure about.
- Narrate your planning and tool use in ENGLISH (short phrases - these are system thinking steps). Write the FINAL ANSWER in the same language as the question.
- Rich answers get STRUCTURE: numbered section headings on their own line ending with ':' (e.g. '1. Gioi thieu chung:'), '- ' bullets for lists, one blank line between sections. Short answers stay short - no padding.
- NEVER paste raw URLs into the answer; refer to documents by name only - sources appear as clickable cards under the answer.
- Do NOT ask the user questions inside the answer. Instead, AFTER the answer, return ONE JSON object {"chips":["..."],"sources":["..."]}. chips: 2-3 COMPLETE, STANDALONE follow-up questions in the question's language that DRILL DEEPER into specific details of THIS answer (mechanisms, configurations, subsections) - never generic neighboring topics. sources: the exact titles of the documents you ACTUALLY used to answer - only those, not everything the search returned.
```

#### 3.1b Data marts scope prompt (`soul.md:33-46`)

```
You are VIB Assistant operating in the DATA MARTS scope (text-to-SQL over VIB's curated financial marts: prod_insight_financial, prod_cur, prod_std).
Work as Plan -> Act (call tools) -> Observe; repeat until you can answer, then answer.
Rules:
- FIRST call recall_sql with the question - if it returns a verified SQL, you may use its result directly.
- On a miss, call fetch_schema to get exact table/column names, then write EXACTLY ONE Databricks SQL SELECT per run_sql call using ONLY tables/columns from the schema. Never invent names.
- run_sql executes one guarded SELECT (SELECT-only, a row LIMIT is enforced). If it returns an error, fix the SQL using the named columns and try again.
- For a multi-part question, decompose it: run one SELECT per part, then combine the numbers in your answer. Do not force everything into one query.
- The LAST run_sql you call MUST be the single query that produces the answer the user sees (its result becomes the displayed table and chart). Run any helper lookup (finding the latest period, resolving a code to its label) BEFORE that final query, never after. Select ONLY the columns the question asks for; do not add a grouping column when the filter already pins it to one value.
- Answer in the same language as the question (Vietnamese question -> Vietnamese with full diacritics).
- Ground every number ONLY in rows returned by run_sql. Never invent numbers. If no query succeeds, say so plainly.
- For a why / root-cause question, attribute the change ONLY to figures you actually returned from run_sql (the breakdown that moved, the periods you compared). If the returned rows do not explain the cause, say so plainly and name what further breakdown would be needed; never attribute the cause to numbers or periods you did not query.
- Only ask a clarification when the question is too vague to pick a sensible default (no metric, no period, several candidate tables).
- Write the final answer as a 3-layer analysis, each label EXACTLY ONCE on its own line: Vietnamese -> 'Bối cảnh:' / 'Insight:' / 'Gợi ý hành động:'; English -> 'Context:' / 'Insight:' / 'Action:'. Bối cảnh: one sentence. Insight: 3-6 short '- ' bullets, one fact each, lead with the number. Gợi ý hành động: one sentence. No markdown (##, **).
- AFTER the answer, return ONE JSON object {"chips":["..."]}: 2-3 COMPLETE, STANDALONE follow-up questions in the question's language, each naming metric + period + dimension.
```

#### 3.1c RB DBB mart scope prompt (`soul.md:50-64`)

Identical in shape to 3.1b but pinned to catalogs `prod_v_ext_decdc, prod_cur, prod_std`
and with the extra rule line: `Use ONLY tables in these catalogs: prod_v_ext_decdc, prod_cur, prod_std.`

### 3.2 The 3-layer narrative prompt (`skills/analytics_sql.py:142-158`)

Used on the deterministic mart path (the mart-brain writes the narrative directly under the
soul). `{question}` is the resolved question; `{sample}` is `rows[:50]` as JSON.

```
You are a VIB data analyst. Based ONLY on the query RESULT below, write a short analysis in THE SAME LANGUAGE as the question. Use EXACTLY THREE labeled sections, each label EXACTLY ONCE, each on its own line - pick ONE label set by the question's language and NEVER mix sets:
English question -> 'Context:' / 'Insight:' / 'Action:'
Vietnamese question -> 'Bối cảnh:' / 'Insight:' / 'Gợi ý hành động:'
Context: one sentence. Insight: 3-6 SHORT '- ' bullets, ONE fact per bullet, lead with the number (e.g. '- Q4 38.69T, +5.5% vs Q3') - no run-on sentences. Action: one sentence; do NOT repeat it under another label.
No markdown (##, **). NEVER invent numbers that are not in the result. Then return follow-up suggestions as JSON {"chips":["...","..."]}: 2-3 COMPLETE, STANDALONE questions in the question's language, each naming the metric + period + dimension so it can be asked without prior context (no fragments like 'By quarter?').

Question: {question}
Result: {sample}
```

Deep-mode addendum (`analytics_sql.py:191-192`, appended when deep):

```
Go DEEPER: add cross-group comparisons, rate of change between periods, and anomalies (if any) - still ONLY from the given figures.
```

### 3.3 The SQL-generation prompt (deterministic mart path, `analytics_sql.py:62-66`)

`{cats}` defaults to `prod_insight_financial, prod_cur, prod_std`; `{ctx}` is the joined
retrieved schema chunks.

```
Write EXACTLY ONE Databricks SQL SELECT that answers the business question. Use ONLY tables in these catalogs: {cats}. Use the exact table/column names from the CONTEXT below. No explanations, no markdown, SQL only.

CONTEXT (semantic layer):
{ctx}

Question: {question}
```

Retry suffixes appended on failure (`analytics_sql.py:132-137`):

```
Your previous reply was NOT a SELECT statement. Return EXACTLY ONE Databricks SQL SELECT using only tables/columns from the CONTEXT.
```
```
The previous SQL FAILED with: {e}
Fix it using ONLY table/column names present in the CONTEXT. SQL only.
```

### 3.4 The follow-up contextualize prompt (`analytics_sql.py:35-42`)

```
Rewrite the user's FOLLOW-UP into a single, self-contained question that can be understood with NO prior context. Resolve pronouns and elliptical references (e.g. 'that quarter', 'con quy truoc', 'theo san pham') using the conversation. KEEP the original language and the exact metric / period / dimension wording. If the follow-up is ALREADY self-contained, return it unchanged. Output ONLY the rewritten question, nothing else.

CONVERSATION:
{turns}

FOLLOW-UP: {question}
```

### 3.5 The store-gate prompt (`agent.py:51-58`)

Runs in a background thread before a verified SQL is cached; `max_tokens=5`, only a
`YES`-prefixed verdict stores (fail-closed).

```
You are reviewing a SQL query before it is cached and replayed for similar questions.
Question: {question}
SQL: {sql}
Does the SQL FULLY answer the question's intent - right metric, right time grain (incl. comparisons like growth/vs-prior-period if asked), right dimensions? Reply EXACTLY YES or NO.
```

### 3.6 Deep-mode self-check prompts

Mart figure self-check (`analytics_sql.py:167-174`), applied to masked rows on both mart
paths in deep mode:

```
Re-check the ANALYSIS below against the query RESULT. Every figure in the analysis MUST be supported by the result rows. Rescaling units is allowed (e.g. raw VND shown as 'tỷ' / 'T') as long as the magnitude matches - but DROP or CORRECT any number not derivable from the rows, and fix wrong unit scaling. Keep the EXACT same section labels and structure, keep the analysis's language (Vietnamese stays Vietnamese with full diacritics), no markdown. Return ONLY the corrected analysis - no follow-up chips JSON.

Question: {question}
Analysis: {narrative}
Result: {sample}
```

Docs claim self-check (`search_docs.py:43-51`), applied over accumulated tool evidence:

```
Check the ANSWER below against the source CONTEXT. Fix or drop every claim the context does not support; add important details from the context that the answer missed. Keep the structure and KEEP THE ANSWER'S LANGUAGE (Vietnamese stays Vietnamese with full diacritics). No markdown. Return only the final answer.

Question: {question}
Answer: {answer}
Context: {ctx}
```

### 3.7 The Brain loop scaffolding (`app/agent/brain.py`)

A hand-rolled OpenAI-style tool-calling loop, no framework. Message assembly
(`brain.py:45-51`): one system message = the rendered soul + optional `system_extra` (the
deep addendum), then history replayed as alternating user/assistant turns, then the current
question. There is no preamble beyond the soul. Tool results are appended as
`role: "tool"` messages, JSON-serialized and truncated to `tool_result_chars`
(`brain.py:83-86`). Budget exhaustion returns `{"answer": ..., "error": "<...> budget exceeded", "tool_calls": [...]}`.

Docs deep addendum (`agent.py:132-136`, passed as `system_extra`):

```
- DEEP MODE: investigate from MULTIPLE angles before answering - combine search_docs and system_graph where relevant, cross-check facts across documents, surface concrete details (versions, SLA, ownership, integration direction) and say explicitly what the documents do NOT cover. Still ONLY from tool results.
```

The docs Brain also has a safety-net supplement prompt (`agent.py:82-89`) used when the
answer admits a gap but no source file was read: it auto-reads the dominant document and
re-answers, keeping the backbone and adding the excerpt's specific details.

### 3.8 The system_graph NL-to-SQL prompt (`system_graph.py:85-130`)

Generates one SELECT over `GRAPH_TABLE` (columns `rel_id, rel_name, doc_id, doc_key,
doc_title, model_a, model_b, type, ...`). It injects the valid `type` values and the real
node-name variants matched from the question, and (for negation questions) a set-difference
template so "which systems do NOT integrate with X" never returns the whole table. Quoted in
full in the research notes; see the file for the exact text.

### 3.9 The eval judge prompt (`eval/agent/lib/judge.py:26-39`)

`RUBRIC = ("faithfulness", "relevance", "completeness")`; the gate axis is `faithfulness`;
fail-closed (all-False) on bad JSON. Fed only `(question, rows, answer)`, in-tenant.

```
You are a strict evaluator for a Vietnamese bank chatbot (VIB). You are given a QUESTION, the CONTEXT rows the agent used, and the agent's ANSWER. Judge the answer on exactly three binary criteria:
1. faithfulness  - every number, name, and claim in ANSWER appears in CONTEXT (no invented figures)
2. relevance     - ANSWER directly addresses QUESTION
3. completeness  - ANSWER covers the main information QUESTION expects given CONTEXT

Return ONLY a JSON object with keys: faithfulness (bool), relevance (bool), completeness (bool), reason (string). No markdown fences, no extra text.

QUESTION: {question}

CONTEXT (rows returned to the user):
{rows_text}

ANSWER:
{answer}
```

---

## 4. Skill I/O contracts

The single registry is `app/agent/skills/__init__.py`. Every skill descriptor must carry
all of `_REQUIRED = (name, description, input_schema, scope, invoker, min_role,
requires_human_approval, audit_action_type)`; `register()` raises `SkillError` if any field
or the `scope{reads, writes}` block is missing. `invoke(name, **kwargs)` normalizes every
result and exception to `{ok, code, message}` with exactly three error codes:
`unknown_skill`, `guard_refused` (a `GuardError` from sqlguard), `skill_error` (any other
exception, or a returned dict with a truthy `error`). `tool_schema(name)` projects a
descriptor into the OpenAI function schema the brain binds.

Eight registered skills. `recall_sql` / `fetch_schema` / `run_sql` are descriptor-only
entries whose runtime executors live in `skills/mart_brain.py`.

| Skill | input_schema | reads | returns (success) | path |
| --- | --- | --- | --- | --- |
| `search_docs` | `{query}` | docs index + `DOC_TABLE` | `{abstain: false, answer, hits[]}` or `{abstain: true}` | docs brain |
| `system_graph` | `{question}` | `GRAPH_TABLE`, `DOC_TABLE` | `{sql, columns, rows}` | docs brain |
| `doc_lookup` | `{name}` | `DOC_TABLE` | bare list -> `{ok, rows[]}` (`id, doc_key, title, current_version, filename, source_url`); SQL is hand-built with `LIMIT 20`, NOT sqlguard-wrapped | docs brain |
| `read_document` | `{name, focus?}` | `DOC_TABLE`, `DOC_VOLUME_BASE` | `{doc, type, text, filename, source_url, chars, truncated}` (xlsx/text) | docs brain |
| `analytics_sql` | `{question}` | mart indices, `CHUNK_STRUCTURED`, route-C catalogs | `{clarify}` or `{sql, columns, rows}` or `{error, sql}` | deterministic mart (MART_BRAIN=0) |
| `recall_sql` | `{question}` | `MEMORY_TABLE` + catalogs | `{hit: false}` or `{hit: true, sql, sim, columns, rows}` | mart brain |
| `fetch_schema` | `{question}` | mart indices, `CHUNK_STRUCTURED` | `{context: [schema texts]}` | mart brain |
| `run_sql` | `{sql}` | route-C catalogs | `{sql, columns, rows}` or `{error}`; invoker is `run_sql(sqlguard_guard(sql, ROW_LIMIT))` | mart brain |

All carry `min_role: user`, `requires_human_approval: false`. `audit_action_type` is pinned
metadata (e.g. `agent_run_sql`), not yet runtime-enforced. The runtime executors mask rows
and cap them at 30 rows to the model (`mart_brain.py`).

**Retrieval helper `build_context`** (`analytics_sql.py:69-100`), used by both `analytics_sql`
and `fetch_schema`: per mart index, `vector_search(ix, question, k=10)` then `merge_hits(k=10)`
(dedup by `chunk_id` keeping max score). For each hit, a `table` chunk contributes its id;
any other chunk contributes its `parent_id` (the parent table chunk) plus its own column
text. The top 8 distinct table ids are fetched in full from `CHUNK_STRUCTURED`
(`chunk_type='table'`), re-sorted to relevance order, and returned as full table schemas
first, then up to 6 column chunks. This is the column-chunk -> parent-table expansion that
keeps the model from inventing column names.

---

## 5. Persistent data model (DDL)

All application tables live in `prod_mgmt.ai`; the upstream PII tables in
`prod_mgmt.nedp_mgmt`. The authoritative contract DDLs for the two assembled SMDLs are owned
by `scripts/lib/load_to_delta.py`; assemble jobs call it then `ALTER ADD COLUMNS` for newer
fields.

### 5.1 Upstream (read-only): `prod_mgmt.nedp_mgmt.*`

- `pii_tag_profile` - per-column profile: `catalog_name, schema_name, table_name,
  column_name, data_type, ordinal_position, rows_sampled, distinct_in_sample, samples,
  non_null_count, is_deleted`. Key `(catalog, schema, table, column)`.
- `pii_tag_rule_based`, `pii_tag_ai` - PII tags: `catalog_name, schema_name, table_name,
  column_name, pii_type, confidence` (one tag/column by max confidence).

### 5.2 Factory outputs (structured)

```sql
-- smdl_scaffold  (merge key: fqn, column_name)
fqn STRING, catalog_name STRING, schema_name STRING, table_name STRING, column_name STRING,
ordinal INT, type STRING, pii_type STRING, pii_source STRING, sensitive BOOLEAN,
value_dictionary ARRAY<STRING>, already_verified BOOLEAN, scope_tag STRING, scaffolded_ts TIMESTAMP

-- smdl_enrichment  (merge key: fqn, column_name; + quality_score DOUBLE, flags ARRAY<STRING> from score.py)
fqn STRING, column_name STRING, description STRING,
synonyms ARRAY<STRUCT<term:STRING,lang:STRING,status:STRING>>,
value_meanings MAP<STRING,STRING>, value_meanings_status STRING,
cdm_concept STRUCT<term:STRING,module:STRING>,
status STRING, model STRING, enriched_ts TIMESTAMP, source STRING

-- smdl_metric  (merge key: fqn, metric_name)
fqn STRING, metric_name STRING, type STRING, sql STRING, filter STRING,
status STRING, model STRING, enriched_ts TIMESTAMP, source STRING

-- smdl_model_enrichment  (merge key: fqn)
fqn STRING, description STRING, grain STRING, table_type STRING,
status STRING, model STRING, enriched_ts TIMESTAMP, source STRING

-- smdl_structured_relationship  (merge key: rel_name)
rel_name STRING, model_a STRING, model_b STRING, join_type STRING, rel_type STRING,
condition STRING, confidence DOUBLE, status STRING, ingested_ts TIMESTAMP, smdl_version STRING, scope STRING

-- smdl_structured  (the assembled contract, merge key: fqn; DDL owned by load_to_delta.py)
fqn STRING, model_name STRING, catalog STRING, schema_name STRING, table_name STRING,
domain STRING, description STRING, grain STRING, table_type STRING, scope STRING,
columns ARRAY<STRUCT<name,type,description,pii_type,sensitive,value_dictionary:ARRAY<STRING>,
  value_meanings:MAP<STRING,STRING>,value_meanings_status,cdm_concept:STRUCT<term,module>>>,
synonyms ARRAY<STRUCT<term,lang,target,status>>,
metrics ARRAY<STRUCT<name,type,sql,filter,status>>,
relationships ARRAY<STRUCT<name,model_a,model_b,join_type,rel_type,condition,confidence:DOUBLE,status>>,
lineage STRUCT<upstream_tables:ARRAY<STRING>,source_catalogs:ARRAY<STRING>,source:STRING>,
masked BOOLEAN, raw_json STRING, content_hash STRING, ingested_ts TIMESTAMP, smdl_version STRING
```

### 5.3 Factory outputs (unstructured + golden)

```sql
-- smdl_doc_text (U1, overwrite), smdl_doc_version (U2, overwrite), smdl_doc_semantic (U3, merge key id),
-- smdl_doc_audited (U4, overwrite) are staging; the published contract is:

-- smdl_unstructured  (merge key: id; DDL owned by load_to_delta.py; + source STRING)
id STRING, doc_key STRING, title STRING, type STRING, doc_type STRING, domain STRING,
brief STRING, comment STRING, tags ARRAY<STRING>, current_version STRING,
versions ARRAY<STRUCT<version,filename,path,source_url,type,size_bytes:BIGINT,is_current:BOOLEAN,qualifier>>,
entities ARRAY<STRUCT<name,kind,vendor,domain,description>>,
relationships ARRAY<STRUCT<name,model_a,model_b,type,description>>,
masked BOOLEAN, raw_json STRING, content_hash STRING, ingested_ts TIMESTAMP, smdl_version STRING

-- smdl_unstructured_relationship  (merge key: rel_id) - flattened graph edges for system_graph
rel_id STRING, rel_name STRING, doc_id STRING, doc_key STRING, doc_title STRING,
model_a STRING, model_b STRING, type STRING, description STRING, domain STRING, ingested_ts TIMESTAMP, smdl_version STRING

-- smdl_golden_entity  (overwrite) - the curated glossary
id STRING, name_en STRING, name_vi STRING, definition STRING, module STRING,
synonyms ARRAY<STRUCT<term,lang>>, status STRING, provenance STRING, source_ref STRING

-- smdl_golden_column_map  (upsert key: fqn, column_name) - column -> entity match (auto >= 0.85)
fqn STRING, column_name STRING, entity_id STRING, score DOUBLE, match_status STRING, matched_ts TIMESTAMP
```

### 5.4 Embedding chunk tables and indices

All chunk tables share one schema `CHUNK_FIELDS` (`chunk_smdl.py:12-16`), merge key
`chunk_id`, CDF on:

```sql
chunk_id STRING NOT NULL, parent_id STRING, layer STRING, source_id STRING,
chunk_type STRING, ref STRING, text STRING, domain STRING, status STRING,
sensitivity STRING, source_tag STRING, source_url STRING, content_hash STRING, smdl_version STRING
```

Physical tables: `chunk_fs`, `chunk_dec`, `chunk_shared` (the per-scope structured split),
`chunk_unstructured` (docs). `chunk_structured` is a VIEW = `chunk_fs UNION ALL chunk_dec
UNION ALL chunk_shared`. Four DELTA_SYNC Vector Search indices on endpoint
`smdl_vs_endpoint`, each `primary_key=chunk_id`, `embedding_source_column=text`,
`embedding_model_endpoint_name=databricks-qwen3-embedding-0-6b`, `pipeline_type=TRIGGERED`:
`chunk_fs -> smdl_fs_index`, `chunk_dec -> smdl_dec_index`, `chunk_shared -> smdl_shared_index`,
`chunk_unstructured -> smdl_unstructured_index`.

### 5.5 App runtime tables

```sql
-- agent_usage  (INSERT-only; DDL duplicated in app/agent/core/usage.py and scripts/lib/usage.py - keep in sync)
ts TIMESTAMP, scope STRING, cost_center STRING, call_type STRING, model_endpoint STRING,
index_name STRING, input_tokens BIGINT, output_tokens BIGINT, request_id STRING, source STRING

-- app_chat_history  (merge key: session_id, user_email; provisioned out-of-band - schema inferred from DML)
session_id STRING, user_email STRING, title STRING, scope STRING, turns STRING (JSON),
turn_count INT, created_ts TIMESTAMP, updated_ts TIMESTAMP

-- app_query_memory  (key id; dedup on scope+lower(trim(question)); provisioned out-of-band)
id STRING, scope STRING, question STRING (PII-masked), question_embedding ARRAY<FLOAT>,
sql_text STRING, ref_tables ARRAY<STRING>, verified_by STRING, hit_count BIGINT,
last_used_ts TIMESTAMP, created_ts TIMESTAMP, is_active BOOLEAN
```

> Two reproduction notes: (1) the `agent_usage` DDL exists in two files that must stay
> identical; (2) `app_chat_history` and `app_query_memory` have no DDL in the repo and are
> provisioned out-of-band - create them from the inferred schemas above before first run.

---

## 6. Frontend and SSE contract

The contract is `app/ui/src/types.ts` (canonical) mirrored by `app/agent/answers/__init__.py`.

### 6.1 Types (`app/ui/src/types.ts`, verbatim)

```typescript
export type ThinkStep =
  | { kind: "txt"; html: string }
  | { kind: "tool"; name: string; json: string[] };

export interface GraphData { center: string; adjacency: Record<string, { n: string; t: string; d: "in" | "out" }[]>; }
export interface ChartSpec { type: string; x?: string; y?: string; orient?: string; value_col?: string; title?: string; }
export interface SourceCard { snippet: string; refs: number; title?: string; url?: string; }

export interface DataAnswer {
  kind: "data"; badge: string; intro: string;
  table: { columns: string[]; rows: (string | number)[][]; rightAlign: number[] };
  sql: string; raw: { columns: string[]; rows: (string | number)[][] };
  followups: string[]; meta: string[]; chart?: ChartSpec | null; memoryId?: string | null;
}
export interface DocAnswer {
  kind: "doc"; badge: string; intro: string; graph: GraphData; sources: SourceCard[];
  followups: string[]; meta: string[]; sql?: string; raw?: { columns: string[]; rows: (string | number)[][] };
}
export interface TextAnswer {
  kind: "text"; badge: string; intro: string; links?: { label: string; url: string }[];
  citations?: string[]; sources?: SourceCard[]; followups: string[]; meta: string[];
}
export type Answer = DataAnswer | DocAnswer | TextAnswer;
export type ChatEvent =
  | { type: "step"; step: ThinkStep }
  | { type: "answer"; answer: Answer }
  | { type: "done"; elapsedMs: number };
```

### 6.2 Server wire format (`app/server.py`)

- `_sse(payload)` -> `data: {json}\n\n` over `text/event-stream`. Three event types: `step`
  (txt/tool), `answer`, terminal `done` with `elapsedMs`. The agent runs in a worker thread;
  the SSE generator drains an `asyncio.Queue`.
- `POST /api/chat` body: `{q, scopes[], deep, graph, history[]}`. If `rbdbb` is requested but
  not in `authz.allowed_scopes(token)`, the stream returns a denial text answer instead of
  running the agent.
- Identity from headers: `x-forwarded-preferred-username` -> `x-forwarded-email` ->
  `x-forwarded-user`; OBO token from `x-forwarded-access-token`.
- `GET /api/me` -> `{name, team, allowed_scopes}`. History: `GET /api/history`,
  `GET/PUT /api/history/{sid}`. `POST /api/memory/{mid}/deactivate` soft-deletes a cached SQL.
  The built React app is mounted last at `/` so `/api/*` matches first.

### 6.3 Answer assembly (`app/agent/answers/__init__.py`)

`_data_answer` formats a display table (cap 50 rows, numeric cells with thousands
separators, `rightAlign` = numeric column indices) plus a raw provenance table (cap 100).
`_text_answer` PII-masks `intro` at the output boundary. `_confidence_note` appends a warning
on 0 rows or when `len(rows) >= ROW_LIMIT` (truncation). `_clean_narrative` strips the chips
JSON and markdown and forces each 3-layer label onto its own paragraph.

---

## 7. Stand-up sequence (from zero)

All `databricks bundle` commands carry `DATABRICKS_TF_VERSION=1.10.0` (baked into the `DBX`
make var). Defaults: `TARGET=prod`, DAS profile `prod_nedp_das_dg`, BU profile
`prod_nedp_bu_dg`.

1. **Upstream PII tagging (admin workspace).** Ensure the scope's source tables exist and
   are PII-tagged; otherwise every column resolves to `pending` -> sensitive -> no value
   dictionary.
2. **Profile:** `make profile CATALOG=<cat> SCHEMA=<sch>` -> runs `nedp_mgmt_pii_profile`
   (admin workspace, `incremental=false`), writing `prod_mgmt.nedp_mgmt.pii_tag_profile`.
3. **Codegen:** `make build` regenerates the job YAMLs from `workflow/<job>/template.yml`
   (the generated YAMLs are gitignored; never hand-edit). Optionally `make validate`.
4. **Deploy the DAS factory bundle:** `make deploy` -> `bundle deploy -t prod` in
   `bundles/factory` (factory jobs + `smdl_build_chunks`).
5. **Structured factory:** `make factory CATALOG=<cat> SCHEMA=<sch>` -> runs `smdl_factory`
   (scaffold -> golden_match -> ai_enrich -> metric_enrich -> score -> discover_rel ->
   assemble), publishing `prod_mgmt.ai.smdl_structured`.
6. **Unstructured factory:** `make doc-factory [LIMIT=N]` -> runs `smdl_doc_factory`
   (extract -> group -> understand -> audit -> assemble), publishing
   `prod_mgmt.ai.smdl_unstructured`.
7. **Build chunks + sync indices:** run `smdl_build_chunks` (factory bundle) to write the
   chunk tables, then `smdl_index_sync` (app bundle, BU) to sync the four Vector Search
   indices. `smdl_index_sync` is also event-triggered on chunk-table updates.
8. **Build the app tree:** `make app-build` -> `scripts/build_dbx_app.sh` runs
   `VITE_USE_BACKEND=1 npm run build`, assembles `build/dbx_app/` (server.py + agent/ +
   static/), and writes `app.yaml` (start `python server.py`, `MART_BRAIN=1`, `WAREHOUSE_ID`
   from the `sql_warehouse` resource). The server listens on `0.0.0.0:$DATABRICKS_APP_PORT`.
9. **Deploy + start the app:** `make app-deploy PROFILE=prod_nedp_bu_dg` = app-build +
   `bundle deploy -t bu` (BU) + `bundle run smdl_assistant -t bu`. The app resource declares
   `user_api_scopes: [sql]` (OBO per-user masking) and binds the warehouse with `CAN_USE`.

Before first run, also create the two app tables that have no DDL in the repo
(`app_chat_history`, `app_query_memory`) from Section 5.5, and grant the app SP read on the
mart catalogs (+ UC dynamic views for the gated scope).

---

## 8. Residual gaps

Even with this spec, a docs-only rebuild will differ from the running system in these ways.
Each is intentional (environment- or tenant-specific) and is sourced from the repo or the
workspace, not this document:

- **Secrets and infra IDs** (`<SERVICE_PRINCIPAL_ID>`, cluster ids, warehouse id, hosts):
  in `bundles/shared/variables.yml` and the workspace. Never commit the real values.
- **Domain data**: the 191 structured models, 170 documents, and the 840-entity golden
  glossary are produced by running the factory over your own catalogs and authoring your own
  `semantic/golden/business_glossary.yml`. See the cloning chapter of the bible.
- **Helper code not quoted here**: `viz.pick_chart` heuristics, `pii_mask` regexes (Luhn +
  IIN), the codegen `generate_job.py`, the Wren `compile_mdl` curate regex, `merge_hits`,
  and the chunk-text templates. All are small and live in the repo at the cited paths.
- **Dependency versions and the test suites** (`app/tests/`, `eval/agent/`): clone from the
  repo. The eval harness encodes the known failure modes (aggregation grain, missing LIMIT,
  unit scaling) you will need to tune for a new domain.

With those four supplied from the repo and your tenant, this spec plus the bible is enough to
reproduce the agent close to 1:1.
