# RoadTrace benchmark architecture

RoadTrace evaluation is corpus-based. No repository, product vocabulary, or
hand-authored roadmap is a reference architecture for the inference engine. The
benchmark asks whether the same evidence contracts and reasoning invariants hold
across heterogeneous software.

## Corpus shape

The local deterministic corpus covers these software classes:

| Corpus class | Representative mechanism pressure |
| --- | --- |
| Interactive application | UI actions, filtering, state, persistence, and computed output |
| CRUD / administrative system | Record search, mutation, validation, and persistence |
| Backend / service | Endpoint, request validation, authorization, service calls, and audit state |
| Scientific / numerical computation | Boundary conditions, iterative computation, and result export |
| ML / inference | Model loading, feature transformation, prediction, and explanation |
| Automation / event-driven system | Event handling, queues, retries, and notifications |
| Developer tool / CLI | Entry points, dependency analysis, and report generation |
| Data-processing system | Ingestion, normalization, aggregation, and format conversion |
| Library / framework | Registration, composition, extension points, and invocation |
| Unfamiliar domain software | Domain-local entities combined through computation and data flow |

Fixtures are deliberately small enough to inspect and are never executed by
RoadTrace. The multi-commit end-to-end fixture additionally exercises API, UI,
configuration, tests, persistence, and temporal evolution. Real repositories may be
used as unprivileged external validation inputs, but they receive no special weight,
phrases, aliases, or exact expected capability list.

## Evaluation invariants

Tests allow reasonable alternative terminology. They evaluate properties rather than
requiring an exact capability string:

- **Evidence grounding:** every observation, behavior, trait, and capability resolves
  to valid observed evidence.
- **Structural cohesion:** relationship-backed neighborhoods affect behavior
  confidence and preserve cooperating entities.
- **Behavior separation:** unrelated clusters do not collapse solely because they
  share a generic operation word.
- **Capability abstraction:** implementation artifacts do not dominate the capability
  graph, and capability count remains below raw entity count.
- **Duplicate control:** normalized capability names are unique within one result.
- **Unsupported-capability control:** document claims and test prose cannot establish
  implementation without supporting code.
- **Hierarchy integrity:** parent/child references resolve and remain acyclic.
- **Temporal consistency:** first/last observations and state transitions follow Git
  chronology and retain commit evidence.
- **Semantic label quality:** labels retain a repository-local domain concept plus a
  supported operation or behavior at a roadmap-meaningful level.
- **Identifier robustness:** obfuscation may reduce label precision but must not erase
  observable behavior, topology, provenance, or lens overlap.

These are invariant gates, not fabricated aggregate scores. Reporting can expose raw
counts and failures; a composite benchmark score should wait for a calibrated corpus
and defensible weighting method.

## Ablations and adversarial cases

The suite includes:

- a paired meaningful/obfuscated identifier fixture with unchanged topology and UI or
  storage semantics;
- a structure-versus-lexicon ablation that removes graph relationships and verifies a
  measurable loss of behavior confidence;
- misleading documentation in both directions: unsupported prose does not create a
  capability, while undocumented implementation remains discoverable;
- replaceable and deprecated lens definitions; and
- invalid LLM evidence, behavior, and lens references.

## Rules for extending the corpus

1. Add new domains as held-out evidence, not as sources for product phrase rules.
2. Express expectations as semantic alternatives and graph/provenance invariants.
3. Never add a production alias merely to make one fixture pass.
4. Record known ambiguity rather than silently lowering the abstraction requirement.
5. Prefer improvements to relationships, data flow, state sharing, framework wiring,
   and temporal co-change before expanding lexical cues.

The next benchmark increment should add larger held-out repositories and annotate
behavior boundaries independently of capability wording. That will support precision,
recall, separation, and calibration studies without turning human labels into a fixed
ontology.
