from __future__ import annotations

import re
from collections import defaultdict

from app.analysis.languages import stable_id
from app.domain import (
    CodeEntity,
    CodeRelationship,
    CommitRecord,
    EntityType,
    EvidenceKind,
    Observation,
    ObservationKind,
    ObservedEvidence,
    RelationshipType,
    SourceKind,
)

_SIGNAL_KINDS: dict[str, ObservationKind] = {
    "button_label": ObservationKind.INTERACTION,
    "form_label": ObservationKind.INTERACTION,
    "heading": ObservationKind.INTERACTION,
    "jsx_text": ObservationKind.INTERACTION,
    "ui_text": ObservationKind.INTERACTION,
    "route": ObservationKind.INTERACTION,
    "route_path": ObservationKind.INTERACTION,
    "api_path": ObservationKind.INTERACTION,
    "api_route": ObservationKind.INTERACTION,
    "schema_field": ObservationKind.DATA_FLOW,
    "model_field": ObservationKind.DATA_FLOW,
    "storage_key": ObservationKind.PERSISTENCE,
    "browser_storage": ObservationKind.PERSISTENCE,
    "database_operation": ObservationKind.PERSISTENCE,
    "data_operation": ObservationKind.PERSISTENCE,
    "environment_variable": ObservationKind.CONFIGURATION,
    "env_var": ObservationKind.CONFIGURATION,
    "error_message": ObservationKind.VALIDATION,
    "test_label": ObservationKind.TEST_BEHAVIOR,
    "test_name": ObservationKind.TEST_BEHAVIOR,
    "external_system": ObservationKind.EXTERNAL_CALL,
    "constant": ObservationKind.STRUCTURE,
}

_RELATION_KINDS: dict[RelationshipType, ObservationKind] = {
    RelationshipType.CALLS: ObservationKind.INTERACTION,
    RelationshipType.RENDERS: ObservationKind.INTERACTION,
    RelationshipType.EXPOSES: ObservationKind.INTERACTION,
    RelationshipType.READS: ObservationKind.DATA_FLOW,
    RelationshipType.WRITES: ObservationKind.PERSISTENCE,
    RelationshipType.TESTS: ObservationKind.TEST_BEHAVIOR,
    RelationshipType.IMPORTS: ObservationKind.EXTERNAL_CALL,
    RelationshipType.DEPENDS_ON: ObservationKind.EXTERNAL_CALL,
    RelationshipType.INSTANTIATES: ObservationKind.STRUCTURE,
    RelationshipType.INHERITS: ObservationKind.STRUCTURE,
    RelationshipType.CONTAINS: ObservationKind.STRUCTURE,
}

_OPERATION_HINTS: tuple[tuple[ObservationKind, tuple[str, ...]], ...] = (
    (ObservationKind.PERSISTENCE, ("save", "store", "persist", "load", "read", "write", "cache")),
    (ObservationKind.VALIDATION, ("validate", "guard", "check", "sanitize", "authorize", "verify")),
    (
        ObservationKind.TRANSFORMATION,
        (
            "parse",
            "convert",
            "transform",
            "normalize",
            "calculate",
            "compute",
            "score",
            "generate",
            "aggregate",
        ),
    ),
    (
        ObservationKind.INTERACTION,
        ("render", "display", "select", "search", "filter", "submit", "handle"),
    ),
    (ObservationKind.EXTERNAL_CALL, ("fetch", "request", "publish", "send", "client", "webhook")),
)


