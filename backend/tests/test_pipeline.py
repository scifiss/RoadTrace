from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from app.analysis.history import GitHistoryAnalyzer
from app.analysis.modeling import _balanced_code_entities, maturity_state
from app.domain import CodeEntity, EntityType, MaturitySignals, MaturityState
from app.ingestion.repository import GitHubRepository, GitRunner
from app.main import create_app
from app.service import AnalysisService


def identity() -> GitHubRepository:
    return GitHubRepository(
        owner="roadtrace-fixtures",
        name="roadnet",
        url="https://github.com/roadtrace-fixtures/roadnet",
    )


def test_git_history_extracts_multiple_commits(synthetic_repository: Path, settings) -> None:
    commits, branch, warnings = GitHistoryAnalyzer(
        GitRunner(settings.git_timeout_seconds), settings.max_commits
    ).analyze(synthetic_repository)
    assert len(commits) == 6
    assert commits[0].subject == "initial CLI"
    assert commits[-1].changed_paths
    assert commits[-1].tags == ["v0.1.0"]
    assert branch == "main"
    assert not warnings


def test_git_history_samples_across_the_reachable_history(
    synthetic_repository: Path, settings
) -> None:
    commits, _, warnings = GitHistoryAnalyzer(
        GitRunner(settings.git_timeout_seconds), max_commits=3
    ).analyze(synthetic_repository)

    assert len(commits) == 3
    assert commits[0].subject == "initial CLI"
    assert commits[-1].tags == ["v0.1.0"]
    assert all(commit.changed_paths for commit in commits)
    assert warnings == ["History overview samples 3 commits across 6 reachable commits"]


def test_maturity_is_ordinal_and_evidence_dimension_based() -> None:
    assert maturity_state(MaturitySignals(), 0) == MaturityState.DISCOVERED
    assert maturity_state(MaturitySignals(implementation=True), 1) == MaturityState.SCAFFOLDED
    assert (
        maturity_state(MaturitySignals(implementation=True, reachable=True), 2)
        == MaturityState.INTEGRATED
    )
    assert (
        maturity_state(
            MaturitySignals(implementation=True, exposed=True, tests=True, operations=True), 4
        )
        == MaturityState.PRODUCTIONIZED
    )


def test_code_graph_selection_balances_repeated_entrypoints() -> None:
    repeated_mains = [
        CodeEntity(
            id=f"main-{index}",
            type=EntityType.FUNCTION,
            name="main",
            qualified_name=f"scripts.job_{index}.main",
            file_path=f"scripts/job_{index}.py",
            language="Python",
            metadata={"entrypoint": True},
        )
        for index in range(40)
    ]
    landmarks = [
        CodeEntity(
            id=f"{entity_type.value}-{index}",
            type=entity_type,
            name=f"{entity_type.value.title()}{index}",
            qualified_name=f"package.{entity_type.value.lower()}{index}",
            file_path=f"package/{entity_type.value.lower()}{index}.py",
            language="Python",
        )
        for entity_type in (
            EntityType.SCHEMA,
            EntityType.CLASS,
            EntityType.MODULE,
            EntityType.CONFIGURATION,
        )
        for index in range(4)
    ]

    selected = _balanced_code_entities([*repeated_mains, *landmarks], [], max_nodes=12)

    assert len(selected) == 12
    assert len([item for item in selected if item.name == "main"]) == 2
    assert {item.type for item in selected}.issuperset(
        {EntityType.SCHEMA, EntityType.CLASS, EntityType.MODULE, EntityType.CONFIGURATION}
    )


