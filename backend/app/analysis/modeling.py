from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

from app.analysis.languages import LanguageAnalysis, PendingRelationship, build_entity, stable_id
from app.domain import (
    CanonicalCategory,
    Capability,
    CategorySummary,
    ChangeType,
    CodeEntity,
    CodeRelationship,
    CommitRecord,
    EntityType,
    EvidenceKind,
    GraphEdge,
    GraphNode,
    GraphProjection,
    MaturitySignals,
    MaturityState,
    ObservedEvidence,
    RelationshipType,
    TimelineEvent,
)
from app.ingestion.repository import SourceFile
from app.taxonomy import TAXONOMY


def support_entities(files: list[SourceFile]) -> LanguageAnalysis:
    result = LanguageAnalysis()
    for source_file in files:
        if source_file.language not in {"Documentation", "Configuration"}:
            continue
        entity_type = (
            EntityType.CONFIGURATION if source_file.language == "Configuration" else EntityType.FILE
        )
        entity, evidence = build_entity(
            entity_type=entity_type,
            name=Path(source_file.path).name,
            qualified_name=source_file.path,
            source_file=source_file,
            line_start=1,
            line_end=max(1, len(source_file.content.splitlines())),
        )
        if source_file.language == "Documentation":
            evidence.kind = EvidenceKind.DOCUMENTATION
            evidence.label = f"Documentation: {source_file.path}"
        result.entities.append(entity)
        result.evidence.append(evidence)
    return result


def merge_and_resolve(chunks: list[LanguageAnalysis]) -> LanguageAnalysis:
    merged = LanguageAnalysis()
    pending: list[PendingRelationship] = []
    for chunk in chunks:
        merged.entities.extend(chunk.entities)
        merged.relationships.extend(chunk.relationships)
        merged.evidence.extend(chunk.evidence)
        merged.warnings.extend(chunk.warnings)
        pending.extend(chunk.pending_relationships)

    by_id = {entity.id: entity for entity in merged.entities}
    by_qualified = {entity.qualified_name: entity for entity in merged.entities}
    by_name: dict[str, list[CodeEntity]] = defaultdict(list)
    for entity in merged.entities:
        by_name[entity.name].append(entity)

    external: dict[str, CodeEntity] = {}
    for item in pending:
        target = _resolve_target(item.target_name, by_qualified, by_name)
        if (
            target is None
            and item.type == RelationshipType.IMPORTS
            and not item.target_name.startswith(".")
        ):
            dependency = _dependency_root(item.target_name)
            if not dependency:
                continue
            target = external.get(dependency)
            if target is None:
                source = by_id.get(item.source_id)
                if source is None:
                    continue
                source_file = SourceFile(
                    path=source.file_path,
                    absolute_path=Path(source.file_path),
                    language=source.language,
                    size=0,
                    content="",
                )
                is_external = (
                    source.language != "Python" or dependency not in sys.stdlib_module_names
                )
                target, target_evidence = build_entity(
                    entity_type=EntityType.EXTERNAL_MODULE,
                    name=dependency,
                    qualified_name=f"external:{dependency}",
                    source_file=source_file,
                    line_start=source.line_start,
                    line_end=source.line_start,
                    metadata={"external": is_external},
                )
                target.file_path = source.file_path
                target_evidence.detail = f"Observed import of external module {dependency}"
                external[dependency] = target
                merged.entities.append(target)
                merged.evidence.append(target_evidence)
        if target is None or target.id == item.source_id:
            continue
        source = by_id.get(item.source_id)
        relation_type = item.type
        if source and source.type == EntityType.TEST and item.type == RelationshipType.CALLS:
            relation_type = RelationshipType.TESTS
        elif (
            source
            and source.type == EntityType.UI_COMPONENT
            and target.type == EntityType.UI_COMPONENT
            and item.type == RelationshipType.CALLS
        ):
            relation_type = RelationshipType.RENDERS
        merged.relationships.append(
            CodeRelationship(
                source_id=item.source_id,
                target_id=target.id,
                type=relation_type,
                confidence=item.confidence,
                evidence_ids=list(item.evidence_ids),
                inferred=item.inferred,
            )
        )

    merged.relationships = _deduplicate_relationships(merged.relationships)
    return merged


