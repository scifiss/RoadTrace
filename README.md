# RoadTrace

**From code history to living roadmap.**

RoadTrace turns a public GitHub repository into an auditable view of what the
software does, how it is organized, and when its major capabilities appeared.
Executable source structure is treated as the strongest evidence; tests, history,
configuration, and documentation support the interpretation.

V0.1 is a complete local vertical slice: paste a public GitHub URL, analyze it,
inspect the versioned-lens reverse roadmap, explore bounded code/capability graphs,
and open any inferred capability to see the evidence behind it.

## What works

- Strict validation for `https://github.com/{owner}/{repo}` public URLs.
- Bounded, temporary Git clones with no prompts, hooks, or submodules.
- Python extraction through the standard AST and JS/TS extraction through
  Tree-sitter: modules, classes, functions, methods, schemas, UI components, API
  routes, imports, calls, inheritance, and test relationships.
- Structural/dependency graph plus explicitly best-effort workflow and data-flow
  projections.
- Bounded Git history sampled across the reachable project span, changed paths,
  tags, change-type heuristics, and first/last capability estimates.
- Source-independent observations, relationship-backed mechanism clusters, and
  open-world semantic capability synthesis.
- Grounded capability hierarchy, traits, and primary/secondary projections under a
  configurable, versioned default set of ten analysis lenses.
- Explicit `DISCOVERED` → `PRODUCTIONIZED` maturity states backed by named evidence
  dimensions—never an invented completion percentage.
- Optional evidence-bounded semantic label refinement through the official OpenAI
  Python SDK and Responses API. Analysis remains fully functional without a key.
- SQLite result persistence and a small REST API.
- Responsive React workspace with honest summary metrics, a searchable capability
  constellation, a compact lens overview, reverse-roadmap filters, focused
  one/two-hop graph exploration, and an evidence drill-down panel. Full bounded graph
  projections remain available as an explicit opt-in.

## Prerequisites

- Python 3.12+
- Git 2.40+
- Node.js 24 LTS (Node 22 LTS also works with the declared frontend toolchain)

RoadTrace runs only its own dependencies. It never installs dependencies or runs
scripts, tests, interpreters, or build tools from an analyzed repository.

## Run locally

From the repository root, create the backend environment and install the frontend:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
cp .env.example .env
cd frontend
npm install
cd ..
```

Then start both the API and web client with:

```bash
./scripts/dev.sh
```

For manual development, run `uvicorn app.main:app --app-dir backend --reload
--port 8000` from the repository root and `npm run dev` from `frontend/` in a
second terminal. Running Vite by itself displays the interface, but repository
analysis cannot work without the API on port 8000.

Open `http://localhost:5173`, paste a public repository URL, and select **Analyze
repository**. Vite proxies `/api` to `http://localhost:8000` in development.

The backend API documentation is available at `http://localhost:8000/docs`.

### Optional development-only local repositories

Private GitHub authentication remains out of scope, but local development can analyze
an existing private worktree through the same static/Git/capability pipeline. Enable
both server access and the optional form input before starting RoadTrace:

```bash
export ROADTRACE_DEV_LOCAL_REPOS=true
export ROADTRACE_LOCAL_REPO_ROOTS=/home/rebecca/projects/geoworld-ss
export VITE_ENABLE_LOCAL_REPOS=true
./scripts/dev.sh
```

Then enter the absolute Git top-level path, for example
`/home/rebecca/projects/geoworld-ss/geoworld`. Multiple allowed roots use the platform path
separator (`:` on Linux). RoadTrace resolves the requested path and roots, rejects
symlink/path traversal outside them, requires the exact Git top-level directory, and
never executes repository code. The feature is disabled and absent from the form by
default; production must opt in explicitly to both controls.

### Optional semantic refinement