def test_end_to_end_fixture_builds_evidence_backed_reverse_roadmap(
    synthetic_repository: Path, settings
) -> None:
    result = AnalysisService(settings).analyze_path(synthetic_repository, identity())
    categories = {
        category
        for capability in result.capabilities
        for category in (capability.category, *capability.secondary_categories)
    }
    assert "Domain Capability" in categories
    assert "Data & State" in categories
    assert "Operations & Scale" in categories
    names = {capability.name for capability in result.capabilities}
    assert "Route Persistence" in names
    assert any("Path" in name and "Computation" in name for name in names)
    assert "Authentication" not in names
    assert not names.intersection(
        {"API Surface", "Json Engine", "User Interface", "React Component"}
    )
    assert result.behaviors
    assert result.observations
    assert result.capability_states
    assert result.lens_set and result.lens_set.version == "2.0"
    assert all(capability.behavior_ids for capability in result.capabilities)
    assert all(
        set(capability.behavior_ids).issubset({item.id for item in result.behaviors})
        for capability in result.capabilities
    )
    assert all(capability.evidence_ids for capability in result.capabilities)
    assert all(0 <= capability.confidence <= 1 for capability in result.capabilities)
    assert result.timeline
    assert result.code_graph.nodes
    assert result.capability_graph.nodes
    assert result.workflow_graph.description.startswith("Best-effort")
    assert any(node.metadata.get("entrypoint") for node in result.workflow_graph.nodes)
    assert all("language" in node.metadata for node in result.code_graph.nodes)
    assert result.repository.files_analyzed >= 8
    assert result.semantic_mode == "deterministic"


def test_api_analysis_workflow_persists_and_returns_result(
    synthetic_repository: Path, settings, monkeypatch
) -> None:
    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr("app.api.routes.asyncio.to_thread", run_inline)
    app = create_app(settings)

    async def request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        messages: list[dict] = []
        delivered = False

        async def receive() -> dict:
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            body = json.dumps(payload).encode() if payload is not None else b""
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict) -> None:
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1234),
                "server": ("test", 80),
            },
            receive,
            send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return start["status"], json.loads(body)

    async def exercise_api() -> None:
        async with app.router.lifespan_context(app):
            service = AnalysisService(settings, app.state.analysis_store)
            service.analyze_url = lambda _url: service.analyze_path(  # type: ignore[method-assign]
                synthetic_repository, identity()
            )
            app.state.analysis_service = service
            status, payload = await request(
                "POST",
                "/api/analyses",
                {"repository_url": "https://github.com/roadtrace-fixtures/roadnet"},
            )
            assert status == 201
            stored_status, stored = await request("GET", f"/api/analyses/{payload['id']}")
            assert stored_status == 200
            assert stored["repository"]["name"] == "roadnet"
            health_status, health = await request("GET", "/api/health")
            assert health_status == 200
            assert health == {"status": "ok"}

    asyncio.run(exercise_api())


def test_development_local_input_uses_the_standard_analysis_pipeline(
    synthetic_repository: Path, settings
) -> None:
    enabled = replace(
        settings,
        dev_local_repos=True,
        local_repo_roots=(synthetic_repository.parent,),
    )
    result = AnalysisService(enabled).analyze_input(str(synthetic_repository))
    assert result.repository.owner == "local"
    assert result.repository.url.startswith("local://")
    names = {item.name for item in result.capabilities}
    assert "Route Persistence" in names
    assert any("Path" in name and "Computation" in name for name in names)


def test_product_semantic_fixture_clusters_workflows_and_controls_granularity(
    media_semantic_repository: Path, settings
) -> None:
    result = AnalysisService(settings).analyze_path(
        media_semantic_repository,
        GitHubRepository(
            owner="roadtrace-fixtures",
            name="compound-workflow",
            url="https://github.com/roadtrace-fixtures/compound-workflow",
        ),
    )
    by_name = {item.name: item for item in result.capabilities}
    behavior_by_id = {item.id: item for item in result.behaviors}

    def with_role(role: str):
        return [
            capability
            for capability in result.capabilities
            if any(
                role in behavior_by_id[behavior_id].mechanism_types
                for behavior_id in capability.behavior_ids
            )
        ]

    management = with_role("MANAGEMENT")
    search = with_role("SEARCH_FILTER")
    persistence = with_role("PERSISTENCE")
    scoring = with_role("SCORING")
    assert management and search and persistence and scoring
    assert any(item.parent_id == management[0].id for item in [*search, *persistence])
    assert len([item for item in result.capabilities if item.name == management[0].name]) == 1
    assert "Biometric Identity Verification" not in by_name
    assert not {
        "API Surface",
        "Json Engine",
        "User Interface",
        "React Component",
        "Helper Utilities",
    }.intersection(by_name)
    assert all(item.evidence_ids and item.behavior_ids for item in result.capabilities)
    assert all(item.observation_ids for item in result.capabilities)
    evidence_ids = {item.id for item in result.evidence}
    assert all(set(item.evidence_ids).intersection(evidence_ids) for item in result.capabilities)
