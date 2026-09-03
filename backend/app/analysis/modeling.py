from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

from app.analysis.behaviors import build_behavior_summaries
from app.analysis.languages import LanguageAnalysis, PendingRelationship, build_entity, stable_id
from app.domain import (
    BehaviorSummary,
    Capability,
    CapabilityState,
    CapabilityStateKind,
    CapabilityTrait,
    CategorySummary,
    ChangeType,
    CodeEntity,
    CodeRelationship,
    CommitRecord,
    ConfidenceDimensions,
    EntityType,
    EvidenceKind,
    GraphEdge,
    GraphNode,
    GraphProjection,
    KnowledgeQuality,
    LensSet,
    MaturitySignals,
    MaturityState,
    Observation,
    ObservedEvidence,
    RelationshipType,
    TimelineEvent,
)
from app.ingestion.repository import SourceFile
from app.taxonomy import DEFAULT_LENS_SET, active_lenses, lens_label


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
            evidence.kind = EvidenceKind.DOCUMENT_CLAIM
            evidence.label = f"Documentation claim source: {source_file.path}"
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
    if len(candidates) == 1:
        return candidates[0]
    if "." not in normalized:
        top_level = [item for item in candidates if item.type != EntityType.METHOD]
        if len(top_level) == 1:
            return top_level[0]
    return None


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
    def __init__(self, lens_set: LensSet | None = None) -> None:
        self.lens_set = lens_set or DEFAULT_LENS_SET

    def infer(
        self,
        entities: list[CodeEntity],
        relationships: list[CodeRelationship],
        evidence: list[ObservedEvidence],
        commits: list[CommitRecord],
        observations: list[Observation] | None = None,
    ) -> tuple[list[Capability], list[BehaviorSummary]]:
        evidence_by_id = {item.id: item for item in evidence}
        entity_by_id = {item.id: item for item in entities}
        behaviors = build_behavior_summaries(
            entities,
            relationships,
            evidence,
            observations,
            self.lens_set,
        )
        capabilities: list[Capability] = []
        grouped: dict[tuple[str, str], list[BehaviorSummary]] = defaultdict(list)
        for behavior in behaviors:
            grouped[(behavior.primary_lens or "domain-capability", behavior.name)].append(behavior)

        for (primary_lens, name), supporting_behaviors in grouped.items():
            entity_ids = _unique(
                entity_id
                for behavior in supporting_behaviors
                for entity_id in behavior.supporting_entity_ids
            )[:80]
            evidence_ids = _unique(
                evidence_id
                for behavior in supporting_behaviors
                for evidence_id in behavior.evidence_ids
                if evidence_id in evidence_by_id
            )[:120]
            observation_ids = _unique(
                observation_id
                for behavior in supporting_behaviors
                for observation_id in behavior.observation_ids
            )[:160]
            if not entity_ids or not evidence_ids:
                continue
            matched_evidence = [evidence_by_id[item] for item in evidence_ids]
            matched_entities = [entity_by_id[item] for item in entity_ids if item in entity_by_id]
            related_commits = _commits_for_evidence(commits, matched_evidence)
            commit_evidence = [stable_id("evcommit", commit.hash) for commit in related_commits]
            evidence_ids = _unique([*evidence_ids, *commit_evidence])
            signals = calculate_maturity_signals(
                entity_ids,
                evidence_ids,
                relationships,
                entity_by_id,
                evidence_by_id,
                primary_lens,
            )
            secondary_lenses = _unique(
                lens_item
                for behavior in supporting_behaviors
                for lens_item in behavior.secondary_lenses
                if lens_item != primary_lens
            )
            capability_id = stable_id("cap", primary_lens, name)
            dimensions = _aggregate_confidence_dimensions(
                supporting_behaviors, bool(related_commits)
            )
            primary_label = lens_label(self.lens_set, primary_lens)
            capabilities.append(
                Capability(
                    id=capability_id,
                    name=name,
                    description=supporting_behaviors[0].description,
                    primary_lens=primary_lens,
                    secondary_lenses=secondary_lenses,
                    category=primary_label,
                    parent_id=None,
                    behavior_ids=[item.id for item in supporting_behaviors],
                    aliases=_unique(
                        item.name for item in supporting_behaviors if item.name != name
                    ),
                    secondary_categories=[
                        lens_label(self.lens_set, item) for item in secondary_lenses
                    ],
                    observation_ids=observation_ids,
                    traits=_capability_traits(supporting_behaviors, evidence_ids, matched_entities),
                    knowledge_quality=_knowledge_quality(
                        supporting_behaviors,
                        evidence_ids,
                        matched_evidence,
                        signals,
                        dimensions,
                    ),
                    entity_ids=entity_ids,
                    evidence_ids=evidence_ids,
                    commit_hashes=[commit.hash for commit in related_commits],
                    first_seen=related_commits[0].timestamp if related_commits else None,
                    last_changed=related_commits[-1].timestamp if related_commits else None,
                    maturity=maturity_state(signals, len(entity_ids)),
                    maturity_signals=signals,
                    confidence=max(
                        capability_confidence(matched_evidence, len(entity_ids)),
                        max(item.confidence for item in supporting_behaviors),
                    ),
                    confidence_dimensions=dimensions,
                    reasoning_summary=_behavior_reasoning(
                        name,
                        supporting_behaviors,
                        matched_evidence,
                        matched_entities,
                        signals,
                    ),
                )
            )

        _assign_hierarchy_from_behaviors(capabilities, behaviors)
        link_capability_hierarchy(capabilities)
        return capabilities, behaviors


