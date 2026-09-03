# Reasoning architecture audit

Date: 2026-09-02

> **Historical engineering record:** this document describes superseded inference
> behavior observed before the generalized reasoning refactor. It is not the current
> RoadTrace architecture or product narrative. See
> [REASONING_ARCHITECTURE.md](REASONING_ARCHITECTURE.md) for the active design.

This audit records the state of the capability-inference implementation immediately
before the source-independent reasoning correction. It evaluates both the older
`Json Engine` implementation and the later benchmark-tuned semantic layer.

## 1. Current pipeline

The current runtime pipeline is:

```text
GitHub clone or gated local worktree
→ bounded file inventory
→ Python AST / JS+TS Tree-sitter entities and relationships
→ semantic strings attached to entity metadata
→ connected components and bounded relationship neighborhoods
→ named BehaviorPattern matches plus an action/noun fallback
→ BehaviorSummary
→ Capability grouped by fixed CanonicalCategory and name
→ Git path-to-commit timeline projection
→ optional evidence-bounded LLM relabel/merge pass
```

The preceding refactor made real improvements: it stopped mapping every symbol
directly to a capability, introduced `BehaviorSummary`, made relationships influence
selection, captured more code evidence, preserved evidence IDs, and constrained LLM
updates. However, the semantic abstraction is still dominated by a large phrase
catalogue in `analysis/behaviors.py`.

## 2. Footprint of previous benchmark guidance

### Benchmark-specific

The deterministic layer contained final capability phrases, required token groups,
parent/child expectations, aliases, and semantic merge rules copied from expected
outputs for individual validation repositories. Tests then recreated those same
domains and asserted exact names and parents. Although the outputs looked plausible,
the benchmark had become an implicit product ontology.

The LLM prompt correctly named generic implementation artifacts such as `JSON Engine`
and `API Surface` as anti-patterns, but the deterministic candidates supplied to it
were already shaped by the fixed catalogue. All repository-derived product phrases,
normalization aliases, and exact hierarchy expectations therefore needed removal.

### Domain-biased

Other fixed phrases attempted to recognize particular scientific, mapping, archive,
and tracing domains. Some underlying mechanisms—graph query, simulation, provenance,
orchestration, import, and export—are defensible general concepts, but phrase-specific
required-token rules are domain recognizers rather than source-independent inference.
They should not remain in the core catalogue.

### General mechanisms worth retaining in generalized form

- state persistence and database interaction
- import/export and transformation
- authentication and request/input constraints
- automated tests and evaluation
- deployment, continuous integration, and packaging
- external model/service invocation
- orchestration and triggering
- UI interaction and API exposure

These should become evidence roles, observations, mechanism types, lens-placement
signals, or traits. They should not be a closed list of final capability names.

## 3. Lexical versus structural signals

### Lexical signals currently used

- entity, qualified, file, called-symbol, field, route, and test names
- selected JSX strings, labels, constants, storage keys, environment variables, and
  error messages
- hand-authored token aliases, stop words, action groups, required phrase groups, and
  phrase-to-category rules
- phrase normalization for selected duplicate capability names

### Structural signals currently used

- IMPORTS, CALLS, CONTAINS, INSTANTIATES, RENDERS, EXPOSES, TESTS, and related edges
- bounded two-hop neighborhoods excluding import edges during pattern satisfaction
- interface and test neighbors
- connected uncovered implementation components for fallback behavior
- entity/evidence aggregation and path-based Git association

Topology now affects which evidence can cooperate, but vocabulary still decides
whether almost every behavior exists and what it is called. Removing relationships
would reduce locality, yet most named output would still be determined by the phrase
catalogue. The architecture is therefore structurally assisted but predominantly
lexical.

## 4. Genuinely general parts

- bounded, non-executing source acquisition and inventory
- adapter-based Python and JS/TS parsing
- typed code entities and relationships
- precise source locations and evidence IDs
- Git commits as a separate temporal evidence stream
- explicit behavior-to-entity/evidence links
- safe fallback when no LLM is configured
- structured Pydantic LLM responses with evidence/behavior subset validation
- support for primary and secondary placement (although currently enum-bound)
- gated local-repository acquisition with resolved-root containment

