from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.analysis.languages import stable_id
from app.analysis.observations import build_observations
from app.domain import (
    BehaviorSummary,
    CodeEntity,
    CodeRelationship,
    ConfidenceDimensions,
    EntityType,
    LensSet,
    Observation,
    ObservationKind,
    ObservedEvidence,
    RelationshipType,
)
from app.taxonomy import DEFAULT_LENS_SET, active_lenses, lens_label


@dataclass(frozen=True, slots=True)
class MechanismCluster:
    entity_ids: frozenset[str]
    relationship_ids: tuple[str, ...]
    structural_support: float


_IMPLEMENTATION_TYPES = {
    EntityType.CLASS,
    EntityType.FUNCTION,
    EntityType.METHOD,
    EntityType.API_ENDPOINT,
    EntityType.UI_COMPONENT,
    EntityType.SCHEMA,
    EntityType.MODULE,
}

_STRONG_RELATIONSHIPS = {
    RelationshipType.CALLS,
    RelationshipType.RENDERS,
    RelationshipType.EXPOSES,
    RelationshipType.READS,
    RelationshipType.WRITES,
    RelationshipType.INSTANTIATES,
    RelationshipType.TESTS,
}

_MECHANISM_BY_OBSERVATION: dict[ObservationKind, str] = {
    ObservationKind.INTERACTION: "INTERACTION",
    ObservationKind.DATA_FLOW: "DATA_FLOW",
    ObservationKind.PERSISTENCE: "PERSISTENCE",
    ObservationKind.TRANSFORMATION: "TRANSFORMATION",
    ObservationKind.VALIDATION: "VALIDATION",
}

# These are operation roles, not product concepts. They generalize across domains.
_ROLE_TERMS: dict[str, tuple[str, ...]] = {
    "SEARCH_FILTER": ("search", "filter", "query", "find", "lookup"),
    "MATCHING": ("match", "similarity", "compare", "align", "overlap"),
    "SCORING": ("score", "rank", "weight", "metric", "evaluate", "fit"),
    "EXTRACTION": ("extract", "scrape", "parse", "decode"),
    "GENERATION": ("generate", "synthesize", "build", "produce"),
    "COMPUTATION": ("calculate", "compute", "solve", "shortest", "simulate", "optimize"),
    "PERSISTENCE": ("save", "store", "persist", "load", "cache", "database"),
    "IMPORT": ("import", "ingest", "upload", "read"),
    "EXPORT": ("export", "download", "serialize", "write"),
    "VALIDATION": ("validate", "guard", "sanitize", "authorize", "permission"),
    "AUTOMATION": ("event", "trigger", "schedule", "queue", "workflow", "retry"),
    "INFERENCE": ("predict", "infer", "embedding", "model", "classify", "llm", "ai"),
    "VISUALIZATION": ("chart", "graph", "plot", "visual", "display"),
    "MANAGEMENT": (
        "manage",
        "create",
        "update",
        "edit",
        "delete",
        "select",
        "track",
        "list",
    ),
    "INTEGRATION": ("client", "fetch", "request", "webhook", "endpoint", "api"),
}

_GENERIC_TERMS = {
    "api",
    "app",
    "array",
    "async",
    "base",
    "button",
    "class",
    "cli",
    "client",
    "component",
    "config",
    "configuration",
    "const",
    "create",
    "data",
    "def",
    "delete",
    "details",
    "engine",
    "error",
    "event",
    "file",
    "form",
    "function",
    "get",
    "handle",
    "handler",
    "helper",
    "index",
    "input",
    "item",
    "items",
    "json",
    "label",
    "list",
    "main",
    "manager",
    "method",
    "model",
    "module",
    "object",
    "output",
    "page",
    "post",
    "process",
    "record",
    "records",
    "render",
    "repository",
    "request",
    "response",
    "result",
    "schema",
    "select",
    "server",
    "service",
    "set",
    "src",
    "state",
    "store",
    "string",
    "test",
    "tests",
    "type",
    "update",
    "util",
    "utils",
    "value",
    "view",
    "operation",
    "persistence",
    "transformation",
    "validation",
    "interaction",
    "extraction",
    "generation",
    "integration",
    "inference",
    "evaluation",
    "computation",
    "workflow",
    "management",
    "search",
    "filter",
    "scoring",
    "matching",
    "import",
    "export",
    "visualization",
    "parse",
    "normalize",
    "calculate",
    "compute",
    "save",
    "load",
    "write",
    "read",
    "find",
    "extract",
    "generate",
    "expresses",
    "express",
    "from",
    "with",
    "without",
    "into",
    "onto",
    "through",
    "that",
    "this",
    "when",
    "where",
    "which",
    "their",
    "each",
    "every",
    "more",
    "only",
    "before",
    "after",
    "using",
    "used",
    "observed",
    "implemented",
    "malformed",
    "controlled",
    "failed",
    "failure",
    "and",
    "the",
    "for",
    "are",
    "not",
    "but",
    "can",
    "will",
    "has",
    "have",
}

