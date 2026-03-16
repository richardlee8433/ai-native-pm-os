# AI-Native PM OS v5.0 Gap List and Implementation Roadmap

Version: draft 0.1
Date: 2026-03-16
Scope: planning document for upgrading the current codebase from v4.1 validation architecture to v5.0 claim-governed knowledge architecture

## 1. Current Baseline

Current implemented backbone in this repo:

- Signal ingestion and normalization
- Newsletter-to-graph hypothesis writeback
- Graph store for `hypothesis`-centric nodes
- Validation Project (VP) planning
- AVL Evidence Pack creation and validation
- Promotion report generation
- Manual promotion router for provisional LTI / RTI review
- CX replay stub

Current architecture status:

- The repo still points to v4.1 as the active architecture.
- The execution model is still `Graph -> VP -> AVL -> Promotion -> LTI`.
- The knowledge unit is still closer to `signal`, `hypothesis`, and `provisional knowledge` than to v5.0 `claim-governed knowledge`.

## 2. v5.0 Target State

Target operating formula in v5.0:

`Signal -> Knowledge Ingestion -> Claim Graph -> Pattern Distillation -> Validation -> LTI Promotion -> RTI Governance -> Execution -> Evidence Writeback`

Required v5.0 system capabilities:

1. External knowledge is normalized into governed claim objects.
2. Claims are stored in a graph with typed nodes and explicit relationships.
3. Knowledge conflicts are detected and routed through explicit resolution logic.
4. Distillation produces patterns and principles, not just isolated insights.
5. Validation targets are `candidate claim` and `candidate principle`.
6. Promotion accepts `validated claim` / `validated principle`.
7. LTI knowledge can represent `Pattern`, `Principle`, `Decision Rule`, and `Evaluation Standard`.
8. Evidence packs link back to claim references and claim graph nodes.

## 3. Gap List

### 3.1 Contracts and Data Models

Missing:

- `CLAIM_OBJECT` contract
- `CLAIM_EDGE` or equivalent relationship contract
- `PATTERN` / `PRINCIPLE` / `DECISION_RULE` / `EVALUATION_STANDARD` representation
- v5.0-aligned `LTI_NODE` knowledge type metadata
- v5.0 Evidence Pack fields: `claim_reference`, `claim_graph_node`

Impact:

- No stable system boundary exists for claim-governed ingestion.
- Downstream modules cannot distinguish between source text, hypothesis, validated claim, and promoted principle.

### 3.2 Knowledge Ingestion Layer

Missing:

- Claim extraction from external content
- Context detection
- Metric identification
- Assumption extraction
- Failure mode detection
- Applicability detection
- Rule candidate generation

Current limitation:

- Ingestion normalizes content into `SIGNAL`.
- Newsletter flow derives `core_claim` and `hypothesis_statement`, but not a full claim object pipeline.

### 3.3 Claim Graph

Missing:

- Node types for `Claim`, `Context`, `Metric`, `Practice`, `FailureMode`, `Evidence`
- Relationship types for `supports`, `contradicts`, `refines`, `applies_to`, `derived_from`
- Edge persistence and query utilities
- Claim-centric CLI operations

Current limitation:

- Graph store is still `concept / skill / playbook / hypothesis / evidence`.
- Related nodes are stored as loose references, not typed claim graph edges.

### 3.4 Conflict Resolution

Missing:

- Context conflict detection
- Metric conflict detection
- Evidence conflict detection
- Conflict state storage
- Resolution recommendations
- Replay trigger integration for evidence conflicts

Current limitation:

- Contradiction handling is not implemented as a first-class subsystem.

### 3.5 Pattern Distillation Engine

Missing:

- Multi-claim clustering
- Pattern synthesis
- Principle candidate generation
- Rule candidate promotion path

Current limitation:

- Distillation is still article- or hypothesis-oriented.
- No pattern-level artifacts are created.

### 3.6 Validation Layer Upgrade

Missing:

- Validation target model for `claim` and `principle`
- Automated metrics validation flow for v5.0 Mode C
- Validation results attached directly to claim nodes / pattern nodes
- Validation aggregation at claim/principle level