Deterministic mode is the default. To enable semantic refinement, export both:

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='your-responses-compatible-model'
```

The model name is never hard-coded. RoadTrace sends a bounded digest of existing
candidate capabilities, behavior summaries, normalized observations, entities, and
allowed evidence IDs—not whole repository contents. Pydantic validates the structured
response, and updates with unknown candidate, behavior, evidence, or lens IDs are
discarded. Any SDK/API failure falls back to the deterministic result and adds a
visible warning.

### Optional lens projection

The default lens set is versioned with every analysis result. To replace or extend
the projection without changing inference code, point `ROADTRACE_LENS_CONFIG` at a
validated JSON `LensSet`. Lenses have stable IDs, labels, descriptions, versions, and
`ACTIVE` or `DEPRECATED` status. A lens organizes discovered capabilities; it is not a
dictionary of allowed product concepts.

## Tests and checks

With the backend environment active:

```bash
python -m pytest backend/tests
ruff check backend
ruff format --check backend
```

Frontend:

```bash
cd frontend
npm test
npm run lint
npm run build
```

The backend suite creates temporary repositories and never executes them. It includes
a six-commit end-to-end history plus six unseen domains, an identifier-obfuscation
pair, a structure-versus-lexicon ablation, misleading-documentation cases, a custom
versioned lens set, and provenance/confidence invariants. This makes the reasoning
regression reproducible without network access.

See [the reasoning architecture](docs/REASONING_ARCHITECTURE.md),
[the pre-change audit](docs/REASONING_ARCHITECTURE_AUDIT.md), and
[the JobTracker validation](docs/JOBTRACKER_VALIDATION.md).

## REST API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Process health |
| `POST` | `/api/analyses` | Analyze `{ "repository_url": "…" }` |
| `GET` | `/api/analyses` | List recent persisted analyses |
| `GET` | `/api/analyses/{id}` | Retrieve a complete evidence-backed result |

The POST request is intentionally simple and synchronous from the client's point of
view. The server performs blocking analysis in a worker thread. A durable background
job boundary is a post-V0.1 scaling task.

## Architecture

The backend keeps framework-free domain models at its center:

```text
frontend/                    React + TypeScript + Vite
backend/app/
  api/                       REST boundary
  ingestion/                 URL validation, safe clone, bounded inventory
  analysis/                  ASTs, Tree-sitter, history, inference, graphs
  llm/                       optional evidence-bounded semantic refiner
  storage/                   SQLite result adapter
  domain.py                  observed/inferred/visualization contracts
  service.py                 end-to-end orchestration
```

See [the V0.1 architecture](docs/V0.1_ARCHITECTURE.md) for data-layer separation,
pipeline details, extension seams, security invariants, and approximations. Progress
against the implementation brief is tracked in [the milestone checklist](docs/V0.1_MILESTONES.md).

## Security boundary

- By default only exact public GitHub HTTPS repository URLs are accepted. Credentials, ports,
  alternate hosts, SSH/file URLs, local paths, query strings, fragments, encoded
  paths, and additional URL segments are rejected.
- Git is invoked with argument arrays and `shell=False`. Global/system Git config,
  prompts, hooks, LFS smudging, local file transport, and submodules are disabled.
- Clone time/depth/bytes, repository bytes, source bytes, file count, per-file bytes,
  history count, graph nodes, and workflow depth are configurable.
- File walking does not follow symlinks and ignores VCS data, dependencies, virtual
  environments, vendor/build output, generated bundles, binaries, and lockfiles.
- Temporary repositories are removed on both success and failure.
- Development-only local input requires an explicit enable flag and resolved allowed
  roots; traversal, symlink escapes, non-Git paths, and repository subdirectories are
  rejected.

## Known V0.1 limitations

- Static call resolution is lexical and conservative; it is not full type-aware,
  interprocedural control-flow analysis. Workflow/data projections say **inferred**.
- The partial, depth-bounded clone can miss capability origins in repositories with
  more commits than the configured history depth; RoadTrace reports that boundary.
- GitHub pull requests, issues, and release descriptions are not fetched; local Git
  commits and tags are used.
- Deterministic clustering is evidence-backed but conservative in unfamiliar domains.
  Optional semantics can improve naming, merging, categories, and hierarchy but
  cannot create unsupported capabilities.
- Synchronous HTTP results and SQLite target local/single-user operation. Large-scale
  concurrency, caching, cancellation, and durable jobs are not included.
- Private GitHub authentication and future plan-vs-actual comparison are explicitly
  outside V0.1; private worktrees are available only through the opt-in local
  development boundary above.