_PATH_NOISE = {"backend", "frontend", "lib", "pkg", "package", "public", "source", "static", "web"}


def build_behavior_summaries(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    evidence: list[ObservedEvidence],
    observations: list[Observation] | None = None,
    lens_set: LensSet | None = None,
    *,
    use_relationships: bool = True,
) -> list[BehaviorSummary]:
    """Infer open-world mechanisms first, then synthesize domain behavior names.

    Product phrases are not enumerated here. Names are composed from repository-local
    concepts plus cross-domain operation roles, and every result retains the structural
    and observed facts that caused it.
    """
    selected_lenses = lens_set or DEFAULT_LENS_SET
    normalized = observations or build_observations(entities, relationships, evidence)
    entity_by_id = {item.id: item for item in entities}
    observation_by_entity = _observations_by_entity(normalized)
    clusters = _build_clusters(entities, relationships, use_relationships=use_relationships)
    behaviors: list[BehaviorSummary] = []

    for cluster in clusters:
        cluster_entities = sorted(
            (entity_by_id[item] for item in cluster.entity_ids if item in entity_by_id),
            key=lambda item: (item.file_path, item.line_start, item.id),
        )
        cluster_observations = _cluster_observations(cluster.entity_ids, normalized)
        if not _has_implementation(cluster_entities, cluster_observations):
            continue
        compound_roles = _mechanism_roles(cluster_entities, cluster_observations)
        forced_parent_role = (
            "MANAGEMENT"
            if len(cluster_entities) >= 5
            and any(item.type == EntityType.UI_COMPONENT for item in cluster_entities)
            and len(
                set(compound_roles).intersection(
                    {
                        "SEARCH_FILTER",
                        "PERSISTENCE",
                        "VALIDATION",
                        "SCORING",
                        "MATCHING",
                        "IMPORT",
                        "EXPORT",
                    }
                )
            )
            >= 2
            else None
        )
        behavior = _synthesize_behavior(
            cluster,
            cluster_entities,
            cluster_observations,
            selected_lenses,
            parent_name=None,
            forced_role=forced_parent_role,
        )
        if behavior is None:
            continue
        behaviors.append(behavior)
        behaviors.extend(
            _mechanism_children(
                behavior,
                cluster,
                cluster_entities,
                observation_by_entity,
                selected_lenses,
            )
        )

    behaviors.extend(_configuration_behaviors(entities, normalized, evidence, selected_lenses))
    behaviors.extend(_evaluation_behaviors(entities, relationships, normalized, selected_lenses))
    return _merge_behaviors(behaviors)


def _build_clusters(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    *,
    use_relationships: bool,
) -> list[MechanismCluster]:
    eligible = {item.id for item in entities if item.type in _IMPLEMENTATION_TYPES}
    adjacency: dict[str, set[str]] = defaultdict(set)
    relationship_ids: dict[frozenset[str], set[str]] = defaultdict(set)
    if use_relationships:
        for item in relationships:
            if item.source_id not in eligible or item.target_id not in eligible:
                continue
            if item.type not in _STRONG_RELATIONSHIPS and item.type != RelationshipType.CONTAINS:
                continue
            adjacency[item.source_id].add(item.target_id)
            adjacency[item.target_id].add(item.source_id)
            relationship_ids[frozenset({item.source_id, item.target_id})].add(
                _relationship_id(item)
            )

    # Source files are only a starting partition. Relationship neighborhoods can cross them.
    by_file: dict[str, set[str]] = defaultdict(set)
    for item in entities:
        if item.id in eligible:
            by_file[item.file_path].add(item.id)

    seeds = [
        item
        for item in entities
        if item.id in eligible
        and (
            item.type
            in {
                EntityType.API_ENDPOINT,
                EntityType.UI_COMPONENT,
                EntityType.CLASS,
                EntityType.SCHEMA,
            }
            or item.metadata.get("entrypoint")
        )
    ]
    raw: list[set[str]] = []
    for seed in seeds:
        members = set(by_file[seed.file_path])
        if use_relationships:
            queue = deque([(seed.id, 0)])
            members.add(seed.id)
            while queue and len(members) < 48:
                current, depth = queue.popleft()
                if depth >= 2:
                    continue
                for neighbor in adjacency[current]:
                    if neighbor not in members:
                        members.add(neighbor)
                        queue.append((neighbor, depth + 1))
        raw.append(members)
    raw.extend(by_file.values())

    # Merge nearly identical neighborhoods, while preserving separate domain workflows.
    merged: list[set[str]] = []
    for members in sorted(raw, key=lambda item: (-len(item), sorted(item))):
        if not members:
            continue
        target = next(
            (
                existing
                for existing in merged
                if len(existing & members) / max(1, len(existing | members)) >= 0.68
            ),
            None,
        )
        if target is None:
            merged.append(set(members))
        else:
            target.update(members)

    # Attach directly tested implementations, but do not let tests create product clusters.
    for item in relationships:
        if item.type != RelationshipType.TESTS or item.target_id not in eligible:
            continue
        for members in merged:
            if item.target_id in members:
                members.add(item.source_id)

    result: list[MechanismCluster] = []
    for members in merged:
        implementation = {item for item in members if item in eligible}
        if not implementation:
            continue
        rel_ids = sorted(
            {
                rel_id
                for pair, ids in relationship_ids.items()
                if pair.issubset(members)
                for rel_id in ids
            }
        )
        possible = max(1, len(implementation) - 1)
        result.append(
            MechanismCluster(
                entity_ids=frozenset(members),
                relationship_ids=tuple(rel_ids),
                structural_support=min(1.0, len(rel_ids) / possible) if use_relationships else 0.0,
            )
        )
    return result


