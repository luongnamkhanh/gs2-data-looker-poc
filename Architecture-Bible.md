# The AI Foundation Architecture Bible

> **What this is.** A single, faithful, as-built record of VIB's EDP "AI Foundation":
> the end-to-end system that turns a Lakehouse into a governed, PII-safe,
> semantic-search + text-to-SQL chatbot. It is written to be three things at once:
> a **reference** another team can read to understand the whole machine, a **pitch**
> you can present, and a **blueprint** ("bible") a sibling project can clone for a new
> business domain.
>
> **Status of this document.** As-built as of 2026-06-23. Every load-bearing claim is
> grounded in a source file and line (`path:line`). Where the older design prose in
> `CLAUDE.md` / `docs/Semantic-Modeling.md` diverges from the running code, this document
> follows the code and flags the delta (see Appendix C).
>
> **How to read it.** Chapters 1-2 are the executive picture and the design principles.
> Chapters 3-7 walk the pipeline in the order data flows: the two semantic models, the
> factory that builds them, the embedding/index layer, the agent, and the web app.
> Chapters 8-10 cover the cross-cutting concerns: governance, evaluation, deployment.
> Chapter 11 is the clone playbook. The appendices are a file map, a glossary, the
> as-built deltas, and the source citations.
>
> **Confidentiality.** This describes internal VIB architecture, data marts, and security
> material. Treat as confidential. No real PII, credentials, internal IPs, or account /
> card numbers appear here by design; the system is PII-safe by construction and so is
> this document.

---

## Table of contents