def _resolve_target(
    raw_name: str,
    by_qualified: dict[str, CodeEntity],
    by_name: dict[str, list[CodeEntity]],
) -> CodeEntity | None:
    normalized = raw_name.strip("./").replace("/", ".")
    if normalized in by_qualified:
        return by_qualified[normalized]
    tail = normalized.rsplit(".", 1)[-1]
    candidates = by_name.get(tail, [])
    return candidates[0] if len(candidates) == 1 else None


def _dependency_root(name: str) -> str:
    cleaned = name.strip("./").replace("\\", "/")
    if not cleaned:
        return ""
    if cleaned.startswith("@"):
        return "/".join(cleaned.split("/")[:2])
    return re.split(r"[/.]", cleaned, maxsplit=1)[0]


def _deduplicate_relationships(items: list[CodeRelationship]) -> list[CodeRelationship]:
    seen: set[tuple[str, str, RelationshipType]] = set()
    result: list[CodeRelationship] = []
    for item in items:
        key = (item.source_id, item.target_id, item.type)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class CapabilityInferer:
    def infer(
        self,
        entities: list[CodeEntity],
        relationships: list[CodeRelationship],
        evidence: list[ObservedEvidence],
        commits: list[CommitRecord],
    ) -> tuple[list[Capability], list[TimelineEvent], list[CategorySummary]]:
        evidence_by_id = {item.id: item for item in evidence}
        entity_by_id = {item.id: item for item in entities}
        rules = self._candidate_rules(entities, evidence)
        capabilities: list[Capability] = []
        for category, name, description, matched_entities, matched_evidence, parent_name in rules:
            if not matched_evidence:
                continue
            entity_ids = _unique(entity.id for entity in matched_entities)[:80]
            evidence_ids = _unique(item.id for item in matched_evidence)[:120]
            capability_id = stable_id("cap", category, name)
            related_commits = _commits_for_evidence(commits, matched_evidence)
            commit_evidence = [stable_id("evcommit", commit.hash) for commit in related_commits]
            evidence_ids = _unique([*evidence_ids, *commit_evidence])
            signals = calculate_maturity_signals(
                entity_ids,
                evidence_ids,
                relationships,
                entity_by_id,
                evidence_by_id,
                category,
            )
            capabilities.append(
                Capability(
                    id=capability_id,
                    name=name,
                    description=description,
                    category=category,
                    parent_id=stable_id("cap", category, parent_name) if parent_name else None,
                    entity_ids=entity_ids,
                    evidence_ids=evidence_ids,
                    commit_hashes=[commit.hash for commit in related_commits],
                    first_seen=related_commits[0].timestamp if related_commits else None,
                    last_changed=related_commits[-1].timestamp if related_commits else None,
                    maturity=maturity_state(signals, len(entity_ids)),
                    maturity_signals=signals,
                    confidence=capability_confidence(matched_evidence, len(entity_ids)),
                    reasoning_summary=_reasoning(name, matched_evidence, matched_entities, signals),
                )
            )

        for capability in capabilities:
            if capability.parent_id:
                parent = next(
                    (item for item in capabilities if item.id == capability.parent_id), None
                )
                if parent:
                    parent.child_ids.append(capability.id)
                else:
                    capability.parent_id = None

        timeline = build_timeline(capabilities, commits)
        categories = [
            CategorySummary(
                category=category,
                capability_count=sum(cap.category == category for cap in capabilities),
                evidence_count=len(
                    {
                        evidence_id
                        for cap in capabilities
                        if cap.category == category
                        for evidence_id in cap.evidence_ids
                    }
                ),
            )
            for category in TAXONOMY
        ]
        return capabilities, timeline, categories

    def _candidate_rules(
        self, entities: list[CodeEntity], evidence: list[ObservedEvidence]
    ) -> list[
        tuple[
            CanonicalCategory,
            str,
            str,
            list[CodeEntity],
            list[ObservedEvidence],
            str | None,
        ]
    ]:
        evidence_by_id = {item.id: item for item in evidence}

        def select_entities(predicate) -> list[CodeEntity]:
            return [item for item in entities if predicate(item)]

        def selected_evidence(selected: list[CodeEntity]) -> list[ObservedEvidence]:
            return [
                evidence_by_id[evidence_id]
                for entity in selected
                for evidence_id in entity.evidence_ids
                if evidence_id in evidence_by_id
            ]

        ui = select_entities(
            lambda item: (
                item.type == EntityType.UI_COMPONENT
                or _contains_any(item, ("component", "view", "screen", "page", "ui/", "frontend/"))
            )
        )
        workflows = select_entities(
            lambda item: (
                bool(item.metadata.get("entrypoint")) and item.type != EntityType.API_ENDPOINT
            )
        )
        core = select_entities(_is_core_entity)
        schemas = select_entities(lambda item: item.type == EntityType.SCHEMA)
        persistence = select_entities(
            lambda item: _contains_any(
                item,
                (
                    "database",
                    "repository",
                    "persist",
                    "storage",
                    "migration",
                    "cache",
                    "ingest",
                    "transform",
                    "sqlite",
                    "model",
                ),
            )
        )
        api = select_entities(lambda item: item.type == EntityType.API_ENDPOINT)
        integrations = select_entities(
            lambda item: (
                item.type == EntityType.EXTERNAL_MODULE and bool(item.metadata.get("external"))
            )
        )
        reliability = select_entities(
            lambda item: _contains_any(
                item,
                (
                    "validat",
                    "security",
                    "permission",
                    "auth",
                    "sanitize",
                    "safe",
                    "error",
                    "guard",
                    "limit",
                ),
            )
        )
        tests = select_entities(
            lambda item: (
                item.type == EntityType.TEST
                or item.file_path.startswith("test")
                or "/test" in item.file_path.lower()
            )
        )
        ci = select_entities(
            lambda item: (
                item.type == EntityType.CONFIGURATION
                and _contains_any(item, (".github/workflows", "gitlab-ci", "circleci", "jenkins"))
            )
        )
        runtime = select_entities(
            lambda item: (
                item.type == EntityType.CONFIGURATION
                and _contains_any(
                    item,
                    (
                        "dockerfile",
                        "compose",
                        "procfile",
                        "deploy",
                        "terraform",
                        "render",
                        "fly.toml",
                    ),
                )
            )
        )
        docs = select_entities(
            lambda item: (
                evidence_by_id.get(
                    item.evidence_ids[0],
                    ObservedEvidence(id="x", kind=EvidenceKind.SOURCE, label="x"),
                ).kind
                == EvidenceKind.DOCUMENTATION
            )
        )
        tooling = select_entities(
            lambda item: (
                item.type == EntityType.CONFIGURATION
                and _contains_any(
                    item,
                    (
                        "pyproject.toml",
                        "package.json",
                        "vite.config",
                        "tsconfig",
                        "makefile",
                        "ruff",
                        "eslint",
                    ),
                )
            )
        )

        topic = _core_topic(core)
        core_name = f"{topic} Engine" if topic else "Domain Logic"
        return [
            (
                CanonicalCategory.PRODUCT_UX,
                "User Interface",
                "Interactive components and presentation surfaces found in the source tree.",
                ui,
                selected_evidence(ui),
                None,
            ),
            (
                CanonicalCategory.PRODUCT_UX,
                "User Workflows",
                "User-facing or command entry points and their reachable handlers.",
                workflows,
                selected_evidence(workflows),
                "User Interface" if ui else None,
            ),
            (
                CanonicalCategory.CORE,
                core_name,
                (
                    "Project-specific implementation functions and classes that form the "
                    "domain engine."
                ),
                core[:80],
                selected_evidence(core[:80]),
                None,
            ),
            (
                CanonicalCategory.DATA,
                "Data Models & Schemas",
                "Typed schemas and domain data structures observed in executable source.",
                schemas,
                selected_evidence(schemas),
                None,
            ),
            (
                CanonicalCategory.DATA,
                "Persistence & Transformation",
                "Persistence, ingestion, caching, migration, or transformation code.",
                persistence,
                selected_evidence(persistence),
                None,
            ),
            (
                CanonicalCategory.PLATFORM,
                "API Surface",
                "HTTP or service endpoints exposed by application code.",
                api,
                selected_evidence(api),
                None,
            ),
            (
                CanonicalCategory.PLATFORM,
                "External Integrations",
                "Third-party modules directly imported by the analyzed source.",
                integrations,
                selected_evidence(integrations),
                None,
            ),
            (
                CanonicalCategory.RELIABILITY,
                "Validation & Guardrails",
                "Validation, permissions, security, error handling, and bounded-operation code.",
                reliability,
                selected_evidence(reliability),
                None,
            ),
            (
                CanonicalCategory.QUALITY,
                "Automated Testing",
                "Unit, integration, evaluation, or benchmark symbols found in test sources.",
                tests,
                selected_evidence(tests),
                None,
            ),
            (
                CanonicalCategory.OPERATIONS,
                "Continuous Integration",
                "Continuous integration and automated delivery configuration.",
                ci,
                selected_evidence(ci),
                None,
            ),
            (
                CanonicalCategory.OPERATIONS,
                "Deployment & Runtime",
                "Deployment, container, and runtime configuration.",
                runtime,
                selected_evidence(runtime),
                None,
            ),
            (
                CanonicalCategory.DEVELOPER,
                "Documentation",
                (
                    "Repository documentation and contributor guidance, treated as "
                    "supporting evidence."
                ),
                docs,
                selected_evidence(docs),
                None,
            ),
            (
                CanonicalCategory.DEVELOPER,
                "Developer Tooling",
                "Local development, build, type-checking, and lint configuration.",
                tooling,
                selected_evidence(tooling),
                None,
            ),
        ]