def _assign_hierarchy_from_behaviors(
    capabilities: list[Capability], behaviors: list[BehaviorSummary]
) -> None:
    behavior_by_id = {item.id: item for item in behaviors}
    capability_by_name: dict[str, Capability] = {}
    for capability in capabilities:
        capability_by_name.setdefault(capability.name.casefold(), capability)
    for capability in capabilities:
        parent_name = next(
            (
                behavior.parent_name
                for behavior_id in capability.behavior_ids
                if (behavior := behavior_by_id.get(behavior_id)) is not None
                and behavior.parent_name
            ),
            None,
        )
        if parent_name:
            parent = capability_by_name.get(parent_name.casefold())
            capability.parent_id = parent.id if parent and parent.id != capability.id else None


def link_capability_hierarchy(capabilities: list[Capability]) -> None:
    by_id = {item.id: item for item in capabilities}
    for item in capabilities:
        item.child_ids = []
    for item in capabilities:
        if item.parent_id == item.id or item.parent_id not in by_id:
            item.parent_id = None
            continue
        parent = by_id[item.parent_id]
        if parent.parent_id == item.id:
            item.parent_id = None
            continue
        parent.child_ids.append(item.id)


def build_category_summaries(
    capabilities: list[Capability], lens_set: LensSet | None = None
) -> list[CategorySummary]:
    selected = lens_set or DEFAULT_LENS_SET
    return [
        CategorySummary(
            lens_id=lens.id,
            category=lens.label,
            capability_count=sum(cap.primary_lens == lens.id for cap in capabilities),
            evidence_count=len(
                {
                    evidence_id
                    for cap in capabilities
                    if cap.primary_lens == lens.id
                    for evidence_id in cap.evidence_ids
                }
            ),
        )
        for lens in active_lenses(selected)
    ]