Current limitation:

- Validation still centers on VP + AVL around graph hypothesis.
- Evidence is not structurally attached to claim graph entities.

### 3.7 Promotion and Governance

Missing:

- Promotion input model for `validated claim` / `validated principle`
- Unified promotion decision source of truth
- Claim-aware RTI review triggers
- Promotion routing by knowledge type

Current limitation:

- Promotion report and manual promotion router still operate as separate decision systems.
- Promotion output is provisional LTI without v5.0 knowledge typing.

### 3.8 Observability and Migration

Missing:

- Migration path from existing graph hypotheses to claims
- Backfill tools for existing AVL / VP / graph data
- v5.0 acceptance test suite
- Architecture pointer and documentation alignment

Current limitation:

- v5.0 exists as an architecture file, not as the active implementation baseline.

## 4. Design Principles for the Upgrade

1. Preserve v4.1 operational flow while adding v5.0 modules behind explicit boundaries.
2. Introduce new contracts before rewriting existing flows.
3. Keep backward-compatible adapters for current `Graph -> VP -> AVL -> Promotion`.
4. Promote only after claim references are traceable end to end.
5. Prefer append-only storage and deterministic IDs for new knowledge artifacts.

## 5. Module Plan

### Module A. Contracts and Schemas

Goal:

- Define the v5.0 data boundaries.

Deliverables:

- `CLAIM_OBJECT` model and JSON schema
- `CLAIM_EDGE` model and JSON schema
- `PATTERN_CANDIDATE` model and JSON schema
- `PRINCIPLE_CANDIDATE` model and JSON schema
- `LTI_NODE` extension for knowledge typing
- `AVL_EVIDENCE_PACK` extension for claim references

Tasks:

1. Add new Pydantic models in `pm_os_contracts/models.py`.
2. Add matching schemas under `contracts/v1.0/`.
3. Add serialization / deserialization coverage.
4. Add contract validation tests.

Definition of done:

- New contracts validate through both schema and Pydantic tests.
- Existing contracts remain backward-compatible.

### Module B. Knowledge Ingestion Layer

Goal:

- Convert source content into governed claim objects.

Deliverables:

- Claim extraction pipeline
- Claim normalization utilities
- Claim storage output
- CLI for ingestion-to-claim execution

Tasks:

1. Create `ingest/claim_extraction.py`.
2. Create `ingest/claim_pipeline.py`.
3. Extract fields:
   - `claim_statement`
   - `source`
   - `domain`
   - `context`
   - `metric`
   - `evidence_type`
   - `confidence`
   - `failure_modes`
   - `applicability`
   - `rule_candidate`
   - `timestamp`
4. Add deterministic `claim_id` generation.
5. Write claim objects to append-only storage.
6. Add tests for RSS / newsletter / article-derived claim extraction.

Definition of done:

- A source item can be transformed into one or more valid `CLAIM_OBJECT` records.
- Claim extraction output is testable without external network dependence.

### Module C. Claim Graph

Goal:

- Replace hypothesis-centric graph semantics with claim-centric graph semantics.

Deliverables:

- Claim graph node store
- Claim graph edge store
- Query helpers for incoming/outgoing relations
- CLI commands for create/list/show/link

Tasks:

1. Extend `graph/ops.py` or create `graph/claim_ops.py`.
2. Add typed node support:
   - `claim`
   - `context`
   - `metric`
   - `practice`
   - `failure_mode`
   - `evidence`
3. Add edge relation support:
   - `supports`
   - `contradicts`
   - `refines`
   - `applies_to`
   - `derived_from`
4. Add storage indexes for node and edge retrieval.
5. Add migration adapter from existing `hypothesis` nodes to `claim` nodes.

Definition of done:

- Claims and their typed relationships can be persisted and retrieved deterministically.

### Module D. Conflict Resolution Engine

Goal:

- Make conflicting knowledge explicitly governable.

Deliverables:

- Conflict detector
- Conflict record format
- Routing rules for conditional knowledge, tradeoffs, and replay