These should be migrated rather than rewritten.

## 5. Parts to remove or generalize

1. Remove repository/domain phrase patterns from the reasoning core.
2. Replace fixed capability names with graph-induced mechanisms whose labels are
   composed from observed domain concepts and operation roles.
3. Split raw evidence from normalized observations; semantic strings in entity
   metadata are not a sufficient observation layer.
4. Replace the fixed `CanonicalCategory` dependency with a versioned `LensSet` loaded
   from a replaceable definition.
5. Model document statements explicitly as claims and prevent claims from satisfying
   implementation requirements.
6. Add traits/facets independent of lens hierarchy.
7. Split confidence into evidence, behavior, semantic, and temporal dimensions.
8. Add lightweight capability states/versions so temporal evolution is not limited to
   `first_seen` and `last_changed`.
9. Make relationship topology and operation/data-flow roles contribute independently
   of identifier quality.
10. Replace exact single-domain fixture assertions with diversified semantic invariants.

## 6. Proposed minimal refactor

The minimal correction keeps the parser, service, storage, and frontend boundaries:

```text
SourceAdapter output
→ Evidence records
→ ObservationNormalizer
→ typed Entity/Relation graph
→ topology-led mechanism clusters
→ open-world semantic abstraction
→ configurable lens projection
→ temporal states and provenance
```

Implementation increments:

- introduce `Observation`, `LensDefinition`, `LensSet`, `CapabilityTrait`,
  `ConfidenceDimensions`, and `CapabilityState` contracts;
- normalize storage, UI action, route, test, external call, transformation, validation,
  configuration, and document-claim evidence into observations;
- seed mechanism clusters from entry points, UI/API boundaries, state operations,
  test targets, and cohesive internal components;
- derive operation roles from topology and syntax, then choose domain terms from
  evidence concentration rather than repository-specific dictionaries;
- emit conservative open-world names such as `<domain concept> <operation>` and allow
  the LLM to improve names only within the same evidence/observation/behavior bounds;
- assign lenses in a separate configurable projection step;
- retain the current `category` JSON field temporarily as a UI compatibility alias for
  `primary_lens` while removing enum dependence from the reasoning core;
- add diversified fixtures and explicit structure/lexicon ablation diagnostics.

## 7. Required data-model changes

- Evidence gains source kind/revision provenance and document-claim distinction.
- Observations become first-class and reference evidence IDs and entity IDs.
- Behaviors reference observation IDs and expose mechanism/operation roles.
- Capabilities reference behavior and observation IDs, use string lens IDs, carry
  secondary lenses and traits, and expose differentiated confidence.
- Analysis results contain the active versioned lens set.
- Capability states reference time-bounded evidence and change kinds.
- Category summaries become lens summaries; a compatibility field can avoid a UI
  redesign during migration.

## 8. Migration risks

- Existing SQLite JSON results use enum category labels and lack observations/lenses;
  new fields need defaults and compatibility parsing.
- The frontend assumes a fixed category union and fixed colors/order; it must consume
  lens definitions while retaining a neutral fallback style.
- Open-world deterministic labels will be less polished than repository-tuned labels,
  especially with weak identifiers. That is an honest semantic-confidence reduction,
  not a reason to restore hard-coded expected phrases.
- Graph clustering can over-connect monoliths or split dynamically wired systems.
  Cluster boundaries and ablation tests must stay visible and testable.
- Tests based on exact capability wording will become brittle; assertions should use
  evidence, operation roles, topology, lens/trait placement, and semantic alternatives.
- Temporal state derivation from sampled commits is approximate. The model should
  support states now without presenting unsupported split/merge/removal conclusions.
- A configurable lens file is an input boundary and must be validated, size-bounded,
  uniquely keyed, and fail safely to the versioned default.