1. [Executive overview](#1-executive-overview)
2. [Problem and design principles](#2-problem-and-design-principles)
3. [The two semantic models (SMDL)](#3-the-two-semantic-models-smdl)
4. [The factory: building the SMDLs](#4-the-factory-building-the-smdls)
5. [Embedding and Vector Search](#5-embedding-and-vector-search)
6. [The agent](#6-the-agent)
7. [The web application](#7-the-web-application)
8. [Governance and security](#8-governance-and-security)
9. [Evaluation](#9-evaluation)
10. [Deployment topology](#10-deployment-topology)
11. [Cloning to a new business domain](#11-cloning-to-a-new-business-domain)
12. [Appendices](#12-appendices)

---

## 1. Executive overview

The AI Foundation is a semantic layer over the VIB Lakehouse plus a chatbot that answers
two distinct kinds of question against it:

- **"Show me the numbers"** (structured / text-to-SQL): "Tong du no the tin dung thang
  truoc theo phan khuc khach hang?" -> one governed `SELECT`, a chart, and a
  three-layer narrative.
- **"How does the system work / where is the document"** (unstructured / knowledge graph):
  "He thong nao gui du lieu cho EDP?" -> a graph or a set of source-cited document links.

It has four moving parts, in the order data flows:

```
 Upstream (admin workspace)        nedp_mgmt_pii_profile  ->  prod_mgmt.nedp_mgmt.pii_tag_profile
        |
 1. FACTORY (DAS workspace)        structured:  pii_tag_profile -> scaffold -> golden_match
    Databricks jobs, generated                 -> ai_enrich -> metric_enrich -> score
    from workflow/<job>/                        -> discover_rel -> assemble  ->  prod_mgmt.ai.smdl_structured
                                   unstructured: doc Volume -> extract -> group -> understand
                                                 -> audit -> assemble       ->  prod_mgmt.ai.smdl_unstructured
        |
 2. SEMANTIC MODELS (Git)          semantic/structured/*.yml  (191 Wren models + relationships + kb)
    version-tracked, PII-safe      semantic/unstructured/semantic_model.yml  (170 logical docs)
        |
 3. EMBEDDING (DAS, prod)          scripts/embedding/ chunks both SMDLs -> 4 Vector Search indices
                                   (fs, dec, shared, unstructured) on one Qwen3 endpoint
        |
 4. AGENT + WEB APP (BU workspace) FastAPI + SSE backend (app/) -> React UI (app/ui/)
    Databricks App                 scope dropdown = route; mart -> text-to-SQL, docs -> knowledge graph
```

**The one-sentence architecture.** Two Git-reviewable semantic models are built by a
deterministic-then-LLM factory, chunked and embedded into Vector Search, and served by a
scope-routed agent whose every SQL statement passes an AST guard and whose every LLM and
persistence boundary passes a PII mask, all inside the VIB tenant.

**Headline as-built numbers** (2026-06-23):

| Metric | Value | Source |
| --- | --- | --- |
| Structured Wren models | 191 YAMLs across 3 catalogs (`prod_insight_financial`, `prod_cur`, `prod_std`) | `semantic/structured/models/` |
| Verified relationships | 59 (fact -> customer dimension joins) | `semantic/structured/relationships/_verified_relationships.yml` |
| Unstructured logical documents | 170 records over 411 physical file versions | `semantic/unstructured/semantic_model.yml` |
| Distinct entities / relationships in the knowledge graph | 309 names (478 rows) / 254 edges | same |
| Golden-entity glossary | 840 entities, 88.8% column coverage, deployed prod 2026-06-19 | `docs/Golden-Entity-Reference.md` |
| Vector Search indices | 4 on one endpoint (`smdl_vs_endpoint`) | `scripts/embedding/vector_search_setup.py:15-22` |
| Agent LLM / factory LLM / embeddings | Claude Sonnet 4.6 / Claude Opus 4.8 / Qwen3-0.6B (all in-tenant) | `app/agent/core/config.py:8`, `workflow/smdl_factory/template.yml:63`, `vector_search_setup.py:16` |

Everything above lives in **one repository**. (Older prose claiming "the structured branch
and the app are not in this repo" is stale; see Appendix C.)

---

## 2. Problem and design principles

**The problem.** A bank has thousands of tables across `prod_cur` / `prod_insight_financial`
/ `prod_std`, and thousands of architecture / security / BRD documents on SharePoint. A
plain LLM cannot answer questions against either: it does not know the schema, it will
hallucinate column names and joins, it cannot be trusted with PII, and it cannot be
audited by a regulator. The AI Foundation closes that gap with a **semantic layer** the
model can ground on, plus **hard guards** the model cannot talk its way past.

Four principles run through every component. They are the things a clone must preserve.

1. **Git-reviewable, version-tracked semantics.** Both semantic models are YAML in the
   repo, not opaque rows in a database. A change to a column's meaning, a PII flag, or a
   join is a reviewable diff. The factory writes to Delta; the Delta is the runtime feed,
   but the YAML is the human source of truth.

2. **PII-safe by construction, not by policy.** The safety is structural, not a checklist.
   A sensitive column can never carry a `value_dictionary` of example values
   (`scripts/lib/value_dict.py:9-22` returns `None` unless the effective PII type is
   `non_pii`), so no sample of a sensitive column can ever reach the LLM, the chunker, or
   the index. The factory's verify query asserts `sum(sensitive AND size(value_dictionary)>0) == 0`
   (`docs/RUNBOOK-factory.md:60-62`). At serving time, a PII mask runs at every LLM and
   persistence boundary (Chapter 8).

3. **Grounded answers, never free-form.** The agent does not "know" the bank. For data it
   retrieves the relevant model/column/metric chunks, generates exactly one `SELECT`, runs
   it, and narrates the actual rows. For documents it retrieves real chunks and cites the
   source. The golden-entity glossary grounds even the build-time enrichment in VIB's own
   canonical definitions rather than the model's general knowledge
   (`docs/superpowers/specs/2026-06-19-golden-entity-reference-design.md:14-32`).

4. **Governed and in-tenant.** Only approved Databricks Model Serving endpoints are used;
   no content leaves the VIB tenant (PDPL, AI Law 134/2025). Every SQL statement is
   read-only by AST proof. Every query is captured in Unity Catalog system tables for
   SBV/NHNN audit (`docs/AI-Foundation.md:165`).

The corollary design decision (`docs/Semantic-Modeling.md`): **two semantic models, not
one.** Structured data needs an executable schema (Wren MDL: tables, columns, joins, SQL).
Documents need a knowledge graph (entities and relationships, no SQL). Forcing both into
one shape would cripple both. They share vocabulary (`models: [A, B]`, `joinType`) but only
the structured side is executable.

---

## 3. The two semantic models (SMDL)

### 3.1 Structured SMDL (Wren MDL)

`semantic/structured/` is an executable Wren semantic model over the financial data marts.
Four parts:

- `models/` - **191** model YAMLs, one per table, across three catalogs:
  `prod_insight_financial` (91), `prod_cur` (70), `prod_std` (30); schemas include `mdm`,
  `fs`, `profit_loss`, `balance_sheet`, `card`, `rb`, `customer_features`, `ml_features`.
- `relationships/` - 13 files: 11 auto-discovered per-schema candidate sets
  (`relationships__<catalog>__<schema>.yml`), one human-confirmed
  `_verified_relationships.yml` (59 joins), one `_lineage_suspects.yml`.
- `kb/code_meanings.yml` - a 1032-line enum-decode dictionary (code -> Vietnamese label).
- `instructions.md` - the SQL-generation convention sheet, indexed for the agent.

**Anatomy of a model YAML.** Top-level keys: `name`, `domain`, `table_reference`,
`columns`, then optional `metrics`, `synonyms`, `lineage`. (Source YAML uses snake_case
`table_reference`; the compiler renames it to Wren's `tableReference`.) A column carries a
`properties` block, and this is where the PII-safety lives:

```yaml
# semantic/structured/models/prod_cur__mdm__cur_mdm_cdmaritalsttp.yml:25-39
- name: MARITAL_ST_TP_CD
  type: bigint
  properties:
    pii_type: identity
    sensitive: true
    provenance: { source: profiling, run_id: ..., profiled_at: '2026-05-25 ...' }
    cdm_concept: { term: Marital Status Code, module: Customer, status: suggested }
  description: Ma tinh trang hon nhan cua khach hang
```

A **non-sensitive** column instead carries a `value_dictionary` (sampled distinct values,
`total_distinct_in_sample`, `truncated`, `source: profiling_sample`); a **sensitive** column
never does. Confirmed on the largest model, a credit-card feature table: financial measures
get `pii_type: financial`, `sensitive: true`, and no value dictionary
(`models/prod_cur__customer_features__feature_cus_credit_card.yml:1220-1228`), while
non-sensitive numeric columns keep a (possibly truncated) value dictionary.

Other column-level and model-level enrichment:

- `synonyms` - bilingual business term -> column maps (`term`, `lang: vi|en`, `target`),
  so "ma khach hang" / "customer id" both resolve to the `CLIENT_NO` column.
- `metrics` - named measures (`type` such as `AVG`/`COUNT_DISTINCT`, a `sql` expression, an
  optional `filter`), reused by the agent rather than re-derived.
- `cdm_concept` - a canonical-data-model term suggestion (`term`, `module`, `status`).
- `lineage` - `upstream_tables`, `source_catalogs`, `source: unity_catalog`.

All enrichment is provisional until a human confirms it: `synonyms`/`metrics` carry
`status: unverified` and `cdm_concept` carries `status: suggested`.

**Relationships** use the real Wren shape: exactly two `models`, a `joinType`, and a SQL
`condition`.

```yaml
# semantic/structured/relationships/relationships__prod_insight_financial__card.yml:1-9
- name: card_spending__to__ft_fs_fa_card_ns__ACCOUNT_ID
  models: [card_spending, ft_fs_fa_card_ns]   # exactly 2
  joinType: ONE_TO_ONE
  condition: card_spending.ACCOUNT_ID = ft_fs_fa_card_ns.ACCOUNT_ID
  confidence: 0.5
  status: unverified
```

The 59 entries in `_verified_relationships.yml` are the human-confirmed subset; all target
the customer dimension on a `client_no` key (fact -> dimension joins).

**Compilation.** `scripts/compile.py` + `scripts/lib/compile_mdl.py` glob-load every
`models/*.yml`, prefer the verified relationship set (else auto-curate the candidates),
and emit a Wren-MDL manifest `{catalog, schema, models, relationships}` to
`semantic/structured/target/mdl.json` (`compile.py:14-39`). `curate_relationships` keeps
only fact -> dimension joins whose second model matches a customer-dimension regex
(`compile_mdl.py:45-66`). This `mdl.json` is the executable Wren semantic core.

> **As-built note.** The committed `target/mdl.json` holds 200 models / 59 relationships
> while `models/` has 191 YAMLs today: the artifact is stale and would regenerate to 191
> on a fresh `python scripts/compile.py`. Compilation is run manually, not wired into the
> factory or the app build. (Inference from the model count delta.)

`instructions.md` codifies six SQL rules the generator must follow
(`semantic/structured/instructions.md`): point-in-time default for snapshot tables
(`WHERE date = (SELECT MAX(date) FROM same_table)`, omitting it is "a serious error");
total-vs-breakdown grain (no `GROUP BY` unless "theo Y"); count entities with
`COUNT(DISTINCT id)` not `COUNT(*)`; reuse a model's defined metrics; return raw aggregates
(do not divide by 1e9); map Vi/En terms via synonyms.

### 3.2 Unstructured SMDL (knowledge graph)

`semantic/unstructured/semantic_model.yml` is a non-executable knowledge graph over the TCP
Registration document corpus on SharePoint. The header is `version: 2`,
`source: sharepoint/TCPRegistration`, then a `documents:` list.

**One logical document = one record with many `versions[]`.** Physical files that differ
only by version (`TCP_EDP_1.5.xlsx`, `_1.6.xlsx`, `_bk.xlsx`) collapse into one record. The
corpus currently holds **170 logical records over 411 physical versions** (one record holds
up to 29 versions).

```yaml
# abstracted from semantic/unstructured/semantic_model.yml:6-238
- id: f0cd0b653cbc            # sha1(doc_key)[:12] - a stable LOGICAL id
  doc_key: TCP EDP            # version/date/qualifier-stripped, space-normalized name
  title: TCP EDP - Enterprise Data Platform Application Architecture
  type: xlsx
  doc_type: architecture       # architecture | solution-proposal | brd | cost-tracking | ...
  domain: data
  brief: |                     # Vietnamese, <300 words, from the CURRENT version only,
    Tai lieu mo ta kien truc ung dung cua EDP ... (keeps English terms: AWS, EMR, S3, MWAA)
  tags: [data-platform, edp, aws, data-governance, architecture]
  current_version: '1.6'
  versions:                    # every physical file of this logical doc
  - { version: '1.6', filename: TCP_EDP_1.6.xlsx, is_current: true, qualifier: '', ... }
  - { version: '1.5', ..., qualifier: bk }     # backups, V02 qualifiers, version: null all collapse here
  semantic:
    entities:
    - { name: EDP, kind: system, vendor: Inhouse, domain: data, description: ... }
    relationships:
    - name: dcsmobile_part_of_dcs
      models: [DCS Mobile, DCS]   # exactly 2, directional A -> B
      type: part-of
      joinType: MANY_TO_ONE       # ONE_TO_ONE | ONE_TO_MANY | MANY_TO_ONE | MANY_TO_MANY
      description: DCS Mobile la thanh phan mobile cua he thong DCS
```

The `semantic` block is the graph: `entities[]` (canonical `name`, a `kind` such as
`system`/`application`/`vendor`, optional `vendor`/`domain`/`description`) and
`relationships[]` (directional, exactly two `models`, a mandatory `type`, an optional
`joinType`). `joinType` is intentionally sparse (only ~14 of 254 edges carry it) because the
convention is to omit it rather than guess.

**Corpus shape.** doc_type: architecture 145, solution-proposal 22, cost-tracking 2,
brd 1. Top tags: architecture (157), integration (101), infrastructure (63), channel (57),
security (49). Top entities: APIM (23), MyVIB (14), ESB (14), AWS (14). Relationship types:
integrates-with (104), sends-data-to (44), built-on (36), hosted-on (21), depends-on (17).

**Invariants** enforced mechanically by `validate_model.py` (exit 0 = clean, 1 = ERROR,
2 = I/O or parse failure):

- `id == sha1(doc_key)[:12]` (`validate_model.py:60-61, 140-143`); `id` and `doc_key` are
  unique across documents (`:145-150`).
- `versions[]` is non-empty with exactly one `is_current: true`, whose `version` matches
  `current_version` (`:156-164`); `(version, qualifier)` is unique within a document
  (`:165-173`).
- Each relationship's `models` has exactly 2 elements (`:113-115`); `type` is mandatory
  (`:120-121`); `joinType`, if present, is in the enum (`:122-124`).

The "brief/tags/semantic are derived from the current version only" and "idempotent by
`id`" rules are documented conventions (`SKILL.md`), not script-enforced. A new version of
an existing document appends to `versions[]` and bumps the current fields only if higher;
it never creates a second record.

---

## 4. The factory: building the SMDLs

The factory is a set of Databricks jobs that build both Delta-backed SMDLs from upstream
profiling tables and the document Volume. It is a **Databricks Asset Bundle**, and every
job YAML is **generated** from `workflow/<job>/{template.yml, config.yml}` (the generated
YAMLs are gitignored; never hand-edit them).

### 4.1 Upstream: PII profiling (separate workspace)

Stage 0 is a separate upstream job, `nedp_mgmt_pii_profile`, living in
`nedp_dbx_management` (the admin workspace), invoked by `make profile`
(`Makefile:9, 52-54`). It scans the scope's source tables and writes
`prod_mgmt.nedp_mgmt.pii_tag_profile` in Unity Catalog. It is deliberately not chained into
the factory because `run_job_task` cannot cross workspaces and the factory runs on DAS
(`workflow/smdl_factory/template.yml:5-9`); because `pii_tag_profile` is Unity Catalog, DAS
reads it directly.

### 4.2 Structured branch: `smdl_factory`

One chained job, parameterized by `catalog` + `schema`, with seven tasks
(`workflow/smdl_factory/template.yml`):

1. **scaffold** (`scripts/factory/build_scaffold.py`) - deterministic, no LLM. Reads
   `pii_tag_profile` + rule/AI tags, computes per-column type / PII type / `sensitive` /
   `value_dictionary` (reusing `lib.sensitivity` and `lib.value_dict`), MERGEs into
   `prod_mgmt.ai.smdl_scaffold`.
2. **golden_match** (`golden_match.py`) - embeds scaffolded columns against the golden
   glossary (`prod_mgmt.ai.smdl_golden_entity`) via the in-tenant Qwen3 endpoint, upserts
   `prod_mgmt.ai.smdl_golden_column_map`. Runs before enrichment so the grounding is ready.
3. **ai_enrich** (`ai_enrich.py`) - Stage 2. For columns flagged `needs_ai`, calls
   `ai_query('databricks-claude-opus-4-8')` in-tenant and MERGEs `prod_mgmt.ai.smdl_enrichment`
   (status `ai_suggested`). PII-safe: only the column name/type and the non-PII value
   dictionary are sent; raw samples of sensitive columns never leave because the scaffold
   already emptied their value dictionary (`ai_enrich.py:5-7`).
4. **metric_enrich** (`metric_enrich.py`) - proposes per-model metrics -> `prod_mgmt.ai.smdl_metric`.
5. **score** (`score.py`) - non-blocking quality scoring; "never fails and never holds".
6. **discover_rel** (`discover_rel.py`) - the join funnel; runs in parallel with enrichment,
   writes `prod_mgmt.ai.smdl_structured_relationship`.
7. **assemble** (`assemble.py`) - publishes `prod_mgmt.ai.smdl_structured` from Delta
   (scaffold + enrichment + metric + relationship), MERGE on `fqn`.

> **As-built note.** The conceptual chain in older docs ("scaffold -> ai_enrich -> output")
> is a subset; the real job has seven tasks and publishes via `assemble`, not directly from
> `ai_enrich`. The factory LLM is **Claude Opus 4.8** (`template.yml:63`), distinct from the
> agent's Sonnet 4.6.

### 4.3 Unstructured branch: `smdl_doc_factory`

One job, parameterized by `volume` + `limit` (`workflow/smdl_doc_factory/template.yml`):

1. **extract** (`doc_extract.py`) - walks the document Volume, extracts text from
   xlsx/pptx/txt/pdf -> `prod_mgmt.ai.smdl_doc_text`.
2. **group** (`doc_group.py`) - groups into logical docs (`id = sha1(doc_key)`) with
   `versions[]`, picks the current version -> `prod_mgmt.ai.smdl_doc_version`.
3. **understand** (`doc_understand.py`) - `ai_query` (Claude in-tenant) per current-version
   text -> brief / tags / entities / relationships -> `prod_mgmt.ai.smdl_doc_semantic`.
4. **audit** (`doc_audit.py`) - canonicalizes entity names + vendor aliases, detects
   conflicts, checks invariants -> `prod_mgmt.ai.smdl_doc_audited`.
5. **assemble** (`doc_assemble.py`) - MERGE on `id` into `prod_mgmt.ai.smdl_unstructured`
   (no delete-by-source, so verified records survive).

### 4.4 The skill-driven path (human + Claude)

The factory is the scaled, automated path. There is also a skill-driven path for the
unstructured side where the intelligence is Claude's job and Python only does mechanical
work: `semantic-extract` (run `extract_text.py` to emit a metadata stub + raw text, then
Claude writes the `brief`/`tags`/`semantic`) and `semantic-validate` (run `validate_model.py`,
Claude fixes errors until 0 ERROR). The conventions live in the `SKILL.md` files, which are
authoritative over the divergent examples in `docs/Semantic-Modeling.md` §9.2.

### 4.5 Code generation and bundles

`make build` runs `scripts/build_artifacts.py`, which holds the `WORKFLOWS` list and shells
out to `scripts/generate_job.py <name>` for each. The generator reads
`workflow/<name>/{config,template}.yml`, injects `existing_cluster_id = ${var.<cluster_var>}`
on every compute task, wraps the job under the `targets:` from `config.targets`, and emits
to `bundles/<bundle>/resources/jobs/<name>.yml` where `bundle` comes from the config
(`generate_job.py:43-58, 89-96`). The `config.yml` of each job is therefore the routing
table: it decides workspace (bundle), targets, and cluster.

The repo holds **two bundles, one per workspace** (so a `bundle deploy` can never leak a
resource across workspaces):

- `bundles/factory/` - bundle `nedp_semantic_factory`, DAS workspace, targets
  `dev`/`uat`/`prod`. Holds `smdl_factory`, `smdl_doc_factory`, the embedding chunk-build
  job `smdl_build_chunks` (prod only), and `smdl_golden_publish` (prod only).
- `bundles/app/` - bundle `nedp_smdl_app`, BU workspace, target `bu`. Holds the committed
  `smdl-assistant` Databricks App and the generated Vector Search index-sync job
  `smdl_index_sync`.
- `bundles/shared/variables.yml` - defaults included by both: the service principal both
  run as, the DAS cluster (`cluster_id`, factory + embedding build), the BU cluster
  (`bu_cluster_id`, index-sync; VIB does not allow serverless), and the BU SQL warehouse
  (`bu_warehouse_id`, the app's text-to-SQL engine).

Make targets: `build` (codegen), `validate` / `deploy` (build then `bundle validate|deploy -t TARGET`
on the factory bundle), `profile` (upstream PII), `factory` (run the structured job),
`doc-factory` (run the unstructured job), `app-build` (React build + assemble
`build/dbx_app/`), `app-deploy` (build + deploy to BU + run). All bundle ops carry
`DATABRICKS_TF_VERSION=1.10.0` (`Makefile:8`).

---

## 5. Embedding and Vector Search

The embedding code lives at `scripts/embedding/` (note: not a top-level `embedding/`).
It chunks both Delta SMDLs and syncs four Vector Search indices.

**Chunking is a hierarchy, not one chunk per object** (`scripts/embedding/lib/chunk_smdl.py`):

- Structured, per Wren model: one **L1 `table` chunk** (`"Table {fqn} (domain). Metrics:
  ... Columns: ..."`, column list capped at 60 names as a discovery anchor); one **L2
  `column` chunk** per column (name, type, description, CDM concept, synonyms, and example
  values **only if not sensitive**); one **`metric` chunk** per metric. Relationships are a
  separate `relationship` chunk per row of `smdl_structured_relationship`.
- Unstructured, per logical document: one **`document` chunk** (`"{title}: {brief} Tags:
  ..."`), one **`entity` chunk** per entity, one **`relationship` chunk** per edge. All
  carry the current version's `source_url` only.

Every chunk shares one record schema (`chunk_id, parent_id, layer, source_id, chunk_type,
ref, text, domain, status, sensitivity, source_tag, source_url, content_hash, smdl_version`).
`chunk_id` is a deterministic `sha1` of `layer|source_id|chunk_type|ref`, so re-runs MERGE
in place. Only the `text` column is embedded (`vector_search_setup.py:45`).

**Four indices on one endpoint** (`smdl_vs_endpoint`), the result of the per-scope split:

| Index | Source table | Scope |
| --- | --- | --- |
| `prod_mgmt.ai.smdl_fs_index` | `chunk_fs` | fs (financial marts) |
| `prod_mgmt.ai.smdl_dec_index` | `chunk_dec` | dec (RB DBB / dec_bu, parked) |
| `prod_mgmt.ai.smdl_shared_index` | `chunk_shared` | shared (cur/std, queried alongside) |
| `prod_mgmt.ai.smdl_unstructured_index` | `chunk_unstructured` | tcp (documents) |

The split (`docs/superpowers/specs/2026-06-22-per-scope-index-split-design.md`) replaced a
single structured index because, after onboarding dec_bu, ~46% of chunks were dec_bu and
were polluting FS retrieval and blocking per-team cost attribution. A DELTA_SYNC index maps
to exactly one source table and the SQL `vector_search()` TVF the agent uses cannot filter
by metadata, so the answer is N source tables + N indices. The catalog -> scope map
(`scripts/embedding/lib/scope_map.py`): `prod_insight_financial` -> fs,
`prod_v_ext_decdc` -> dec, `prod_cur`/`prod_std` -> shared. `shared` is its own index
queried alongside each scope so shared content is not duplicated (and not billed multiple
times). The agent maps `mart` -> `[fs, shared]`, `docs` -> `[unstructured]`.

**Embedding model:** `databricks-qwen3-embedding-0-6b` (`vector_search_setup.py:16`), the
only in-tenant embedding endpoint, multilingual for Vietnamese, satisfying no-PII-to-internet.
Mode is managed embeddings, `pipeline_type="TRIGGERED"`, `primary_key="chunk_id"`,
`embedding_source_column="text"`.

**Two jobs:**
- `smdl_build_chunks` (factory bundle, prod only, DAS cluster) reads the three SMDL Delta
  inputs, applies the pure transforms, routes structured chunks per-scope into
  `chunk_fs`/`chunk_dec`/`chunk_shared`, MERGEs unstructured into `chunk_unstructured`, and
  rebuilds a `chunk_structured` UNION view.
- `smdl_index_sync` (app bundle, BU workspace) iterates the four indices and calls
  `sync_index`, triggered event-driven on `table_update` of any chunk table
  (`wait_after_last_change_seconds: 120`). It must run in the index-creation workspace (BU),
  which is why it is in the app bundle.

**PII safety in chunking** is defense-in-depth on top of the factory contract: value-
dictionary text is emitted only when the column is not sensitive
(`chunk_smdl.py:106-108`); sensitive columns are tagged `sensitivity="sensitive"` and never
emit example values (tested at `test_chunk_smdl.py:88-92`).

---

## 6. The agent

The agent backend is `app/agent/`, organized as **soul / shield / skills / memory** with a
thin entrypoint. The most important design fact: **there is no LLM router.** The UI scope
dropdown is the route, and `agent.py` branches on the scope string
(`agent.py:402` "scope LA route").

```
scope ──> agent.py _run_inner ──┬── mart | rbdbb  ──> text-to-SQL path
                                └── tcp | brd | vib ──> docs Brain path
```

Multi-scope or zero-scope is refused before any tool runs ("Pick exactly one scope per
question", `agent.py:481-484`).

### 6.1 Mart path (text-to-SQL)

Two execution modes share the same narrative/chart/store tail. `MART_BRAIN` defaults **on**
(`config.py:54`), so the active mart path is a plan-act-observe brain.

- **Active: `_run_mart_brain`** (`agent.py:321-375`) runs `brain.run` over three SQL
  primitives - `recall_sql` (semantic-memory recall), `fetch_schema` (retrieve + expand
  column chunks to full table schema), `run_sql` (guarded execution) - under the mart soul,
  with budgets `(5 iter, 6 calls, 90s)` or deep `(8, 10, 150s)`. The primary result is the
  last successful query.
- **Fallback: deterministic single-SELECT pipeline** (`agent.py:486-567`, reached only when
  `MART_BRAIN=0`): contextualize follow-up -> semantic-memory recall (cosine over the
  verified-SQL cache, hit requires `sim >= 0.92` with a margin) -> on miss
  `skills.invoke("analytics_sql")` (retrieve chunks -> generate one SELECT -> guard -> run ->
  retry on engine error) -> narrative.

Both modes end the same way: rows are PII-masked, a **three-layer narrative** is generated
("Boi canh / Insight / Goi y hanh dong" - Context / Insight / Action), a chart is picked
(`viz.pick_chart`), a confidence note is appended on 0 rows or a LIMIT hit, and a background
**store-gate** thread asks the LLM YES/NO whether the SQL fully answered before caching it.

The `MART_BRAIN`-on gate measured 0.70 vs 0.59 for the deterministic pipeline with no
regressions (`eval/agent/reports/report_2026-06-15_mart_gate.md`), and it "fails safe"
(refuses to invent numbers) where the old pipeline guessed.

### 6.2 Docs path (Brain)

`_run_brain` (`agent.py:139-301`) is the sole docs path (owner decision 2026-06-12: no
keyword routing). It calls `brain.run` (`brain.py:35-89`), a pure-Python plan-act-observe
loop with budgets `MAX_ITERATIONS=8`, `MAX_TOOL_CALLS=10`, `MAX_SECONDS=120` (deep: 12 / 16 /
180). The system prompt is the docs soul. Registered tools: `search_docs`, `system_graph`,
`doc_lookup`, `read_document`.

The **answer shape is derived from the tool trace**, not pre-decided:

- `system_graph` returned rows and the user enabled the graph -> a graph answer
  (`center` + `adjacency`).
- `doc_lookup` produced clickable links -> a links answer.
- otherwise -> a text answer with source cards from the retrieval hits.

Extras: a dominant document gets all its chunks pulled in; a "safety net" auto-reads the
source file when the draft answer admits a gap; deep mode adds a self-check pass.

### 6.3 Skills registry

`skills/__init__.py` is the single registry serving both modes. `register()` refuses any
descriptor missing the required metadata (`name`, `description`, `input_schema`, `scope`,
`invoker`, `min_role`, `requires_human_approval`, `audit_action_type`). `invoke()`
normalizes every result and exception to `{ok, code, message}` (`unknown_skill`,
`guard_refused`, `skill_error`). Registered skills: `search_docs`, `system_graph`,
`doc_lookup`, `analytics_sql`, `recall_sql`, `fetch_schema`, `run_sql`, `read_document`.
The `run_sql` skill is `lambda sql, run_sql: run_sql(sqlguard_guard(sql, ROW_LIMIT))` - the
guard is not bypassable from the skill layer.

### 6.4 Shield

- **sqlguard** (`shield/sqlguard.py`) is an AST guard (sqlglot, Databricks dialect, chosen
  over regex so keywords inside string literals are not falsely blocked). `guard()` requires
  exactly one statement, requires the root to be a `Query` (SELECT/WITH/UNION) else
  `GuardError("only SELECT/WITH allowed")`, walks the whole tree and rejects any forbidden
  node (Insert/Update/Delete/Merge/Drop/Alter/Create/TruncateTable/Grant/Command/Set/Use/
  Call - defense against DDL hidden in `CREATE ... AS SELECT`), and **clamps LIMIT** to
  `ROW_LIMIT` (default 1000), adding one if absent. `extract_sql` pulls a clean statement
  from an LLM reply.
- **pii_mask** (`shield/pii_mask.py`) masks card numbers (formatted, or bare-16 passing Luhn
  with a card IIN, so a long VND `SUM()` is not mistaken for a card), CCCD, VN phone, and
  email. `mask_rows` masks every string cell; `mask_text` masks free text. It runs at every
  boundary: rows before the narrative prompt, intro on output, question before persistence.

### 6.5 Memory tiers

- **working** (`memory/working.py`) - per-invocation retrieval cache, RAM only; deep mode
  widens `k`.
- **session** (`memory/session.py`) - server-side chat history on
  `prod_mgmt.ai.app_chat_history`, MERGE on `(session_id, user_email)`. Every read
  hard-filters `user_email` at the SQL layer - this is the cross-user boundary (red-team
  `test_session_queries_always_parameterized_on_user_email`).
- **semantic** (`memory/semantic.py`) - the verified question -> SQL cache on
  `prod_mgmt.ai.app_query_memory`. Deliberately shared cross-user as an org cache, safe
  because the question is PII-masked, no result rows are stored, and recalled SQL is
  re-guarded before re-execution.
- **episodic** - off / absent by design.

### 6.6 The only SDK module, and the models

`core/llm.py` is the sole module importing the Databricks SDK (lazy singletons elsewhere).
It calls `LLM_ENDPOINT` for single-prompt and tool-calling chat, `EMBED_ENDPOINT` for
embeddings, and SQL via two runners: `run_sql` (the app service principal) and
`run_sql_as_user` (an on-behalf-of user token for the `rbdbb`/dec_bu mart, fail-closed if no
token). The agent model is **`databricks-claude-sonnet-4-6`** (`config.py:8`); embeddings
are Qwen3-0.6B (the trajectory was Opus 4.8 -> Haiku 4.5 -> Sonnet 4.6, overridable by env).

### 6.7 Deep mode

Deep widens retrieval `k` (struct/unstruct 20/12 vs 10/5), widens every budget, and adds a
self-check pass that validates each figure against the tool evidence.

---

## 7. The web application

`app/server.py` is a FastAPI web shell that streams Server-Sent Events to a React+Vite UI
(`app/ui/`). The Python answer shapes in `app/agent/answers/__init__.py` are byte-mirrored
by the TypeScript types in `app/ui/src/types.ts`.

**SSE contract.** Three event types over `text/event-stream`:

- `step` - one thinking step, either `{kind:"txt", html}` (a narrative line) or
  `{kind:"tool", name, json}` (a tool/SQL call). SQL is emitted as a `warehouse.statement`
  tool step.
- `answer` - the final object, one of `DataAnswer` / `DocAnswer` / `TextAnswer`.
- `done` - `{type:"done", elapsedMs}`.

The agent runs in a worker thread (SDK calls block); the SSE generator drains an
`asyncio.Queue`. On any exception the server emits a text error answer rather than breaking
the stream.

**Scope dropdown = route.** The UI always sends exactly one scope; the backend treats
`scopes[0]` as the route. Scopes: `mart` "Data marts" (active), `rbdbb` "RB DBB" (gated),
`tcp` "Documents / TCP" (active), `brd` "BRD-BRS" (soon), `vib` "Internal docs" (disabled).
`rbdbb` is access-gated both in the UI (hidden unless allowed) and server-side
(`authz.allowed_scopes`). Scope is locked once a chat begins.

**A turn renders** as: a user bubble, a Thinking panel (streamed `txt` steps as trusted
HTML, `tool` steps as JSON or pretty-printed SQL, auto-collapsing after `done`), then an
AnswerView. For `data`: a dependency-free inline-SVG chart (`Chart.tsx`, with VN B/M/K unit
scaling), the formatted table, a "View SQL" panel, and a "View raw data" panel. For `doc`:
a graph panel + source cards. For `text`: links, source cards, citations. SQL is
pretty-printed by a quote- and paren-aware formatter (`app/ui/src/sql.ts`).

**Build and dev.** `npm run build` = `tsc -b && vite build`. `VITE_USE_BACKEND != 1` serves
canned demo turns from `demo.ts`; `APP_DEMO=1` stubs Databricks on the backend. In
production FastAPI mounts the built UI as static files at `/` (mounted last so `/api/*`
matches first). `scripts/build_dbx_app.sh` builds the UI and assembles `build/dbx_app/`
(app.yaml + server.py + agent/ + static/).

**Deployment.** The app deploys from `bundles/app/` (bundle `nedp_smdl_app`, target `bu`,
BU workspace) as a Databricks App `smdl-assistant`. It declares OBO `user_api_scopes: [sql]`
for per-user masking and binds the `prod-sql-bu` warehouse as an app resource. User SSO
identity arrives via `X-Forwarded-*` headers.

---

## 8. Governance and security

The governance story is the differentiator, and it is structural at four layers.

1. **PII-safe by construction (build time).** A sensitive column structurally cannot carry a
   value dictionary, so no sample of sensitive data exists anywhere downstream - not in the
   YAML, the Delta, the chunk text, or the index. The factory verify query asserts zero PII
   leaks (`docs/RUNBOOK-factory.md:60-62`).

2. **PII mask (serving time).** Card / CCCD / phone / email are masked at every LLM and
   persistence boundary, with card-vs-amount disambiguation by Luhn + IIN so financial
   aggregates survive (`shield/pii_mask.py`).

3. **Read-only by AST proof.** Every statement that reaches the warehouse has passed the
   sqlguard AST guard: one statement, SELECT/WITH only, no DDL/DML node anywhere in the
   tree, LIMIT clamped. Recalled cache SQL is re-guarded before re-execution.

4. **Identity and access.** Per-user row/column masking for the gated `rbdbb` scope runs the
   data query **as the user** via an on-behalf-of token (`run_sql_as_user`, fail-closed),
   so Unity Catalog definer's-rights dynamic views mask per user (admin sees raw, others
   masked) - design `docs/superpowers/specs/2026-06-22-p2b-model-a-obo-sql-design.md`. The
   scope itself is group-gated (`core/authz.py`, `allowed_scopes` via OBO `current_user.me()`,
   fail-closed, 5-minute cache), enforced in both the UI and the server. Session memory
   hard-filters `user_email` at the SQL layer.

**In-tenant only.** Every model (Claude Sonnet 4.6 agent, Claude Opus 4.8 factory, Qwen3
embeddings) is a Databricks Model Serving endpoint inside the VIB tenant; no content leaves
to an external service (PDPL, AI Law 134/2025). **Auditable:** Unity Catalog system tables
record every query for SBV/NHNN and PDPL audit (`docs/AI-Foundation.md:165`).

**The red-team suite** (`app/tests/red_team/test_refusal.py`) is the executable proof that
the refusal contract reaches runtime: single-scope enforced before any tool touch; PII
masked before the narrative prompt; injected DDL never reaches the warehouse on either path;
recalled-memory SQL re-guarded and poison entries deactivated; prompt-driven memory writes
blocked; session queries always parameterized on `user_email`; and the guard + PII mask hold
inside the mart brain.

---

## 9. Evaluation

The benchmark (`eval/agent/`) is a regression gate that "produces numbers, not opinions".
As-built it has three live layers (the offline router layer was retired with the 4-route
router):

- **Layer 2 retrieval** (`bench_retrieval.py`) - for each gold query in three forms (Vi,
  no-diacritics, En), takes the ranked top-k `chunk_id`s from `vector_search` and computes
  recall@k / MRR / hit_rate@k per form and index. PII-safe: only chunk ids and scores are
  handled. Gold: `gold_retrieval.yml`.
- **Layer 4 route-C text-to-SQL** (`bench_routec.py` + `score_routec.py`) - drives each gold
  `nl_vi` through the real `analytics_sql.run`, then executes produced vs expected SQL and
  compares with a semantic matcher. Default "cluster" engine returns only `{id: pass/err}`
  (rows never leave the cluster); an opt-in "warehouse" engine is row-capped at 5000.
- **Layer 3 e2e** (`bench_e2e.py`) - scores chart family + narrative faithfulness (an
  in-tenant Claude judge on a faithfulness/relevance/completeness rubric, fed only the
  question + rows + answer, never the source tables) and browse-URL correctness.

Reports render to dated `eval/agent/report_*.md`. **Known failure modes** (from
`eval/eval_report.md`, ~8/18 exact-match, ~13/18 business-correct): aggregation grain (a
breakdown where a single total was wanted), missing or wrong `LIMIT`, and unit scaling
(`/1e9`, `/1e12`). These are the three things a clone should expect to tune first.

---

## 10. Deployment topology

```
 Admin workspace (nedp_dbx_management)   nedp_mgmt_pii_profile  ->  pii_tag_profile (UC)
                                          [proposed] P3 chargeback Lakeview dashboard
 DAS workspace (prod-shared-das)          bundle nedp_semantic_factory  (dev / uat / prod)
                                          smdl_factory, smdl_doc_factory,
                                          smdl_build_chunks (prod), smdl_golden_publish (prod)
 BU workspace (dbc-6f163873-fdba)         bundle nedp_smdl_app  (target bu)
                                          smdl-assistant App + smdl_index_sync
                                          uses prod-shared-bu cluster + prod-sql-bu warehouse
```

- **Two bundles, one workspace each**, so a deploy can never cross workspaces. The shared
  service principal runs both. VIB does not allow serverless, so jobs pin named clusters.
- **Storage** (`docs/Storage.md`, PROD): semantic memory + MDL reuse under
  `s3://aws-sg-nedp-prod-datamanagement/ai/` (LanceDB writes S3 directly via IAM, UC
  External Volume as a governance/visibility layer); original documents at
  `s3://aws-sg-nedp-prod-raw/documents/` via UC External Volume `prod_raw.documents`. SMDL
  outputs persist to `prod_mgmt.ai.smdl_*`.
- The production app moved to the BU workspace on 2026-06-12.

**Recent / near-built capabilities** (status as labelled in the specs):

| Capability | Spec | Status |
| --- | --- | --- |
| Golden Entity Reference (840-entity glossary grounding the enrich LLM) | `2026-06-19-golden-entity-reference-design.md` | Deployed prod 2026-06-19 (grounding default OFF until an owner enables) |
| Per-scope index split (4 indices) | `2026-06-22-per-scope-index-split-design.md` | Cutover / live |
| RB DBB (`rbdbb`/dec) scope, group-gated | `2026-06-22-p2b-rbdbb-scope-design.md` | Built |
| OBO "as-user" SQL for per-user masking | `2026-06-22-p2b-model-a-obo-sql-design.md` | Built |
| Cost attribution & chargeback (token metering -> `agent_usage`) | `2026-06-22-cost-attribution-chargeback-design.md` | P1 metering built; P2/P3 phased |
| Chargeback Lakeview dashboard (admin workspace) | `2026-06-23-p3-chargeback-dashboard-design.md` | Approved, near-built |

---

## 11. Cloning to a new business domain

This is the reason the system is shaped the way it is: the expensive, reusable machinery is
domain-agnostic, and the domain lives in a thin, well-bounded layer. To stand up the AI
Foundation for a new business domain (a new set of marts, a new document corpus, or both),
you replace the **domain layer** and keep the **core** untouched.

**The reusable core (clone as-is).** The factory codegen and bundles (`scripts/`,
`workflow/`, `bundles/`), the chunker and Vector Search setup (`scripts/embedding/`), the
entire agent (`app/agent/`: soul / shield / skills / memory / answers), the web shell and UI
(`app/server.py`, `app/ui/`), the SSE contract, the red-team suite, and the eval harness.
None of these encode a specific domain; they encode the pattern.

**The domain layer (replace per clone):**

1. **Upstream profiling scope.** Point `make profile` at the new catalog/schema so
   `pii_tag_profile` covers the new marts. The PII rules in `lib/sensitivity.py` are bank-
   generic but should be reviewed for any domain-specific sensitive types.
2. **Structured SMDL content.** Run the structured factory over the new scope to scaffold
   and enrich `semantic/structured/models/*.yml`. The schema is identical; only the rows
   change. Confirm relationships into the new domain's dimension(s).
3. **Golden entity glossary.** Author `semantic/golden/business_glossary.yml` for the new
   domain's canonical concepts so enrichment is grounded in that domain's truth, not the
   model's guess. This is the single highest-leverage domain artifact (A/B lift OFF 2/10 ->
   ON 9/10 on canonical-term alignment).
4. **Unstructured SMDL content.** Point the document factory (or the `semantic-extract`
   skill) at the new corpus / Volume; the knowledge-graph schema is unchanged.
5. **Scope and routing.** Add the new scope to the UI dropdown, the `SCOPE_INDICES` /
   `SCOPE_CATALOGS` maps, and `catalog -> scope` in `scope_map.py`; gate it with `authz`
   groups if it is access-controlled, exactly as `rbdbb` is.
6. **Indices.** Add an index per new scope on the shared endpoint (the per-scope split is
   already built to scale this way).
7. **The soul.** Tune the per-scope system prompt in `soul/` for the domain's vocabulary
   and any domain-specific refusals.
8. **Gold sets.** Write `gold_retrieval.yml` / route-C gold for the new domain and run the
   benchmark; budget time to tune the three known failure modes (grain, LIMIT, unit
   scaling).

**What stays constant, and why it sells.** Every clone inherits the same governance proof
(PII-safe by construction, read-only AST guard, in-tenant models, OBO per-user masking,
auditable system tables, a red-team suite) and the same cost-attribution machinery. The
pitch to a new domain owner is therefore not "we will build you a chatbot" but "we will
point a proven, governed, regulator-defensible foundation at your data, and the only new
work is your glossary and your gold set."

---

## 12. Appendices

### Appendix A. File map

| Area | Path | What |
| --- | --- | --- |
| Structured SMDL | `semantic/structured/` | 191 model YAMLs, `relationships/`, `kb/code_meanings.yml`, `instructions.md`, compiled `target/mdl.json` |
| Unstructured SMDL | `semantic/unstructured/semantic_model.yml` | 170-record knowledge graph |
| Golden glossary | `semantic/golden/business_glossary.yml` | canonical entity bible |
| Factory scripts | `scripts/factory/`, `scripts/lib/` | scaffold / enrich / assemble / sensitivity / value_dict |
| Codegen | `scripts/build_artifacts.py`, `scripts/generate_job.py` | generate job YAMLs from templates |
| Job sources | `workflow/<job>/{template,config}.yml` | source of truth for every job |
| Bundles | `bundles/factory/`, `bundles/app/`, `bundles/shared/` | two workspaces, shared vars |
| Embedding | `scripts/embedding/` | `lib/chunk_smdl.py`, `vector_search_setup.py`, `build_chunks.py`, `sync_indexes.py`, `lib/scope_map.py` |
| Agent | `app/agent/` | `agent.py`, `brain.py`, `mart_brain.py`, `soul/`, `shield/`, `skills/`, `memory/`, `core/`, `answers/` |
| Web shell + UI | `app/server.py`, `app/ui/` | FastAPI SSE + React/Vite |
| Red team | `app/tests/red_team/` | refusal contract tests |
| Eval | `eval/agent/` | layered benchmarks + gold + reports |
| Skills (Claude-driven) | `.claude/skills/{semantic-extract,semantic-validate,structured-enrich}/` | SKILL.md conventions + mechanical scripts |
| Wiki | `docs/` | `AI-Foundation.md`, `Semantic-Modeling.md`, `Agent-architecture.md`, `Storage.md`, `RUNBOOK-factory.md`, `superpowers/specs/` |

### Appendix B. Glossary

- **SMDL** - Semantic Model (Definition Layer); the structured (Wren MDL) and unstructured
  (knowledge graph) models.
- **Wren MDL** - the executable semantic-model format (tableReference, columns, joins) that
  compiles to `mdl.json`.
- **Scope** - the UI dropdown value that is also the agent's route (`mart`, `rbdbb`, `tcp`,
  `brd`, `vib`).
- **Brain** - the pure-Python plan-act-observe loop (`brain.py`) used by the docs path and,
  with `MART_BRAIN=1`, the mart path.
- **Soul / shield / skills / memory** - the agent's system prompts / guards / tool registry
  / memory tiers.
- **OBO** - on-behalf-of; running a SQL query under the end user's token so Unity Catalog
  masks per user.
- **DAS / BU** - the two Databricks workspaces (factory / app).
- **Golden entity** - a curated canonical VIB concept used to ground build-time enrichment.

### Appendix C. As-built deltas from the older prose

This document follows the running code where it diverges from `CLAUDE.md` /
`docs/Semantic-Modeling.md`:

1. The embedding pipeline lives at `scripts/embedding/`, not a top-level `embedding/`.
2. The agent LLM is Claude Sonnet 4.6 (`config.py:8`); the factory enrichment LLM is Claude
   Opus 4.8. (Older prose says "Haiku" or just "Claude".)
3. The mart path defaults to a plan-act-observe brain (`MART_BRAIN=1`); the deterministic
   single-SELECT pipeline is the fallback.
4. There are four Vector Search indices (per-scope split), not two.
5. The structured factory has seven tasks publishing via `assemble`, not a three-step chain.
6. The compiled `target/mdl.json` is stale (200 models vs 191 YAMLs) and is built manually.
7. `docs/Semantic-Modeling.md` §9.2's unstructured examples (`join_type`, `properties.type`)
   are wrong; the authority is `validate_model.py` + the `SKILL.md` files.
8. `docs/Agent-architecture.md` describes an MCP design that was not built; the as-built
   agent uses in-process skills (a declared deviation in `manifest.yaml`).

### Appendix D. Primary sources

`semantic/structured/`, `semantic/unstructured/semantic_model.yml`,
`scripts/{factory,lib,embedding}/`, `scripts/{compile.py,build_artifacts.py,generate_job.py}`,
`workflow/<job>/{template,config}.yml`, `bundles/`, `app/agent/`, `app/server.py`,
`app/ui/src/`, `app/tests/red_team/`, `eval/agent/`, `.claude/skills/`, and the design wiki
under `docs/` (notably `AI-Foundation.md`, `Semantic-Modeling.md`, `Storage.md`,
`RUNBOOK-factory.md`, `Golden-Entity-Reference.md`, and `docs/superpowers/specs/`).