Tasks:

1. Create `graph/conflicts.py`.
2. Implement context mismatch detection.
3. Implement metric mismatch detection.
4. Implement evidence conflict detection.
5. Produce conflict records with:
   - conflict type
   - involved claims
   - confidence / severity
   - recommended resolution path
6. Integrate evidence conflict with `cx_replay`.

Definition of done:

- Contradictory claims produce explicit conflict records and recommended governance actions.

### Module E. Pattern Distillation Engine

Goal:

- Distill multiple claims into patterns and principles.

Deliverables:

- Claim clustering
- Pattern candidate generation
- Principle candidate generation
- Distillation report artifact

Tasks:

1. Create `distill/pattern_engine.py`.
2. Implement clustering by shared context, metric, and practice.
3. Generate `PATTERN_CANDIDATE` output.
4. Generate `PRINCIPLE_CANDIDATE` output.
5. Link pattern candidates back to source claim graph nodes.
6. Add tests for multi-claim synthesis behavior.

Definition of done:

- Multiple related claims can produce a traceable pattern candidate and principle candidate.

### Module F. Validation Layer Upgrade

Goal:

- Validate claims and principles directly.

Deliverables:

- Claim/principle validation target model
- Validation adapters for Mode A / B / C
- Evidence linkage back to claim graph

Tasks:

1. Extend VP initialization to support `claim_id` and `pattern_id`.
2. Update AVL template to include `claim_reference` and `claim_graph_node`.
3. Store validation outcome against claim/principle targets.
4. Add automated metrics validation scaffold for Mode C.
5. Add aggregation logic across multiple evidence packs for a claim/principle target.

Definition of done:

- Validation artifacts can point to a claim or principle without relying on free-form hypothesis text.

### Module G. Promotion and Governance

Goal:

- Promote validated claims and principles into governed knowledge.

Deliverables:

- Unified promotion decision engine
- Claim-aware promotion report
- v5.0 LTI knowledge typing
- RTI routing based on governance impact and conflict state

Tasks:

1. Refactor promotion logic so report and router share one decision source.
2. Accept `validated_claim` and `validated_principle` as promotion inputs.
3. Extend `LTI_NODE` with `knowledge_type`.
4. Support values:
   - `pattern`
   - `principle`
   - `decision_rule`
   - `evaluation_standard`
5. Add RTI routing conditions for:
   - governance impact
   - unresolved evidence conflict
   - rule contradictions

Definition of done:

- Promotion output preserves what kind of knowledge was promoted and why.

### Module H. Migration and Documentation

Goal:

- Upgrade safely without breaking current operations.

Deliverables:

- Migration scripts
- Backfill utilities
- documentation updates
- acceptance checklist

Tasks:

1. Add migration script from hypothesis graph nodes to claim graph nodes.
2. Add backfill script for existing AVL evidence packs.
3. Add compatibility notes for v4.1-to-v5.0 mixed mode.
4. Update `docs/CURRENT_ARCHITECTURE.md` only after minimum v5.0 baseline is implemented.
5. Add v5.0 architecture acceptance tests.

Definition of done:

- Existing repo data remains usable while new v5.0 records are introduced.

## 6. Recommended Delivery Phases

### Phase 0. Foundation

Objective:

- Establish contracts and storage without breaking the current flow.

Tasks:

- Module A complete
- Add empty scaffolds for Modules B, C, D, E
- Add feature flags for v5.0 paths

Exit criteria:

- Contracts exist
- Tests pass
- No existing CLI regressions

### Phase 1. Claim Ingestion MVP

Objective:

- Produce claim objects from selected source types.

Tasks:

- Module B complete for newsletter + RSS
- Initial claim storage
- CLI support for claim ingestion

Exit criteria:

- One newsletter item can become claim objects
- Claims can be persisted and reviewed

### Phase 2. Claim Graph MVP

Objective:

- Persist claims in a typed graph.

Tasks:

- Module C complete
- Claim node/edge CLI
- Backfill adapter from current graph hypotheses

Exit criteria:

- Claim graph queries work locally
- Existing graph records can be mapped forward

### Phase 3. Conflict Governance MVP

Objective:

- Detect contradictions and route them.

Tasks:

- Module D complete
- Replay trigger integration for evidence conflicts

Exit criteria:

- A pair of contradictory claims yields a stored conflict artifact

### Phase 4. Pattern Distillation MVP

Objective:

- Turn claims into reusable governed knowledge candidates.

Tasks:

- Module E complete
- Add pattern/principle traceability

Exit criteria:

- Multi-claim input can produce pattern and principle candidates

### Phase 5. Validation and Promotion Upgrade

Objective:

- Move governance from hypothesis-centric to claim-centric promotion.

Tasks:

- Module F complete
- Module G complete

Exit criteria:

- A validated claim or principle can be promoted into typed LTI knowledge

### Phase 6. Migration and Cutover

Objective:

- Make v5.0 the active architecture.

Tasks:

- Module H complete
- Update architecture pointer
- Add release checklist

Exit criteria:

- `docs/CURRENT_ARCHITECTURE.md` points to v5.0 implementation baseline

## 7. Directly Actionable Task Backlog

### P0

1. Add `CLAIM_OBJECT` contract and schema.
2. Add `CLAIM_EDGE` contract and schema.
3. Extend AVL evidence pack schema with `claim_reference` and `claim_graph_node`.
4. Extend `LTI_NODE` with `knowledge_type`.
5. Create append-only claim store and tests.

### P1

1. Implement newsletter-to-claim extraction.
2. Implement RSS item-to-claim extraction.
3. Add `pmos claim ingest` CLI.
4. Add claim graph node and edge persistence.
5. Add claim graph smoke tests.

### P2

1. Implement context conflict detection.
2. Implement metric conflict detection.
3. Implement evidence conflict detection.
4. Integrate evidence conflict with replay routing.
5. Add conflict artifact storage and tests.

### P3

1. Build pattern clustering engine.
2. Build principle candidate generator.
3. Link pattern outputs to source claims.
4. Add distillation report artifact.
5. Add multi-claim end-to-end tests.

### P4

1. Refactor VP to target claim/principle IDs.
2. Refactor promotion report to use claim/principle targets.
3. Unify promotion decision engine and manual router.
4. Add typed LTI promotion.
5. Add RTI routing for unresolved conflicts.

### P5

1. Add migration from `hypothesis` graph nodes to `claim` graph nodes.
2. Add compatibility adapters for v4.1 mixed mode.
3. Add v5.0 acceptance suite.
4. Update docs pointer and release notes.

## 8. Risks and Controls

### Risk 1. Overwriting v4.1 semantics too early

Control:

- Keep v5.0 paths behind new modules and feature flags until promotion is claim-aware end to end.

### Risk 2. Claim extraction quality is too weak

Control:

- Start with deterministic heuristics and strong tests before adding more automation.

### Risk 3. Promotion logic splits further

Control:

- Enforce a single decision function shared by report generation and routing.

### Risk 4. Migration creates duplicate or untraceable knowledge

Control:

- Use deterministic IDs and source-to-claim trace fields from the start.

## 9. Recommended First Sprint

Sprint objective:

- Establish the minimum v5.0 foundation without changing active governance behavior.

Sprint scope:

1. Add `CLAIM_OBJECT`, `CLAIM_EDGE`, and `knowledge_type` contract changes.
2. Add claim store and tests.
3. Implement newsletter-to-claim extraction MVP.
4. Add AVL fields for `claim_reference` and `claim_graph_node`.
5. Add a basic `pmos claim` CLI namespace.

Expected outcome:

- The repo remains v4.1 operationally, but claim-governed v5.0 data starts existing as a first-class layer.

## 10. Implementation Order Summary

Build in this order:

1. Contracts
2. Claim ingestion
3. Claim graph
4. Conflict resolution
5. Pattern distillation
6. Validation upgrade
7. Promotion upgrade
8. Migration and cutover

Do not start with pattern distillation or promotion refactors before contracts and claim storage exist.