def _is_core_entity(entity: CodeEntity) -> bool:
    if entity.type not in {EntityType.CLASS, EntityType.FUNCTION, EntityType.METHOD}:
        return False
    lowered = f"{entity.file_path} {entity.qualified_name}".lower()
    return not any(
        marker in lowered
        for marker in (
            "test",
            "migration",
            "config",
            "setup",
            "route",
            "controller",
            "__init__",
            "vite.config",
        )
    )


def _contains_any(entity: CodeEntity, needles: tuple[str, ...]) -> bool:
    value = f"{entity.file_path} {entity.qualified_name}".lower()
    return any(needle in value for needle in needles)


def _core_topic(entities: list[CodeEntity]) -> str | None:
    stop = {
        "app",
        "src",
        "lib",
        "core",
        "main",
        "index",
        "service",
        "function",
        "get",
        "set",
        "create",
        "update",
        "handle",
        "manager",
    }
    tokens: Counter[str] = Counter()
    for entity in entities:
        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", entity.name.replace("_", " "))
        tokens.update(word.lower() for word in words if len(word) > 3 and word.lower() not in stop)
    if not tokens:
        return None
    topic, count = tokens.most_common(1)[0]
    return topic.title() if count >= 2 or len(entities) <= 5 else None


def calculate_maturity_signals(
    entity_ids: list[str],
    evidence_ids: list[str],
    relationships: list[CodeRelationship],
    entity_by_id: dict[str, CodeEntity],
    evidence_by_id: dict[str, ObservedEvidence],
    category: CanonicalCategory,
) -> MaturitySignals:
    selected = {entity_id for entity_id in entity_ids}
    selected_entities = [entity_by_id[item] for item in selected if item in entity_by_id]
    evidence_items = [evidence_by_id[item] for item in evidence_ids if item in evidence_by_id]
    inbound = [relationship for relationship in relationships if relationship.target_id in selected]
    implementation = any(
        item.type
        in {
            EntityType.CLASS,
            EntityType.FUNCTION,
            EntityType.METHOD,
            EntityType.API_ENDPOINT,
            EntityType.UI_COMPONENT,
            EntityType.SCHEMA,
            EntityType.TEST,
        }
        for item in selected_entities
    )
    reachable = any(
        relationship.type
        in {
            RelationshipType.CALLS,
            RelationshipType.INSTANTIATES,
            RelationshipType.RENDERS,
            RelationshipType.EXPOSES,
        }
        for relationship in inbound
    ) or any(bool(item.metadata.get("entrypoint")) for item in selected_entities)
    exposed = any(
        item.type in {EntityType.API_ENDPOINT, EntityType.UI_COMPONENT}
        for item in selected_entities
    ) or any(item.type == RelationshipType.EXPOSES for item in inbound)
    tests = any(item.type == RelationshipType.TESTS for item in inbound) or any(
        item.kind == EvidenceKind.TEST for item in evidence_items
    )
    validation = any(
        token in f"{item.file_path} {item.qualified_name}".lower()
        for item in selected_entities
        for token in ("validat", "guard", "security", "permission", "sanitize", "error")
    )
    operations = category == CanonicalCategory.OPERATIONS
    documentation = any(item.kind == EvidenceKind.DOCUMENTATION for item in evidence_items)
    monitoring = any(
        token in f"{item.file_path} {item.qualified_name}".lower()
        for item in selected_entities
        for token in ("monitor", "metric", "telemetry", "observab")
    )
    return MaturitySignals(
        implementation=implementation,
        reachable=reachable,
        exposed=exposed,
        tests=tests,
        validation=validation,
        operations=operations,
        documentation=documentation,
        monitoring=monitoring,
    )