def _synthesize_behavior(
    cluster: MechanismCluster,
    entities: list[CodeEntity],
    observations: list[Observation],
    lens_set: LensSet,
    parent_name: str | None,
    forced_role: str | None = None,
) -> BehaviorSummary | None:
    implementation = [item for item in entities if item.type in _IMPLEMENTATION_TYPES]
    evidence_ids = _unique(
        evidence_id
        for item in observations
        if item.kind != ObservationKind.DOCUMENT_CLAIM
        for evidence_id in item.evidence_ids
    )[:140]
    if not implementation or not evidence_ids:
        return None
    terms = _rank_terms(implementation, observations)
    roles = _mechanism_roles(implementation, observations)
    if forced_role:
        roles = [forced_role, *[item for item in roles if item != forced_role]]
    concept = _concept_label(
        implementation,
        observations,
        terms,
        surface_role=forced_role if forced_role == "MANAGEMENT" else None,
    )
    role = roles[0] if roles else "DOMAIN_BEHAVIOR"
    name = _behavior_name(concept, role)
    if not name or _artifact_name(name):
        name = _fallback_name(concept, implementation, roles)
    primary_lens, secondary_lenses = _project_lenses(roles, terms, lens_set, implementation)
    label = lens_label(lens_set, primary_lens)
    observation_ids = [
        item.id for item in observations if item.kind != ObservationKind.DOCUMENT_CLAIM
    ]
    inputs = _unique(value for item in observations for value in item.inputs)[:12]
    outputs = _unique(value for item in observations for value in item.outputs)[:12]
    ui = _unique(item.name for item in implementation if item.type == EntityType.UI_COMPONENT)[:12]
    api = _unique(
        str(item.metadata.get("route_path") or item.metadata.get("route") or item.name)
        for item in implementation
        if item.type == EntityType.API_ENDPOINT
    )[:12]
    tests = _unique(
        str(item.metadata.get("test_label") or item.name)
        for item in entities
        if item.type == EntityType.TEST
    )[:12]
    evidence_confidence = min(0.98, 0.48 + 0.04 * min(len(set(evidence_ids)), 8))
    behavior_confidence = min(
        0.96,
        0.42
        + cluster.structural_support * 0.3
        + (0.1 if len(implementation) >= 2 else 0)
        + (0.08 if ui or api else 0),
    )
    semantic_confidence = min(0.94, 0.4 + 0.07 * min(len(terms), 6))
    confidence = round((evidence_confidence + behavior_confidence + semantic_confidence) / 3, 2)
    entity_ids = [item.id for item in entities]
    behavior_id = stable_id("behavior", primary_lens, name, *sorted(entity_ids)[:30])
    return BehaviorSummary(
        id=behavior_id,
        name=name,
        description=_description(name, roles, inputs, outputs, ui, api),
        mechanism_types=roles,
        primary_lens=primary_lens,
        secondary_lenses=secondary_lenses,
        primary_category=label,
        secondary_categories=[lens_label(lens_set, item) for item in secondary_lenses],
        parent_name=parent_name,
        supporting_entity_ids=entity_ids[:100],
        supporting_relationships=list(cluster.relationship_ids)[:120],
        observation_ids=observation_ids[:160],
        evidence_ids=evidence_ids,
        observable_inputs=inputs,
        observable_outputs=outputs,
        ui_surfaces=ui,
        api_paths=api,
        tests=tests,
        semantic_terms=terms[:16],
        confidence=confidence,
        confidence_dimensions=ConfidenceDimensions(
            evidence=round(evidence_confidence, 2),
            behavior=round(behavior_confidence, 2),
            semantic=round(semantic_confidence, 2),
            temporal=0,
        ),
    )


