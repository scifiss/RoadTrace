# Product-semantic capability inference

RoadTrace separates implementation structure from product meaning. Files, symbols,
routes, schemas, components, and imports remain visible in the Code Graph. A
Capability Graph node must answer: **what meaningful thing can this software do
because this implementation exists?**

## Why the former pipeline produced generic nodes

The original `CapabilityInferer` applied a small set of filters directly to a flat
entity inventory. UI components became `User Interface`, endpoints became `API
Surface`, and an unmatched frequent serialization identifier could become an
`Engine`, producing labels such as `Json Engine`.

The failure was architectural: no normalized observation layer, no relationship-backed
mechanism cluster, and no behavior representation stood between code entities and
capabilities. The optional model could rename candidates but could not recover missing
behavior structure.

## Current contract

```text
Evidence → Observation → Entity/relationship graph → Mechanism cluster
         → BehaviorSummary → Capability → Versioned lens projection
```

The deterministic engine contains reusable operation roles, not a catalog of product
phrases. Domain terms come from the repository's own implementation and observable
surfaces. A behavior must be backed by cooperating implementation or an observable
UI/API/schema boundary. Documentation claims never seed implemented capabilities;
tests attach to the code they exercise.

Every capability preserves evidence, observation, behavior, entity, relationship,
and temporal references plus separate evidence, behavior, semantic, and temporal
confidence. Exact duplicates merge, compound workflows may produce parent/child
capabilities, and cross-cutting meaning is represented with one primary and optional
secondary lens IDs rather than duplicate nodes.

The default ten-lens set is a replaceable, versioned projection. It is not an
ontology. An unfamiliar product concept can still be discovered without first adding
it to a RoadTrace dictionary.

## Optional semantic refinement

When configured, the LLM receives only existing behavior-backed candidates and a
bounded structured evidence digest. It may improve naming, descriptions, hierarchy,
deduplication, and active-lens assignment. Pydantic and subset checks reject unknown
candidates, behavior IDs, evidence IDs, and lenses. It cannot invent implemented
capabilities.

The full contracts, extension rules, temporal model, evaluation strategy, and known
limits are documented in [REASONING_ARCHITECTURE.md](REASONING_ARCHITECTURE.md). The
pre-change footprint is recorded in
[REASONING_ARCHITECTURE_AUDIT.md](REASONING_ARCHITECTURE_AUDIT.md).