def maturity_state(signals: MaturitySignals, entity_count: int) -> MaturityState:
    if not signals.implementation:
        return MaturityState.DISCOVERED
    if signals.tests and signals.operations and (signals.exposed or signals.reachable):
        return MaturityState.PRODUCTIONIZED
    if signals.tests or (signals.validation and (signals.exposed or signals.reachable)):
        return MaturityState.VALIDATED
    if signals.exposed or signals.reachable:
        return MaturityState.INTEGRATED
    if entity_count >= 2:
        return MaturityState.FUNCTIONAL
    return MaturityState.SCAFFOLDED


def capability_confidence(evidence: list[ObservedEvidence], entity_count: int) -> float:
    weights = {
        EvidenceKind.SOURCE: 0.18,
        EvidenceKind.TEST: 0.16,
        EvidenceKind.API: 0.2,
        EvidenceKind.SCHEMA: 0.18,
        EvidenceKind.UI: 0.18,
        EvidenceKind.CONFIGURATION: 0.1,
        EvidenceKind.DEPENDENCY: 0.08,
        EvidenceKind.DOCUMENTATION: 0.04,
        EvidenceKind.COMMIT: 0.06,
    }
    kinds = {item.kind for item in evidence}
    return round(
        min(0.98, 0.36 + sum(weights[kind] for kind in kinds) + min(entity_count, 8) * 0.025), 2
    )