def _mechanism_children(
    parent: BehaviorSummary,
    cluster: MechanismCluster,
    entities: list[CodeEntity],
    observations_by_entity: dict[str, list[Observation]],
    lens_set: LensSet,
) -> list[BehaviorSummary]:
    # Only decompose a genuinely compound behavior. Small clusters remain readable.
    if len([item for item in entities if item.type in _IMPLEMENTATION_TYPES]) < 5:
        return []
    by_role: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        observations = observations_by_entity.get(entity.id, [])
        for role in _mechanism_roles([entity], observations):
            if role not in {"DOMAIN_BEHAVIOR", "INTERACTION"}:
                by_role[role].add(entity.id)
    independently_observable = {
        "PERSISTENCE",
        "VALIDATION",
        "EXTRACTION",
        "IMPORT",
        "EXPORT",
        "INFERENCE",
        "SCORING",
        "MATCHING",
    }
    strong = [
        (role, ids)
        for role, ids in by_role.items()
        if len(ids) >= 2 or (ids and role in independently_observable)
    ]
    strong.sort(key=lambda item: (-len(item[1]), item[0]))
    if len(strong) < 2:
        return []
    children: list[BehaviorSummary] = []
    by_id = {item.id: item for item in entities}
    for role, ids in strong[:10]:
        child_entities = sorted(
            (by_id[item] for item in ids if item in by_id),
            key=lambda item: (item.file_path, item.line_start, item.id),
        )
        child_observations = _unique_objects(
            item for entity_id in ids for item in observations_by_entity.get(entity_id, [])
        )
        child_cluster = MechanismCluster(
            entity_ids=frozenset(ids),
            # Relationship IDs are intentionally opaque stable hashes. Retain the
            # bounded parent neighborhood so the child keeps structural provenance;
            # its entity/observation lists still identify the narrower mechanism.
            relationship_ids=cluster.relationship_ids,
            structural_support=cluster.structural_support,
        )
        child = _synthesize_behavior(
            child_cluster,
            child_entities,
            child_observations,
            lens_set,
            parent_name=parent.name,
            forced_role=role,
        )
        if child and child.name != parent.name:
            parent_concept = set(_tokens(parent.name)) - set(
                _tokens(_behavior_name("", parent.mechanism_types[0]))
            )
            child_concept = set(_tokens(child.name)) - set(_tokens(_behavior_name("", role)))
            if not parent_concept.intersection(child_concept):
                executable_count = sum(
                    item.type not in {EntityType.MODULE, EntityType.TEST} for item in child_entities
                )
                parent_has_ui = any(item.type == EntityType.UI_COMPONENT for item in entities)
                inherited_concept = " ".join(token.title() for token in sorted(parent_concept))
                inherits_surface_domain = role in {
                    "SEARCH_FILTER",
                    "PERSISTENCE",
                    "IMPORT",
                    "EXPORT",
                    "VALIDATION",
                    "DATA_FLOW",
                }
                if parent_has_ui and inherits_surface_domain:
                    child.name = _behavior_name(inherited_concept, role)
                    child.id = stable_id(
                        "behavior",
                        child.primary_lens,
                        child.name,
                        *sorted(child.supporting_entity_ids),
                    )
                elif not parent_has_ui and child_concept.intersection(set(parent.semantic_terms)):
                    combined = " ".join(
                        token.title() for token in [*sorted(parent_concept), *sorted(child_concept)]
                    )
                    child.name = _behavior_name(combined, role)
                    child.id = stable_id(
                        "behavior",
                        child.primary_lens,
                        child.name,
                        *sorted(child.supporting_entity_ids),
                    )
                elif executable_count >= 2:
                    child.parent_name = None
                elif not parent_has_ui:
                    child.name = _behavior_name(inherited_concept, role)
                    child.id = stable_id(
                        "behavior",
                        child.primary_lens,
                        child.name,
                        *sorted(child.supporting_entity_ids),
                    )
                else:
                    continue
            children.append(child)
    return children


