# RoadTrace reasoning architecture

## Purpose and invariants

RoadTrace reconstructs what software can do from implementation evidence. It is a
static-analysis and evidence-reasoning system, not a product-phrase classifier. Its
central question is:

> What meaningful thing can this software do because this implementation exists?

The following invariants apply in deterministic and semantic modes:

- source implementation is the strongest evidence of implemented behavior;
- files, functions, components, routes, and parsers belong in the Code Graph, not
  automatically in the Capability Graph;
- documentation may corroborate interpretation but cannot establish implementation;
- tests verify behavior but do not replace the implementation they target;
- every inferred capability retains a traversable evidence chain;
- lenses project discovered meaning and never define the allowed product vocabulary;
- uncertainty is represented explicitly rather than hidden in a single score; and
- repository code is never imported, installed, built, or executed.

Planning and future-state comparison remain outside this architecture.

## End-to-end pipeline

```text
Repository sources and Git history
  → bounded observed evidence
  → source-independent observations
  → code entity/relationship graph
  → relationship-backed mechanism clusters
  → behavior summaries
  → open-world semantic abstraction
  → capability hierarchy and traits
  → versioned lens projection
  → temporal capability states
  → graph/timeline presentation projections
```

Each stage has a narrower contract than the previous one. Parser adapters do not
create capabilities, and lens configuration does not alter the observed facts.

## 1. Sources, evidence, and observations

Language adapters extract bounded facts from Python ASTs, JavaScript/TypeScript
Tree-sitter syntax, configuration, documentation, and Git. Evidence records retain
their source kind, path, line, symbol, revision, timestamp, and human-readable label.

`Observation` is the source-independent boundary. It normalizes parser-specific facts
into kinds such as structure, interaction, data flow, persistence, transformation,
validation, external call, test behavior, configuration, document claim, and temporal
change. An observation must cite at least one evidence ID. Useful semantic inputs
include identifiers, UI text and form labels, routes, schema fields, storage keys,
environment variables, meaningful constants, errors, tests, imports, and database or
file operations. Noise and generated/trivial strings are discarded by the adapters.

Documentation is normalized as `DOCUMENT_CLAIM`. It is intentionally excluded from
the implementation evidence that seeds mechanisms or capabilities. A later semantic
step may use it to choose terminology or explain setup only when code-backed behavior
already exists.

## 2. Entity and relationship graph

`CodeEntity` represents files, modules, classes, functions, methods, API endpoints,
UI components, schemas, tests, configuration, and external modules. `CodeRelationship`
represents containment, calls, rendering, exposure, reads/writes, imports/dependencies,
instantiation, inheritance, and test targets.

Relationships are resolved conservatively and carry confidence plus an `inferred`
flag. This graph is valuable on its own, but it is still implementation structure.
RoadTrace does not promote an entity simply because it is common, central, or named
`engine`, `API`, `JSON`, or `main`.

## 3. Mechanism clustering and behavior synthesis

The deterministic engine starts with file neighborhoods and observable boundary
entities, then expands over strong relationships such as calls, renders, exposes,
reads, writes, instantiates, and tests. Near-identical neighborhoods merge; distinct
workflows remain separate. A cluster needs multiple executable entities or an
observable UI/API/schema boundary. Tests attach to the implementation they exercise
and do not create product clusters on their own.

RoadTrace recognizes reusable operation roles—not product names—including search,
matching, scoring, extraction, generation, computation, persistence, import/export,
validation, automation, inference, visualization, management, integration, and data
transformation. Repository-local terms supply the domain concept. The combination
produces an intermediate `BehaviorSummary`, for example a local concept such as
`inventory` plus a persistence mechanism.

A behavior records:

- name and description;
- mechanism types and local semantic terms;
- supporting entities and relationships;
- observation and evidence IDs;
- observable inputs and outputs;
- UI surfaces, API paths, and tests;
- parent behavior name where a compound workflow can be decomposed; and
- evidence, behavior, semantic, and temporal confidence dimensions.

This is deliberately open-world. Adding a scientific, administrative, ML, automation,
or developer-tool domain does not require adding its product phrases to RoadTrace.

## 4. Semantic abstraction and capabilities

Capabilities aggregate one or more behaviors at a roadmap-meaningful level. Compound
UI-centered clusters can become a parent management capability with independently
observable persistence, validation, search, import, or export children. Exact
normalized duplicates merge while retaining aliases and combined provenance. Missing
or cyclic parents are removed.

The full explainability path is:

```text
ObservedEvidence
  → Observation
  → CodeEntity / CodeRelationship
  → BehaviorSummary
  → Capability
```

Capabilities also retain maturity signals, first/last dates, commit hashes, traits,
knowledge-quality descriptors where relevant, and multidimensional confidence.
`category` fields remain temporary API compatibility mirrors of lens labels; inference
uses stable lens IDs.

## 5. Versioned analysis lenses

The default `roadtrace-default` lens set is version `2.0`:

| Lens ID | Default label | Projection concern |
| --- | --- | --- |
| `experience-interaction` | Experience & Interaction | Human journeys and presentation |
| `domain-capability` | Domain Capability | Central domain behavior and computation |
| `data-state` | Data & State | Persistence, schemas, ingestion, and state |
| `knowledge-intelligence` | Knowledge & Intelligence | Knowledge, retrieval, models, and inference |
| `automation-agency` | Automation & Agency | Triggered, scheduled, or orchestrated work |
| `interfaces-ecosystem` | Interfaces & Ecosystem | APIs, protocols, services, and integrations |
| `trust-governance` | Trust & Governance | Safety, validation, privacy, access, and policy |
| `quality-evaluation` | Quality & Evaluation | Verification, benchmarks, and failure behavior |
| `operations-scale` | Operations & Scale | Runtime, deployment automation, and scale |
| `distribution-ecosystem` | Distribution & Ecosystem | Packaging, channels, plugins, and extensions |

