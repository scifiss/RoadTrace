# RoadTrace

**From code history to living roadmap.**

RoadTrace turns a public GitHub repository into an auditable view of what the
software does, how it is organized, and when its major capabilities appeared.
Executable source structure is treated as the strongest evidence; tests, history,
configuration, and documentation support the interpretation.

V0.1 is a complete local vertical slice: paste a public GitHub URL, analyze it,
inspect the eight-category reverse roadmap, explore bounded code/capability graphs,
and open any inferred capability to see the evidence behind it.

## What works

- Strict validation for `https://github.com/{owner}/{repo}` public URLs.
- Bounded, temporary Git clones with no prompts, hooks, or submodules.
- Python extraction through the standard AST and JS/TS extraction through
  Tree-sitter: modules, classes, functions, methods, schemas, UI components, API
  routes, imports, calls, inheritance, and test relationships.
- Structural/dependency graph plus explicitly best-effort workflow and data-flow
  projections.
- Bounded Git history, changed paths, line summaries, tags, change-type heuristics,
  and first/last capability estimates.
- Grounded capabilities under RoadTrace's eight canonical categories.
- Explicit `DISCOVERED` → `PRODUCTIONIZED` maturity states backed by named evidence
  dimensions—never an invented completion percentage.
- Optional evidence-bounded semantic label refinement through the official OpenAI
  Python SDK and Responses API. Analysis remains fully functional without a key.
- SQLite result persistence and a small REST API.
- Responsive React workspace with honest summary metrics, a searchable capability
  constellation, a compact eight-category overview, reverse-roadmap filters, focused
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

### Optional semantic refinement

Deterministic mode is the default. To enable semantic refinement, export both:

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='your-responses-compatible-model'
```

The model name is never hard-coded. RoadTrace sends a bounded digest of existing
candidate capabilities, entities, and allowed evidence IDs—not whole repository
contents. Pydantic validates the structured response, and updates with unknown
capability/evidence IDs are discarded. Any SDK/API failure falls back to the
deterministic result and adds a visible warning.

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

The backend suite creates a temporary six-commit synthetic repository containing a
CLI, route algorithm, schemas/persistence, API and validation, tests, React UI,
CI, container configuration, documentation, and a tag. RoadTrace analyzes its
source and Git history but never executes the fixture. This makes the representative
end-to-end reverse roadmap reproducible without network access.

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

- Only exact public GitHub HTTPS repository URLs are accepted. Credentials, ports,
  alternate hosts, SSH/file URLs, local paths, query strings, fragments, encoded
  paths, and additional URL segments are rejected.
- Git is invoked with argument arrays and `shell=False`. Global/system Git config,
  prompts, hooks, LFS smudging, local file transport, and submodules are disabled.
- Clone time/depth/bytes, repository bytes, source bytes, file count, per-file bytes,
  history count, graph nodes, and workflow depth are configurable.
- File walking does not follow symlinks and ignores VCS data, dependencies, virtual
  environments, vendor/build output, generated bundles, binaries, and lockfiles.
- Temporary repositories are removed on both success and failure.

## Known V0.1 limitations

- Static call resolution is lexical and conservative; it is not full type-aware,
  interprocedural control-flow analysis. Workflow/data projections say **inferred**.
- The bounded shallow clone can miss capability origins older than the configured
  history window.
- GitHub pull requests, issues, and release descriptions are not fetched; local Git
  commits and tags are used.
- Capability clustering is deliberately small and deterministic. Optional semantics
  can improve labels but cannot create unsupported capabilities.
- Synchronous HTTP results and SQLite target local/single-user operation. Large-scale
  concurrency, caching, cancellation, and durable jobs are not included.
- Private repositories, authentication, and future plan-vs-actual comparison are
  explicitly outside V0.1.