def calculate_maturity_signals(
    entity_ids: list[str],
    evidence_ids: list[str],
    relationships: list[CodeRelationship],
    entity_by_id: dict[str, CodeEntity],
    evidence_by_id: dict[str, ObservedEvidence],
    primary_lens: str,
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
    ) or (
        primary_lens in {"operations-scale", "distribution-ecosystem"}
        and any(
            item.type in {EntityType.CONFIGURATION, EntityType.FILE} for item in selected_entities
        )
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
        token
        in (
            f"{item.file_path} {item.qualified_name} {item.metadata.get('semantic_signals', '')}"
        ).lower()
        for item in selected_entities
        for token in ("validat", "guard", "security", "permission", "sanitize", "error")
    )
    operations = primary_lens == "operations-scale"
    documentation = any(
        item.kind in {EvidenceKind.DOCUMENTATION, EvidenceKind.DOCUMENT_CLAIM}
        for item in evidence_items
    )
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
        EvidenceKind.SEMANTIC: 0.14,
        EvidenceKind.DOCUMENT_CLAIM: 0.02,
    }
    kinds = {item.kind for item in evidence}
    return round(
        min(0.98, 0.36 + sum(weights[kind] for kind in kinds) + min(entity_count, 8) * 0.025), 2
    )


def _aggregate_confidence_dimensions(
    behaviors: list[BehaviorSummary], has_history: bool
) -> ConfidenceDimensions:
    count = max(1, len(behaviors))
    return ConfidenceDimensions(
        evidence=round(sum(item.confidence_dimensions.evidence for item in behaviors) / count, 2),
        behavior=round(sum(item.confidence_dimensions.behavior for item in behaviors) / count, 2),
        semantic=round(sum(item.confidence_dimensions.semantic for item in behaviors) / count, 2),
        temporal=0.88 if has_history else 0.0,
    )


def _capability_traits(
    behaviors: list[BehaviorSummary],
    evidence_ids: list[str],
    entities: list[CodeEntity],
) -> list[CapabilityTrait]:
    roles = {role for behavior in behaviors for role in behavior.mechanism_types}
    backed = evidence_ids[:20]
    if not backed:
        return []
    candidates = {
        "INTERACTION": ("interactive", "Interactive"),
        "PERSISTENCE": ("persistent", "Persistent"),
        "EXTERNAL_INTEGRATION": ("externally-integrated", "Externally integrated"),
        "INTEGRATION": ("interface-exposed", "Interface exposed"),
        "AUTOMATION": ("automated", "Automated"),
        "EVALUATION": ("evaluated", "Evaluated"),
        "VALIDATION": ("guarded", "Guarded"),
        "INFERENCE": ("inference-backed", "Inference backed"),
    }
    traits = [
        CapabilityTrait(id=trait_id, label=label, evidence_ids=backed, confidence=0.78)
        for role, (trait_id, label) in candidates.items()
        if role in roles
    ]
    if any(item.type == EntityType.UI_COMPONENT for item in entities) and not any(
        item.id == "interactive" for item in traits
    ):
        traits.append(
            CapabilityTrait(
                id="interactive", label="Interactive", evidence_ids=backed, confidence=0.86
            )
        )
    return traits[:8]


def _knowledge_quality(
    behaviors: list[BehaviorSummary],
    evidence_ids: list[str],
    evidence: list[ObservedEvidence],
    signals: MaturitySignals,
    dimensions: ConfidenceDimensions,
) -> KnowledgeQuality | None:
    roles = {role for behavior in behaviors for role in behavior.mechanism_types}
    if not roles.intersection({"INFERENCE", "MATCHING", "SEARCH_FILTER"}):
        return None
    source_kinds = {item.source_kind for item in evidence if item.source_kind is not None}
    return KnowledgeQuality(
        breadth="multiple observed source kinds"
        if len(source_kinds) > 1
        else "single observed source kind",
        depth="implementation-linked" if signals.implementation else "claim-level only",
        executability="runtime-reachable"
        if signals.reachable or signals.exposed
        else "not established",
        grounding="code and tests" if signals.tests else "code evidence",
        freshness="Git history observed" if dimensions.temporal > 0 else "not established",
        evidence_ids=evidence_ids[:24],
        # The schema supports a future defensible knowledge-quality measure. The
        # current evidence is sufficient for descriptions, not a numeric score.
        confidence=None,
    )