def _reasoning(
    name: str,
    evidence: list[ObservedEvidence],
    entities: list[CodeEntity],
    signals: MaturitySignals,
) -> str:
    kind_counts = Counter(item.kind.value.lower().replace("_", " ") for item in evidence)
    kinds = ", ".join(f"{count} {kind}" for kind, count in kind_counts.most_common(3))
    signal_names = [key.replace("_", " ") for key, value in signals.model_dump().items() if value]
    signal_text = ", ".join(signal_names) or "discovery only"
    return (
        f"{name} is grounded in {len(entities)} code/configuration entities ({kinds}). "
        f"Observed maturity signals: {signal_text}."
    )


def _commits_for_evidence(
    commits: list[CommitRecord], evidence: list[ObservedEvidence]
) -> list[CommitRecord]:
    paths = {item.file_path for item in evidence if item.file_path}
    return [commit for commit in commits if paths.intersection(commit.changed_paths)]


def commit_evidence(commits: list[CommitRecord]) -> list[ObservedEvidence]:
    return [
        ObservedEvidence(
            id=stable_id("evcommit", commit.hash),
            kind=EvidenceKind.COMMIT,
            label=f"Commit {commit.short_hash}: {commit.subject}",
            commit_hash=commit.hash,
            observed_at=commit.timestamp,
            detail=(
                f"{commit.change_type.value.replace('_', ' ').title()} touching "
                f"{len(commit.changed_paths)} path(s)"
                + (
                    f", +{commit.additions}/-{commit.deletions}"
                    if commit.additions or commit.deletions
                    else ""
                )
            ),
        )
        for commit in commits
    ]


def build_timeline(
    capabilities: list[Capability], commits: list[CommitRecord]
) -> list[TimelineEvent]:
    commit_by_hash = {commit.hash: commit for commit in commits}
    events: list[TimelineEvent] = []
    for capability in capabilities:
        related = [
            commit_by_hash[item] for item in capability.commit_hashes if item in commit_by_hash
        ]
        if not related:
            continue
        chosen = [related[0]]
        candidates = related[1:]
        substantial = (
            sorted(candidates, key=lambda item: item.additions + item.deletions, reverse=True)[:2]
            if any(item.additions or item.deletions for item in candidates)
            else candidates[-2:]
        )
        for index, commit in enumerate(_unique_commits([*chosen, *substantial])):
            first = index == 0
            events.append(
                TimelineEvent(
                    id=stable_id("event", capability.id, commit.hash),
                    capability_id=capability.id,
                    timestamp=commit.timestamp,
                    change_type=ChangeType.NEW_CAPABILITY if first else commit.change_type,
                    title=f"{capability.name} {'appeared' if first else 'evolved'}",
                    summary=commit.subject,
                    commit_hash=commit.hash,
                    evidence_ids=[stable_id("evcommit", commit.hash)],
                )
            )
    return sorted(events, key=lambda item: item.timestamp)