Each capability has one `primary_lens` and may have secondary lenses when evidence is
cross-cutting. The same capability is not duplicated under several lenses.

A `LensSet` is validated, versioned configuration. Lenses have stable IDs, labels,
descriptions, aliases/signals, their own version, and an `ACTIVE` or `DEPRECATED`
status. `ROADTRACE_LENS_CONFIG=/absolute/path/lenses.json` replaces the default
projection. Deprecated lenses remain representable but receive no new projections.
Teams may add or replace lenses without editing the behavior engine.

### Data is not knowledge

`Data & State` answers what information exists, where it enters, how it moves or is
transformed, and where it is stored. `Knowledge & Intelligence` answers what semantic
relationships, learned models, rules, retrieval processes, or inferences the system
can use. One artifact may support both roles: stored vector chunks are data, while
retrieval over their semantic representation is knowledge behavior. Primary and
secondary lenses retain that overlap without declaring the concepts interchangeable.

## 6. Traits and knowledge quality

Traits describe supported facets without turning every facet into another hierarchy
node. Current traits are derived from evidence-backed mechanisms such as interactive,
persistent, validated, externally integrated, automated, inferred, and evaluated.
Every trait cites evidence and has its own confidence.

Knowledge-oriented behavior is not summarized as one fake percentage. Where evidence
supports it, `KnowledgeQuality` describes breadth, depth, executability, grounding,
freshness, and the evidence IDs behind that description. Absent evidence stays absent.

## 7. Time and capability state

Git history contributes changed paths, subjects, timestamps, and change types without
checking out or executing historical code. Evidence paths bound first and last
observed capability changes. Timeline events retain commit/evidence provenance.

`CapabilityState` explicitly records supported transitions such as `INTRODUCED`,
`STRENGTHENED`, `REFACTORED`, and `REMOVED`. The schema can represent split, merge,
and deprecation, but deterministic mode does not claim those states without sufficient
historical evidence. Temporal confidence is kept separate from semantic confidence,
especially when clone depth limits the visible origin.

## 8. Optional LLM refinement boundary

Deterministic inference always produces a complete result. If `OPENAI_API_KEY` and
`OPENAI_MODEL` are configured, the semantic refiner receives a bounded structured
digest containing:

- the active lens definitions;
- existing behavior-backed capability candidates;
- bounded observations, entities, inputs/outputs, UI/API surfaces, and test labels;
- the exact allowed behavior and evidence IDs for each candidate.

Pydantic validates structured output. The model may rename, describe, merge, assign
an active lens, or establish hierarchy among supplied candidates. It cannot create a
new candidate, invent an evidence/behavior ID, select an unknown/deprecated lens, or
change implementation and maturity facts. Invalid output is discarded; transport,
SDK, or validation failures return the deterministic result with a warning.

## 9. Safe private-worktree validation

Developer-only local analysis uses the same file, Git, observation, mechanism, and
capability pipeline as a GitHub clone. Enable it explicitly:

```bash
cd /home/rebecca/projects/RoadTrace
export ROADTRACE_DEV_LOCAL_REPOS=true
export ROADTRACE_LOCAL_REPO_ROOTS=/home/rebecca/projects
export VITE_ENABLE_LOCAL_REPOS=true
./scripts/dev.sh
```

Then enter the exact absolute Git top-level path, for example
`/home/rebecca/projects/geoworld-ss/geoworld`. Multiple roots are colon-separated on
Linux. The server resolves symlinks, checks canonical containment beneath an allowed
root, requires the requested path to equal Git's top-level worktree, and rejects local
input unless the gate and roots are configured. Production defaults remain disabled.

For backend-only validation, omit `VITE_ENABLE_LOCAL_REPOS` and POST the path as
`repository_url` while the development-gated server is running. Local analysis never
executes repository code.

## 10. Evaluation strategy and current limits

The regression suite checks a multi-commit end-to-end repository, six unseen domains,
identifier obfuscation, graph-relationship ablation, misleading documentation in both
directions, configurable/deprecated lenses, LLM evidence bounds, local-path security,
and complete provenance/confidence references. JobTracker is an important regression
case, not a source of vocabulary.

Current limits are explicit:

- relationship resolution is lexical and does not model dynamic dispatch or framework
  magic with compiler precision;
- unfamiliar domains can still receive awkward deterministic wording even when the
  evidence grouping is correct;
- identifier obfuscation preserves visible/storage concepts and structural grouping,
  but can change the chosen mechanism when no semantic code names remain;
- monolithic modules can over-connect unrelated behaviors;
- role scoring is heuristic and can confuse loading a model with persistence or
  aggregating metrics with scoring;
- deep split/merge histories require stronger historical identity tracking; and
- optional LLM refinement is bounded by deterministic candidate recall.

These are reasons to improve observation adapters, relationship resolution, and
abstraction scoring—not reasons to add repository-specific phrase catalogs.

Future sources such as issues, pull requests, telemetry, designs, and external
documentation should enter through new source adapters and normalize into the same
evidence/observation contracts. A related product could project the shared reasoning
layers into a requirement or knowledge graph without changing RoadTrace into a
generic-platform UI today.