def _configuration_behaviors(
    entities: list[CodeEntity],
    observations: list[Observation],
    evidence: list[ObservedEvidence],
    lens_set: LensSet,
) -> list[BehaviorSummary]:
    evidence_by_id = {item.id: item for item in evidence}
    result: list[BehaviorSummary] = []
    for entity in entities:
        if entity.type != EntityType.CONFIGURATION:
            continue
        path = entity.file_path.casefold()
        roles: list[str] = []
        name = ""
        if ".github/workflows" in path or "gitlab-ci" in path or "jenkins" in path:
            roles, name = ["CONTINUOUS_INTEGRATION", "OPERATIONS"], "Continuous Integration"
        elif "dockerfile" in path or "compose" in path or "kubernetes" in path:
            roles, name = ["DISTRIBUTION", "OPERATIONS"], "Containerized Distribution"
        elif PurePosixPath(path).name in {
            "pyproject.toml",
            "package.json",
            "setup.py",
            "cargo.toml",
        }:
            roles, name = ["DISTRIBUTION"], "Package Distribution"
        if not roles:
            continue
        evidence_ids = [item for item in entity.evidence_ids if item in evidence_by_id]
        if not evidence_ids:
            continue
        primary, secondary = _project_lenses(roles, [], lens_set, [entity])
        result.append(
            BehaviorSummary(
                id=stable_id("behavior", primary, name, entity.id),
                name=name,
                description=f"Configuration evidence implements {name.lower()} behavior.",
                mechanism_types=roles,
                primary_lens=primary,
                secondary_lenses=secondary,
                primary_category=lens_label(lens_set, primary),
                secondary_categories=[lens_label(lens_set, item) for item in secondary],
                supporting_entity_ids=[entity.id],
                observation_ids=[item.id for item in observations if entity.id in item.entity_ids],
                evidence_ids=evidence_ids,
                semantic_terms=_tokens(path),
                confidence=0.76,
                confidence_dimensions=ConfidenceDimensions(
                    evidence=0.9, behavior=0.72, semantic=0.78, temporal=0
                ),
            )
        )
    return result


def _evaluation_behaviors(
    entities: list[CodeEntity],
    relationships: list[CodeRelationship],
    observations: list[Observation],
    lens_set: LensSet,
) -> list[BehaviorSummary]:
    tests_by_file: dict[str, list[CodeEntity]] = defaultdict(list)
    for item in entities:
        if item.type == EntityType.TEST:
            tests_by_file[item.file_path].append(item)
    result: list[BehaviorSummary] = []
    for tests in tests_by_file.values():
        if len(tests) < 2:
            continue
        test_ids = {item.id for item in tests}
        test_relationships = [
            item
            for item in relationships
            if item.type == RelationshipType.TESTS and item.source_id in test_ids
        ]
        targets = {item.target_id for item in test_relationships}
        if not targets:
            continue
        target_entities = [item for item in entities if item.id in targets]
        supporting = [*tests, *target_entities]
        supporting_ids = {item.id for item in supporting}
        relevant = [
            item for item in observations if set(item.entity_ids).intersection(supporting_ids)
        ]
        target_observations = [
            item
            for item in relevant
            if set(item.entity_ids).intersection(targets)
            and item.kind != ObservationKind.TEST_BEHAVIOR
        ]
        evidence_ids = _unique(
            evidence_id for item in relevant for evidence_id in item.evidence_ids
        )
        if not evidence_ids:
            continue
        terms = _rank_terms(supporting, relevant)
        # Test prose is excellent corroboration, but implementation targets provide the
        # stable domain anchor. This avoids names based on incidental assertion wording
        # such as "returns rendered output" while preserving that prose as evidence.
        target_terms = _rank_terms(target_entities, target_observations)
        concept = _concept_label(target_entities, target_observations, target_terms)
        if not concept:
            concept = _concept_label(supporting, relevant, terms)
        name = f"{concept} Evaluation" if concept else "Automated Behavioral Evaluation"
        primary, secondary = _project_lenses(["EVALUATION"], terms, lens_set, supporting)
        result.append(
            BehaviorSummary(
                id=stable_id("behavior", primary, name, *sorted(test_ids)),
                name=name,
                description="Executable tests verify implemented behavior and failure paths.",
                mechanism_types=["EVALUATION"],
                primary_lens=primary,
                secondary_lenses=secondary,
                primary_category=lens_label(lens_set, primary),
                secondary_categories=[lens_label(lens_set, item) for item in secondary],
                supporting_entity_ids=[item.id for item in supporting],
                supporting_relationships=[_relationship_id(item) for item in test_relationships],
                observation_ids=[item.id for item in relevant],
                evidence_ids=evidence_ids,
                tests=[str(item.metadata.get("test_label") or item.name) for item in tests],
                semantic_terms=terms[:16],
                confidence=0.82,
                confidence_dimensions=ConfidenceDimensions(
                    evidence=0.94, behavior=0.86, semantic=0.68, temporal=0
                ),
            )
        )
    return result


