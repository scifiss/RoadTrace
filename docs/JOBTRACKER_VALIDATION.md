# JobTracker reasoning validation

Validation repository: `scifiss/JobTracker` at commit
`2cc1a6398ff284d4fbe920d00b88c5c3e0ba6ba1` (2026-08-08). The repository was
analyzed locally in deterministic mode on 2026-09-03. RoadTrace did not execute its
code. The run completed without warnings.

## Why this regression has two “before” states

The original entity-to-capability implementation returned ten broad nodes from 85
entities and 117 relationships. Its visible failures included `User Interface`,
`User Workflows`, `Json Engine`, `API Surface`, `External Integrations`, and
`Validation & Guardrails`.

The first semantic refactor made JobTracker's output look much better by adding a
large phrase/rule catalog shaped around its expected features. That produced a
convincing list, but it was not evidence of general reasoning: product phrases such
as application tracking, skill-fit assessment, and specific integrations had become
an implicit ontology. The pre-change audit classifies and removes that footprint.

## Generalized deterministic result

The corrected pipeline extracted:

| Record | Count |
| --- | ---: |
| Code entities | 107 |
| Code relationships | 161 |
| Observed evidence records | 251 |
| Normalized observations | 435 |
| Behavior summaries | 25 |
| Capabilities | 25 |
| Capability states | 74 |
| Git commits observed | 6 |

The discovered capability projection was:

- **Domain Capability:** Application Management; Job Extraction; Skill Extraction;
  Skill Matching; Skill Scoring; Skill Job Transformation; Quoted Field Extraction;
  Skill Fit Scoring.
- **Experience & Interaction:** Application Search & Filtering; Job Posting Search &
  Filtering.
- **Data & State:** Application Export; Application Import; Application Persistence;
  Application State; Job Analysis Persistence; Job Limited Text Import; Job Export.
- **Knowledge & Intelligence:** Job Inference.
- **Interfaces & Ecosystem:** Job Integration.
- **Trust & Governance:** Application Validation; Job URL Validation.
- **Quality & Evaluation:** Job Evaluation; URL Evaluation.
- **Operations & Scale:** Continuous Integration.
- **Distribution & Ecosystem:** Package Distribution.

`Application Management` aggregates its search/filtering, persistence, state,
validation, import, and export mechanisms. `Job Integration` aggregates extraction,
inference, validation, persistence, search/filtering, import, and export behavior.
The exact hierarchy remains heuristic, but it is based on cooperating entities and
relationships rather than repository-specific product rules.

## Interpretation

The important improvement is not exact agreement with a hand-authored JobTracker
roadmap. It is that `Json Engine` and `API Surface` disappear through a general
source-independent pipeline, while domain concepts such as application, job, skill,
fit, and URL remain attached to implementation evidence.

The result is materially more useful but not perfect. Labels including `Skill Job
Transformation`, `Quoted Field Extraction`, and `Job Limited Text Import` expose the
current deterministic naming limit. Some expected product groupings—candidate profile,
visualization, referral/notes, Ollama, and Playwright—may appear as evidence or traits
rather than clean top-level capability names. Optional evidence-bounded semantic
refinement is the intended naming/merging improvement; deterministic recall and
provenance remain the hard boundary.

No JobTracker repository name, path, product phrase, or integration name is present in
the inference implementation. JobTracker is now a regression input, not a taxonomy.