def build_observations(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    evidence: list[ObservedEvidence],
    commits: list[CommitRecord] | None = None,
) -> list[Observation]:
    """Normalize parser-specific facts into a bounded source-independent layer."""
    evidence_by_id = {item.id: item for item in evidence}
    entity_by_id = {item.id: item for item in entities}
    result: list[Observation] = []

    for item in evidence:
        item.source_kind = item.source_kind or _source_kind(item)

    for entity in entities:
        entity_evidence = [item for item in entity.evidence_ids if item in evidence_by_id]
        if not entity_evidence:
            continue
        if entity.type == EntityType.FILE and any(
            evidence_by_id[item].kind in {EvidenceKind.DOCUMENTATION, EvidenceKind.DOCUMENT_CLAIM}
            for item in entity_evidence
        ):
            result.append(
                Observation(
                    id=stable_id("obs", "document", entity.id),
                    kind=ObservationKind.DOCUMENT_CLAIM,
                    summary=f"Documentation claims are present in {entity.file_path}",
                    evidence_ids=entity_evidence,
                    entity_ids=[entity.id],
                    terms=_terms(entity.name),
                    confidence=0.55,
                )
            )
            continue

        result.append(
            Observation(
                id=stable_id("obs", "entity", entity.id),
                kind=(
                    ObservationKind.CONFIGURATION
                    if entity.type == EntityType.CONFIGURATION
                    else ObservationKind.TEST_BEHAVIOR
                    if entity.type == EntityType.TEST
                    else ObservationKind.STRUCTURE
                ),
                summary=(
                    f"{entity.type.value.replace('_', ' ').title()} {entity.qualified_name} exists"
                ),
                evidence_ids=entity_evidence[:20],
                entity_ids=[entity.id],
                terms=_terms(f"{entity.name} {entity.qualified_name}"),
                structural=True,
                confidence=0.98,
            )
        )
        signals = entity.metadata.get("semantic_signals", [])
        if isinstance(signals, list):
            evidence_by_label: dict[str, list[str]] = defaultdict(list)
            for evidence_id in entity_evidence:
                observed = evidence_by_id[evidence_id]
                evidence_by_label[observed.label.casefold()].append(evidence_id)
            for index, signal in enumerate(signals[:80]):
                if not isinstance(signal, dict):
                    continue
                kind = str(signal.get("kind", "")).strip().casefold()
                value = str(signal.get("value", "")).strip()
                if not value:
                    continue
                observation_kind = _signal_observation_kind(kind, value)
                matched = [
                    evidence_id
                    for label, ids in evidence_by_label.items()
                    if value.casefold() in label
                    for evidence_id in ids
                ]
                result.append(
                    Observation(
                        id=stable_id("obs", "signal", entity.id, kind, value, index),
                        kind=observation_kind,
                        summary=f"{kind.replace('_', ' ').title()}: {value}",
                        evidence_ids=(matched or entity_evidence)[:10],
                        entity_ids=[entity.id],
                        inputs=[value]
                        if kind in {"form_label", "schema_field", "model_field"}
                        else [],
                        outputs=[value]
                        if kind in {"heading", "jsx_text", "ui_text", "error_message"}
                        else [],
                        terms=_terms(value),
                        structural=observation_kind == ObservationKind.STRUCTURE,
                        confidence=0.92,
                    )
                )

        operation_kind = _operation_kind(entity.name)
        if operation_kind != ObservationKind.STRUCTURE:
            result.append(
                Observation(
                    id=stable_id("obs", "operation", entity.id, operation_kind),
                    kind=operation_kind,
                    summary=(
                        f"{entity.qualified_name} expresses a "
                        f"{operation_kind.value.lower()} operation"
                    ),
                    evidence_ids=entity_evidence[:10],
                    entity_ids=[entity.id],
                    terms=_terms(entity.name),
                    confidence=0.72,
                )
            )

    for relationship in relationships:
        source = entity_by_id.get(relationship.source_id)
        target = entity_by_id.get(relationship.target_id)
        if source is None or target is None:
            continue
        evidence_ids = [item for item in relationship.evidence_ids if item in evidence_by_id]
        if not evidence_ids:
            evidence_ids = [
                item
                for item in [*source.evidence_ids, *target.evidence_ids]
                if item in evidence_by_id
            ][:10]
        if not evidence_ids:
            continue
        relationship_id = stable_id(
            "rel", relationship.source_id, relationship.target_id, relationship.type
        )
        result.append(
            Observation(
                id=stable_id("obs", relationship_id),
                kind=_RELATION_KINDS[relationship.type],
                summary=(
                    f"{source.qualified_name} {relationship.type.value.lower().replace('_', ' ')} "
                    f"{target.qualified_name}"
                ),
                evidence_ids=evidence_ids,
                entity_ids=[source.id, target.id],
                relationship_ids=[relationship_id],
                terms=_terms(f"{source.name} {target.name}"),
                structural=True,
                confidence=relationship.confidence,
            )
        )

    for commit in commits or []:
        evidence_id = stable_id("evcommit", commit.hash)
        if evidence_id not in evidence_by_id:
            continue
        result.append(
            Observation(
                id=stable_id("obs", "commit", commit.hash),
                kind=ObservationKind.TEMPORAL_CHANGE,
                summary=f"Commit {commit.short_hash}: {commit.subject}",
                evidence_ids=[evidence_id],
                terms=_terms(commit.subject),
                confidence=0.96,
            )
        )
    return _deduplicate(result)


def _source_kind(item: ObservedEvidence) -> SourceKind:
    if item.kind == EvidenceKind.COMMIT:
        return SourceKind.GIT
    if item.kind in {EvidenceKind.DOCUMENTATION, EvidenceKind.DOCUMENT_CLAIM}:
        return SourceKind.DOCUMENTATION
    if item.kind == EvidenceKind.TEST:
        return SourceKind.TEST
    if item.kind == EvidenceKind.CONFIGURATION:
        return SourceKind.CONFIGURATION
    if item.kind == EvidenceKind.UI:
        return SourceKind.USER_INTERFACE
    return SourceKind.CODE


def _operation_kind(value: str) -> ObservationKind:
    normalized = " ".join(_terms(value))
    for kind, hints in _OPERATION_HINTS:
        if any(hint in normalized for hint in hints):
            return kind
    return ObservationKind.STRUCTURE


def _signal_observation_kind(kind: str, value: str) -> ObservationKind:
    lowered = value.casefold()
    if kind == "data_operation":
        if any(token in lowered for token in ("save", "insert", "update", "delete", "write")):
            return ObservationKind.PERSISTENCE
        return ObservationKind.DATA_FLOW
    if kind == "constant" and "storage" in lowered and "key" in lowered:
        return ObservationKind.PERSISTENCE
    return _SIGNAL_KINDS.get(kind, _operation_kind(value))


def _terms(value: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", expanded)
        if token.casefold() not in {"src", "test", "tests", "main", "index", "app"}
    ][:24]


def _deduplicate(items: list[Observation]) -> list[Observation]:
    by_id: dict[str, Observation] = {}
    for item in items:
        by_id.setdefault(item.id, item)
    return list(by_id.values())