def _mechanism_roles(entities: list[CodeEntity], observations: list[Observation]) -> list[str]:
    raw_text = " ".join(
        [item.name for item in entities if item.type != EntityType.TEST]
        + [
            item.summary
            for item in observations
            if not item.structural and item.kind != ObservationKind.TEST_BEHAVIOR
        ]
        + [
            term
            for item in observations
            if not item.structural and item.kind != ObservationKind.TEST_BEHAVIOR
            for term in item.terms
        ]
    )
    text = " ".join(_tokens(raw_text))
    counts: Counter[str] = Counter()
    for item in observations:
        if item.structural:
            continue
        mechanism = _MECHANISM_BY_OBSERVATION.get(item.kind)
        if mechanism:
            counts[mechanism] += 1
    for role, terms in _ROLE_TERMS.items():
        hits = sum(len(re.findall(rf"\b{re.escape(term)}\w*\b", text)) for term in terms)
        if hits:
            counts[role] += hits * 2
    if any(item.type == EntityType.UI_COMPONENT for item in entities):
        counts["INTERACTION"] += 4
    if any(item.type == EntityType.API_ENDPOINT for item in entities):
        counts["INTEGRATION"] += 2
    if any(item.type == EntityType.SCHEMA for item in entities):
        counts["DATA_FLOW"] += 2
    return [item for item, _ in counts.most_common()] or ["DOMAIN_BEHAVIOR"]


def _rank_terms(entities: list[CodeEntity], observations: list[Observation]) -> list[str]:
    score: Counter[str] = Counter()
    observations_by_entity = _observations_by_entity(observations)
    for entity in entities:
        weight = (
            4
            if entity.type in {EntityType.SCHEMA, EntityType.UI_COMPONENT, EntityType.API_ENDPOINT}
            else 2
        )
        name_terms = {_singular(token) for token in _tokens(entity.name)}
        for token in name_terms:
            if not _is_generic_token(token):
                score[token] += weight
        for token in _tokens(PurePosixPath(entity.file_path).stem):
            if token not in _PATH_NOISE and not _is_generic_token(token):
                score[token] += 1
        local_observations = observations_by_entity.get(entity.id, [])
        local_terms = {
            _singular(token)
            for observation in local_observations
            if observation.kind != ObservationKind.DOCUMENT_CLAIM and not observation.structural
            for token in observation.terms
            if not _is_generic_token(_singular(token))
        }
        observation_weight = 3 if entity.type in {EntityType.UI_COMPONENT, EntityType.TEST} else 1
        for token in local_terms:
            score[token] += observation_weight
    return [item for item, _ in score.most_common(20)]


def _concept_label(
    entities: list[CodeEntity],
    observations: list[Observation],
    terms: list[str],
    surface_role: str | None = None,
) -> str:
    if surface_role and any(item.type == EntityType.UI_COMPONENT for item in entities):
        anchored = _surface_concept(observations, terms, surface_role)
        if anchored:
            return anchored.title()
    phrases: Counter[tuple[str, ...]] = Counter()
    values = [item.name for item in entities if item.type != EntityType.MODULE]
    values.extend(
        item.summary.split(":", 1)[-1]
        for item in observations
        if item.kind not in {ObservationKind.DOCUMENT_CLAIM, ObservationKind.STRUCTURE}
        and not item.structural
    )
    for value in values:
        tokens = [
            _singular(item)
            for item in _tokens(value)
            if not _is_generic_token(_singular(item)) and item not in _PATH_NOISE
        ]
        for width in (2, 1):
            for index in range(max(0, len(tokens) - width + 1)):
                phrase = tuple(tokens[index : index + width])
                if phrase:
                    phrases[phrase] += width + 1
    if phrases:
        best = max(phrases, key=lambda item: (phrases[item], len(item), item))
        return " ".join(token.title() for token in best)
    return " ".join(item.title() for item in terms[:2])


def _behavior_name(concept: str, role: str) -> str:
    suffix = {
        "SEARCH_FILTER": "Search & Filtering",
        "MATCHING": "Matching",
        "SCORING": "Scoring",
        "EXTRACTION": "Extraction",
        "GENERATION": "Generation",
        "COMPUTATION": "Computation",
        "PERSISTENCE": "Persistence",
        "IMPORT": "Import",
        "EXPORT": "Export",
        "VALIDATION": "Validation",
        "AUTOMATION": "Automation",
        "INFERENCE": "Inference",
        "VISUALIZATION": "Visualization",
        "MANAGEMENT": "Management",
        "INTEGRATION": "Integration",
        "EXTERNAL_INTEGRATION": "Integration",
        "DATA_FLOW": "State",
        "TRANSFORMATION": "Transformation",
        "INTERACTION": "Interaction",
        "EVALUATION": "Evaluation",
        "DOMAIN_BEHAVIOR": "Workflow",
    }.get(role, role.replace("_", " ").title())
    if not concept:
        return suffix
    concept_terms = set(_tokens(concept))
    suffix_terms = set(_tokens(suffix))
    if concept_terms and concept_terms.issubset(suffix_terms):
        return suffix
    return f"{concept} {suffix}".strip()