def _behavior_reasoning(
    name: str,
    behaviors: list[BehaviorSummary],
    evidence: list[ObservedEvidence],
    entities: list[CodeEntity],
    signals: MaturitySignals,
) -> str:
    kind_counts = Counter(item.kind.value.lower().replace("_", " ") for item in evidence)
    kinds = ", ".join(f"{count} {kind}" for kind, count in kind_counts.most_common(3))
    behavior_names = ", ".join(f'"{item.name}"' for item in behaviors)
    semantic_terms = _unique(term for item in behaviors for term in item.semantic_terms)[:8]
    term_text = ", ".join(semantic_terms) or "connected implementation structure"
    signal_names = [key.replace("_", " ") for key, value in signals.model_dump().items() if value]
    signal_text = ", ".join(signal_names) or "discovery only"
    return (
        f"Observed {len(entities)} cooperating code entities ({kinds}) with signals "
        f'{term_text}; inferred behavior {behavior_names}; synthesized capability "{name}". '
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


def build_capability_states(
    capabilities: list[Capability], timeline: list[TimelineEvent]
) -> list[CapabilityState]:
    """Materialize temporal state transitions without inventing split/merge events."""
    result: list[CapabilityState] = []
    by_capability: dict[str, list[TimelineEvent]] = defaultdict(list)
    for event in timeline:
        by_capability[event.capability_id].append(event)
    for capability in capabilities:
        events = sorted(by_capability.get(capability.id, []), key=lambda item: item.timestamp)
        for index, event in enumerate(events):
            kind = (
                CapabilityStateKind.INTRODUCED
                if index == 0
                else CapabilityStateKind.REFACTORED
                if event.change_type == ChangeType.REFACTOR
                else CapabilityStateKind.REMOVED
                if event.change_type == ChangeType.REMOVAL
                else CapabilityStateKind.STRENGTHENED
            )
            result.append(
                CapabilityState(
                    id=stable_id("capstate", capability.id, event.id),
                    capability_id=capability.id,
                    kind=kind,
                    timestamp=event.timestamp,
                    summary=event.summary,
                    evidence_ids=event.evidence_ids,
                    behavior_ids=capability.behavior_ids,
                    confidence=capability.confidence_dimensions.temporal,
                )
            )
    return result


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
    lens_set: LensSet | None = None,
) -> tuple[GraphProjection, GraphProjection, GraphProjection, GraphProjection]:
    capability_graph = _capability_graph(capabilities, lens_set or DEFAULT_LENS_SET)
    code_graph = _code_graph(entities, relationships, max_nodes)
    workflow_graph = _workflow_graph(entities, relationships, max_nodes, workflow_depth)
    data_graph = _data_graph(entities, relationships, max_nodes)
    return capability_graph, code_graph, workflow_graph, data_graph


def _capability_graph(capabilities: list[Capability], lens_set: LensSet) -> GraphProjection:
    nodes = [
        GraphNode(id=f"lens:{lens.id}", label=lens.label, kind="LENS")
        for lens in active_lenses(lens_set)
    ]
    nodes.extend(
        GraphNode(
            id=cap.id,
            label=cap.name,
            kind="CAPABILITY",
            group=cap.category,
            metadata={
                "maturity": cap.maturity.value,
                "confidence": cap.confidence,
                "primary_lens": cap.primary_lens,
                "observation_ids": cap.observation_ids,
            },
        )
        for cap in capabilities
    )
    edges = [
        GraphEdge(
            id=stable_id("edge", cap.parent_id or cap.primary_lens, cap.id),
            source=cap.parent_id or f"lens:{cap.primary_lens}",
            target=cap.id,
            type="CONTAINS",
        )
        for cap in capabilities
    ]
    return GraphProjection(
        label="Capability graph",
        description="Versioned lenses, inferred capabilities, and subcapabilities.",
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