def _unique(values) -> list:
    return list(dict.fromkeys(values))


def _unique_commits(commits: list[CommitRecord]) -> list[CommitRecord]:
    seen: set[str] = set()
    result: list[CommitRecord] = []
    for commit in commits:
        if commit.hash not in seen:
            seen.add(commit.hash)
            result.append(commit)
    return result


def build_graphs(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    capabilities: list[Capability],
    max_nodes: int,
    workflow_depth: int,
) -> tuple[GraphProjection, GraphProjection, GraphProjection, GraphProjection]:
    capability_graph = _capability_graph(capabilities)
    code_graph = _code_graph(entities, relationships, max_nodes)
    workflow_graph = _workflow_graph(entities, relationships, max_nodes, workflow_depth)
    data_graph = _data_graph(entities, relationships, max_nodes)
    return capability_graph, code_graph, workflow_graph, data_graph


def _capability_graph(capabilities: list[Capability]) -> GraphProjection:
    nodes = [
        GraphNode(id=f"category:{category.value}", label=category.value, kind="CATEGORY")
        for category in TAXONOMY
    ]
    nodes.extend(
        GraphNode(
            id=cap.id,
            label=cap.name,
            kind="CAPABILITY",
            group=cap.category.value,
            metadata={"maturity": cap.maturity.value, "confidence": cap.confidence},
        )
        for cap in capabilities
    )
    edges = [
        GraphEdge(
            id=stable_id("edge", cap.parent_id or cap.category, cap.id),
            source=cap.parent_id or f"category:{cap.category.value}",
            target=cap.id,
            type="CONTAINS",
        )
        for cap in capabilities
    ]
    return GraphProjection(
        label="Capability graph",
        description="Canonical categories, inferred capabilities, and subcapabilities.",
        nodes=nodes,
        edges=edges,
    )


def _code_graph(
    entities: list[CodeEntity], relationships: list[CodeRelationship], max_nodes: int
) -> GraphProjection:
    selected = _balanced_code_entities(entities, relationships, max_nodes)
    return _project_entities(
        "Code graph",
        "Balanced structural view of modules, interfaces, data types, "
        "executable symbols, and imports.",
        selected,
        relationships,
        truncated=len(entities) > len(selected),
    )