def _fallback_name(concept: str, entities: list[CodeEntity], roles: list[str]) -> str:
    if concept:
        return f"{concept} Workflow"
    if any(item.type == EntityType.UI_COMPONENT for item in entities):
        return "Interactive Workflow"
    if "TRANSFORMATION" in roles or "DATA_FLOW" in roles:
        return "Data Transformation Workflow"
    return "Implemented Domain Workflow"


def _project_lenses(
    roles: list[str],
    terms: list[str],
    lens_set: LensSet,
    entities: list[CodeEntity],
) -> tuple[str, list[str]]:
    lenses = active_lenses(lens_set)
    text = " ".join([*roles, *terms]).casefold().replace("_", " ")
    scores: Counter[str] = Counter()
    for lens in lenses:
        for signal in lens.signals:
            if signal.casefold() in text:
                scores[lens.id] += 2
    preferred = {
        "INTERACTION": "experience-interaction",
        "VISUALIZATION": "experience-interaction",
        "SEARCH_FILTER": "experience-interaction",
        "PERSISTENCE": "data-state",
        "DATA_FLOW": "data-state",
        "IMPORT": "data-state",
        "EXPORT": "data-state",
        "INFERENCE": "knowledge-intelligence",
        "AUTOMATION": "automation-agency",
        "INTEGRATION": "interfaces-ecosystem",
        "EXTERNAL_INTEGRATION": "interfaces-ecosystem",
        "VALIDATION": "trust-governance",
        "EVALUATION": "quality-evaluation",
        "OPERATIONS": "operations-scale",
        "CONTINUOUS_INTEGRATION": "operations-scale",
        "DISTRIBUTION": "distribution-ecosystem",
        "COMPUTATION": "domain-capability",
        "GENERATION": "domain-capability",
        "MATCHING": "domain-capability",
        "SCORING": "domain-capability",
        "EXTRACTION": "domain-capability",
        "MANAGEMENT": "domain-capability",
        "TRANSFORMATION": "domain-capability",
        "DOMAIN_BEHAVIOR": "domain-capability",
    }
    available = {item.id for item in lenses}
    for index, role in enumerate(roles):
        if (lens_id := preferred.get(role)) in available:
            scores[lens_id] += 20 if index == 0 else 4
    if (
        any(item.type == EntityType.UI_COMPONENT for item in entities)
        and "experience-interaction" in available
    ):
        scores["experience-interaction"] += 3
    if (
        any(item.type == EntityType.API_ENDPOINT for item in entities)
        and "interfaces-ecosystem" in available
    ):
        scores["interfaces-ecosystem"] += 2
    fallback = "domain-capability" if "domain-capability" in available else lenses[0].id
    ordered = [item for item, _ in scores.most_common() if item in available]
    primary = ordered[0] if ordered else fallback
    return primary, [item for item in ordered[1:4] if item != primary]


def _description(
    name: str,
    roles: list[str],
    inputs: list[str],
    outputs: list[str],
    ui: list[str],
    api: list[str],
) -> str:
    surfaces = [*(f"UI {item}" for item in ui[:2]), *(f"API {item}" for item in api[:2])]
    detail = f" through {', '.join(surfaces)}" if surfaces else ""
    flow = ""
    if inputs or outputs:
        input_text = ", ".join(inputs[:3]) or "observed values"
        output_text = ", ".join(outputs[:3]) or "implemented results"
        flow = f" Inputs include {input_text}; outputs include {output_text}."
    mechanisms = ", ".join(item.lower().replace("_", " ") for item in roles[:3])
    return f"Implements {name.lower()}{detail} using {mechanisms}.{flow}"


def _has_implementation(entities: list[CodeEntity], observations: list[Observation]) -> bool:
    executable = [
        item
        for item in entities
        if item.type in _IMPLEMENTATION_TYPES
        and item.type not in {EntityType.MODULE, EntityType.TEST}
    ]
    if len(executable) >= 2:
        return True
    return any(
        item.type in {EntityType.API_ENDPOINT, EntityType.UI_COMPONENT, EntityType.SCHEMA}
        for item in executable
    )


def _surface_concept(
    observations: list[Observation], ranked_terms: list[str], preferred_role: str
) -> str:
    scores: Counter[str] = Counter()
    rank = {term: index for index, term in enumerate(ranked_terms)}
    for observation in observations:
        if (
            observation.structural
            or observation.kind != ObservationKind.INTERACTION
            or not observation.summary.startswith(("Ui Text:", "Form Label:", "Button Label:"))
        ):
            continue
        tokens = [_singular(item) for item in _tokens(observation.summary.split(":", 1)[-1])]
        preferred_operations = _ROLE_TERMS.get(preferred_role, ())
        action_indexes = [
            index
            for index, token in enumerate(tokens)
            if any(token.startswith(operation) for operation in preferred_operations)
        ]
        if not action_indexes:
            continue
        weight = 6 if len(tokens) <= 9 else 2
        domain_indexes = [
            index
            for index, token in enumerate(tokens)
            if not _is_generic_token(token) and token not in _PATH_NOISE
        ]
        for action_index in action_indexes:
            if domain_indexes:
                closest = min(domain_indexes, key=lambda index: abs(index - action_index))
                scores[tokens[closest]] += weight
    if not scores:
        return ""
    return max(scores, key=lambda item: (scores[item], -rank.get(item, 999), item))


def _is_generic_token(token: str) -> bool:
    if token in _GENERIC_TERMS:
        return True
    return any(
        token.startswith(operation)
        for operations in _ROLE_TERMS.values()
        for operation in operations
        if len(operation) >= 4
    )


def _artifact_name(name: str) -> bool:
    normalized = " ".join(_tokens(name))
    return normalized in {
        "api surface",
        "json engine",
        "react component",
        "data parser",
        "express server",
        "helper utilities",
        "user interface",
        "implemented domain workflow",
    }


def _observations_by_entity(observations: list[Observation]) -> dict[str, list[Observation]]:
    result: dict[str, list[Observation]] = defaultdict(list)
    for item in observations:
        for entity_id in item.entity_ids:
            result[entity_id].append(item)
    return result


def _cluster_observations(
    entity_ids: frozenset[str], observations: list[Observation]
) -> list[Observation]:
    return [item for item in observations if set(item.entity_ids).intersection(entity_ids)]


def _merge_behaviors(items: list[BehaviorSummary]) -> list[BehaviorSummary]:
    result: list[BehaviorSummary] = []
    by_key: dict[str, BehaviorSummary] = {}
    for item in sorted(items, key=lambda value: (-value.confidence, value.name)):
        key = _normalized_name(item.name)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = item
            result.append(item)
            continue
        existing.supporting_entity_ids = _unique(
            [*existing.supporting_entity_ids, *item.supporting_entity_ids]
        )[:100]
        existing.supporting_relationships = _unique(
            [*existing.supporting_relationships, *item.supporting_relationships]
        )[:120]
        existing.observation_ids = _unique([*existing.observation_ids, *item.observation_ids])[:160]
        existing.evidence_ids = _unique([*existing.evidence_ids, *item.evidence_ids])[:140]
        existing.semantic_terms = _unique([*existing.semantic_terms, *item.semantic_terms])[:20]
        existing.tests = _unique([*existing.tests, *item.tests])[:16]
        existing.secondary_lenses = _unique(
            [
                *existing.secondary_lenses,
                *(value for value in [item.primary_lens, *item.secondary_lenses] if value),
            ]
        )[:4]
        existing.secondary_categories = _unique(
            [*existing.secondary_categories, item.primary_category, *item.secondary_categories]
        )[:4]
        existing.confidence = max(existing.confidence, item.confidence)
    # Do not show a parent pointer to a behavior eliminated during deduplication.
    names = {item.name for item in result}
    for item in result:
        if item.parent_name not in names:
            item.parent_name = None
    return result[:80]


def _normalized_name(value: str) -> str:
    tokens = [_singular(item) for item in _tokens(value)]
    return " ".join(tokens)


def _tokens(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [item.casefold() for item in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", value)]


def _singular(value: str) -> str:
    if value.endswith("sis"):
        return value
    if value.endswith("sses") and len(value) > 5:
        return value[:-2]
    if value.endswith("ies") and len(value) > 4:
        return f"{value[:-3]}y"
    if value.endswith("s") and not value.endswith(("ss", "us")) and len(value) > 4:
        return value[:-1]
    return value


def _relationship_id(item: CodeRelationship) -> str:
    return stable_id("rel", item.source_id, item.target_id, item.type)


def _unique[T](items) -> list[T]:
    return list(dict.fromkeys(items))


def _unique_objects[T](items) -> list[T]:
    result: list[T] = []
    seen: set[str] = set()
    for item in items:
        item_id = getattr(item, "id", repr(item))
        if item_id not in seen:
            seen.add(item_id)
            result.append(item)
    return result