def _balanced_code_entities(
    entities: list[CodeEntity], relationships: list[CodeRelationship], max_nodes: int
) -> list[CodeEntity]:
    """Keep a bounded graph representative instead of letting one symbol type dominate."""
    type_order = [
        EntityType.API_ENDPOINT,
        EntityType.UI_COMPONENT,
        EntityType.SCHEMA,
        EntityType.CLASS,
        EntityType.MODULE,
        EntityType.CONFIGURATION,
        EntityType.FUNCTION,
        EntityType.TEST,
        EntityType.METHOD,
        EntityType.EXTERNAL_MODULE,
        EntityType.FILE,
    ]
    degree = Counter[str]()
    for relationship in relationships:
        degree[relationship.source_id] += 1
        degree[relationship.target_id] += 1

    buckets = {entity_type: [] for entity_type in type_order}
    for entity in entities:
        buckets.setdefault(entity.type, []).append(entity)
    for bucket in buckets.values():
        bucket.sort(
            key=lambda item: (
                0 if item.metadata.get("entrypoint") else 1,
                -degree[item.id],
                item.file_path,
                item.line_start,
            )
        )

    selected: list[CodeEntity] = []
    selected_ids: set[str] = set()
    name_counts: Counter[tuple[EntityType, str]] = Counter()
    file_counts: Counter[str] = Counter()
    cursors = {entity_type: 0 for entity_type in buckets}
    duplicate_limit = max(2, max_nodes // 30)
    per_file_limit = max(4, max_nodes // 18)

    while len(selected) < max_nodes:
        progressed = False
        for entity_type in type_order:
            bucket = buckets[entity_type]
            while cursors[entity_type] < len(bucket):
                item = bucket[cursors[entity_type]]
                cursors[entity_type] += 1
                name_key = (item.type, item.name.casefold())
                if name_counts[name_key] >= duplicate_limit:
                    continue
                if file_counts[item.file_path] >= per_file_limit:
                    continue
                selected.append(item)
                selected_ids.add(item.id)
                name_counts[name_key] += 1
                file_counts[item.file_path] += 1
                progressed = True
                break
            if len(selected) >= max_nodes:
                break
        if not progressed:
            break

    if len(selected) < max_nodes:
        remaining = sorted(
            (item for item in entities if item.id not in selected_ids),
            key=lambda item: (
                type_order.index(item.type) if item.type in type_order else len(type_order),
                0 if item.metadata.get("entrypoint") else 1,
                -degree[item.id],
                item.file_path,
                item.line_start,
            ),
        )
        selected.extend(remaining[: max_nodes - len(selected)])
    return selected


def _workflow_graph(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    max_nodes: int,
    max_depth: int,
) -> GraphProjection:
    by_id = {item.id: item for item in entities}
    adjacency: dict[str, list[CodeRelationship]] = defaultdict(list)
    allowed = {
        RelationshipType.CALLS,
        RelationshipType.INSTANTIATES,
        RelationshipType.EXPOSES,
        RelationshipType.RENDERS,
    }
    for relationship in relationships:
        if relationship.type in allowed:
            adjacency[relationship.source_id].append(relationship)
    entries = [
        item
        for item in entities
        if item.metadata.get("entrypoint") or item.type == EntityType.API_ENDPOINT
    ][:24]
    selected_ids = {item.id for item in entries}
    queue = deque((item.id, 0) for item in entries)
    while queue and len(selected_ids) < max_nodes:
        source_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for relationship in adjacency[source_id]:
            if relationship.target_id in by_id and relationship.target_id not in selected_ids:
                selected_ids.add(relationship.target_id)
                queue.append((relationship.target_id, depth + 1))
    selected = [item for item in entities if item.id in selected_ids]
    projection = _project_entities(
        "Inferred workflows",
        f"Best-effort static call neighborhoods, bounded to depth {max_depth}.",
        selected,
        relationships,
        inferred=True,
        truncated=bool(queue),
    )
    return projection


def _data_graph(
    entities: list[CodeEntity], relationships: list[CodeRelationship], max_nodes: int
) -> GraphProjection:
    schema_ids = {item.id for item in entities if item.type == EntityType.SCHEMA}
    related_ids = set(schema_ids)
    for relationship in relationships:
        if relationship.source_id in schema_ids or relationship.target_id in schema_ids:
            related_ids.update({relationship.source_id, relationship.target_id})
    selected = [item for item in entities if item.id in related_ids][:max_nodes]
    return _project_entities(
        "Data-flow hints",
        "Obvious schema producers and consumers inferred from imports, calls, and instantiation.",
        selected,
        relationships,
        inferred=True,
        truncated=len(related_ids) > len(selected),
    )


def _project_entities(
    label: str,
    description: str,
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    *,
    inferred: bool = False,
    truncated: bool = False,
) -> GraphProjection:
    selected_ids = {item.id for item in entities}
    nodes = [
        GraphNode(
            id=item.id,
            label=item.name,
            kind=item.type.value,
            group=item.file_path,
            metadata={
                "file_path": item.file_path,
                "line": item.line_start,
                "language": item.language,
                "entrypoint": bool(item.metadata.get("entrypoint")),
                "qualified_name": item.qualified_name,
            },
        )
        for item in entities
    ]
    edges = [
        GraphEdge(
            id=stable_id("edge", item.source_id, item.target_id, item.type),
            source=item.source_id,
            target=item.target_id,
            type=item.type.value,
            confidence=item.confidence,
            inferred=inferred or item.inferred,
        )
        for item in relationships
        if item.source_id in selected_ids and item.target_id in selected_ids
    ]
    return GraphProjection(
        label=label,
        description=description,
        nodes=nodes,
        edges=edges,
        truncated=truncated,
    )
