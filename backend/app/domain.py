from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class EvidenceKind(StrEnum):
    SOURCE = "SOURCE"
    TEST = "TEST"
    API = "API"
    SCHEMA = "SCHEMA"
    UI = "UI"
    CONFIGURATION = "CONFIGURATION"
    DEPENDENCY = "DEPENDENCY"
    COMMIT = "COMMIT"
    DOCUMENTATION = "DOCUMENTATION"
    SEMANTIC = "SEMANTIC"
    DOCUMENT_CLAIM = "DOCUMENT_CLAIM"


class SourceKind(StrEnum):
    CODE = "CODE"
    TEST = "TEST"
    CONFIGURATION = "CONFIGURATION"
    USER_INTERFACE = "USER_INTERFACE"
    DOCUMENTATION = "DOCUMENTATION"
    GIT = "GIT"


class ObservationKind(StrEnum):
    STRUCTURE = "STRUCTURE"
    INTERACTION = "INTERACTION"
    DATA_FLOW = "DATA_FLOW"
    PERSISTENCE = "PERSISTENCE"
    TRANSFORMATION = "TRANSFORMATION"
    VALIDATION = "VALIDATION"
    EXTERNAL_CALL = "EXTERNAL_CALL"
    TEST_BEHAVIOR = "TEST_BEHAVIOR"
    CONFIGURATION = "CONFIGURATION"
    DOCUMENT_CLAIM = "DOCUMENT_CLAIM"
    TEMPORAL_CHANGE = "TEMPORAL_CHANGE"


class LensStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class CapabilityStateKind(StrEnum):
    INTRODUCED = "INTRODUCED"
    STRENGTHENED = "STRENGTHENED"
    REFACTORED = "REFACTORED"
    SPLIT = "SPLIT"
    MERGED = "MERGED"
    DEPRECATED = "DEPRECATED"
    REMOVED = "REMOVED"


class EntityType(StrEnum):
    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    API_ENDPOINT = "API_ENDPOINT"
    UI_COMPONENT = "UI_COMPONENT"
    SCHEMA = "SCHEMA"
    TEST = "TEST"
    CONFIGURATION = "CONFIGURATION"
    EXTERNAL_MODULE = "EXTERNAL_MODULE"


class RelationshipType(StrEnum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    INSTANTIATES = "INSTANTIATES"
    READS = "READS"
    WRITES = "WRITES"
    EXPOSES = "EXPOSES"
    TESTS = "TESTS"
    RENDERS = "RENDERS"
    DEPENDS_ON = "DEPENDS_ON"


class MaturityState(StrEnum):
    DISCOVERED = "DISCOVERED"
    SCAFFOLDED = "SCAFFOLDED"
    FUNCTIONAL = "FUNCTIONAL"
    INTEGRATED = "INTEGRATED"
    VALIDATED = "VALIDATED"
    PRODUCTIONIZED = "PRODUCTIONIZED"


class ChangeType(StrEnum):
    NEW_CAPABILITY = "NEW_CAPABILITY"
    ENHANCEMENT = "ENHANCEMENT"
    REFACTOR = "REFACTOR"
    BUG_FIX = "BUG_FIX"
    MIGRATION = "MIGRATION"
    TEST_MATURATION = "TEST_MATURATION"
    DOCUMENTATION = "DOCUMENTATION"
    OPERATIONS = "OPERATIONS"
    REMOVAL = "REMOVAL"


class ObservedEvidence(BaseModel):
    id: str
    kind: EvidenceKind
    label: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    symbol: str | None = None
    commit_hash: str | None = None
    observed_at: datetime | None = None
    detail: str | None = None
    source_kind: SourceKind | None = None
    source_revision: str | None = None


class Observation(BaseModel):
    """A normalized, source-independent statement grounded in observed evidence."""

    id: str
    kind: ObservationKind
    summary: str
    evidence_ids: list[str] = Field(min_length=1)
    entity_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    structural: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)


class LensDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    label: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=400)
    version: str = "1.0"
    status: LensStatus = LensStatus.ACTIVE
    aliases: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)


class LensSet(BaseModel):
    id: str = "roadtrace-default"
    version: str = "1.0"
    lenses: list[LensDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_lenses(self) -> LensSet:
        ids = [item.id for item in self.lenses]
        labels = [item.label.casefold() for item in self.lenses]
        if len(ids) != len(set(ids)) or len(labels) != len(set(labels)):
            raise ValueError("lens ids and labels must be unique")
        if not any(item.status == LensStatus.ACTIVE for item in self.lenses):
            raise ValueError("a lens set must contain at least one active lens")
        return self


class ConfidenceDimensions(BaseModel):
    evidence: float = Field(default=0.5, ge=0, le=1)
    behavior: float = Field(default=0.5, ge=0, le=1)
    semantic: float = Field(default=0.5, ge=0, le=1)
    temporal: float = Field(default=0.0, ge=0, le=1)


class CapabilityTrait(BaseModel):
    id: str
    label: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0, le=1)


class KnowledgeQuality(BaseModel):
    breadth: str | None = None
    depth: str | None = None
    executability: str | None = None
    grounding: str | None = None
    freshness: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class CodeEntity(BaseModel):
    id: str
    type: EntityType
    name: str
    qualified_name: str
    file_path: str
    line_start: int = 1
    line_end: int = 1
    language: str
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeRelationship(BaseModel):
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    inferred: bool = False


class CommitRecord(BaseModel):
    hash: str
    short_hash: str
    timestamp: datetime
    author: str
    subject: str
    changed_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    change_type: ChangeType = ChangeType.ENHANCEMENT


class MaturitySignals(BaseModel):
    implementation: bool = False
    reachable: bool = False
    exposed: bool = False
    tests: bool = False
    validation: bool = False
    operations: bool = False
    documentation: bool = False
    monitoring: bool = False


class Capability(BaseModel):
    id: str
    name: str
    description: str
    primary_lens: str | None = None
    secondary_lenses: list[str] = Field(default_factory=list)
    # Kept in the API during the V0.1 migration. It mirrors the primary lens label.
    category: str | None = None
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    behavior_ids: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    secondary_categories: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    traits: list[CapabilityTrait] = Field(default_factory=list)
    knowledge_quality: KnowledgeQuality | None = None
    entity_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    commit_hashes: list[str] = Field(default_factory=list)
    first_seen: datetime | None = None
    last_changed: datetime | None = None
    maturity: MaturityState
    maturity_signals: MaturitySignals
    confidence: float = Field(ge=0, le=1)
    confidence_dimensions: ConfidenceDimensions = Field(default_factory=ConfidenceDimensions)
    reasoning_summary: str

    @model_validator(mode="after")
    def synchronize_lens_compatibility(self) -> Capability:
        if not self.primary_lens and self.category:
            self.primary_lens = self.category
        if not self.category and self.primary_lens:
            self.category = self.primary_lens
        if not self.secondary_lenses and self.secondary_categories:
            self.secondary_lenses = list(self.secondary_categories)
        if not self.secondary_categories and self.secondary_lenses:
            self.secondary_categories = list(self.secondary_lenses)
        if not self.primary_lens or not self.category:
            raise ValueError("capability requires a primary lens")
        return self


class BehaviorSummary(BaseModel):
    id: str
    name: str
    description: str
    mechanism_types: list[str] = Field(default_factory=list)
    primary_lens: str | None = None
    secondary_lenses: list[str] = Field(default_factory=list)
    primary_category: str | None = None
    secondary_categories: list[str] = Field(default_factory=list)
    parent_name: str | None = None
    supporting_entity_ids: list[str] = Field(default_factory=list)
    supporting_relationships: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    observable_inputs: list[str] = Field(default_factory=list)
    observable_outputs: list[str] = Field(default_factory=list)
    ui_surfaces: list[str] = Field(default_factory=list)
    api_paths: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    semantic_terms: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    confidence_dimensions: ConfidenceDimensions = Field(default_factory=ConfidenceDimensions)

    @model_validator(mode="after")
    def synchronize_lens_compatibility(self) -> BehaviorSummary:
        if not self.primary_lens and self.primary_category:
            self.primary_lens = self.primary_category
        if not self.primary_category and self.primary_lens:
            self.primary_category = self.primary_lens
        if not self.secondary_lenses and self.secondary_categories:
            self.secondary_lenses = list(self.secondary_categories)
        if not self.secondary_categories and self.secondary_lenses:
            self.secondary_categories = list(self.secondary_lenses)
        if not self.primary_lens:
            raise ValueError("behavior requires a primary lens")
        return self


class CapabilityState(BaseModel):
    id: str
    capability_id: str
    kind: CapabilityStateKind
    timestamp: datetime
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    behavior_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)


class TimelineEvent(BaseModel):
    id: str
    capability_id: str
    timestamp: datetime
    change_type: ChangeType
    title: str
    summary: str
    commit_hash: str
    evidence_ids: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    group: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    confidence: float = Field(default=1, ge=0, le=1)
    inferred: bool = False


class GraphProjection(BaseModel):
    label: str
    description: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    truncated: bool = False


class CategorySummary(BaseModel):
    lens_id: str | None = None
    category: str
    capability_count: int
    evidence_count: int


class RepositorySummary(BaseModel):
    owner: str
    name: str
    url: str
    default_branch: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    history_start: datetime | None = None
    history_end: datetime | None = None
    files_analyzed: int = 0
    source_bytes: int = 0


class AnalysisResult(BaseModel):
    id: str
    repository: RepositorySummary
    evidence: list[ObservedEvidence]
    entities: list[CodeEntity]
    relationships: list[CodeRelationship]
    observations: list[Observation] = Field(default_factory=list)
    commits: list[CommitRecord]
    behaviors: list[BehaviorSummary] = Field(default_factory=list)
    capabilities: list[Capability]
    timeline: list[TimelineEvent]
    capability_states: list[CapabilityState] = Field(default_factory=list)
    categories: list[CategorySummary]
    lens_set: LensSet | None = None
    capability_graph: GraphProjection
    code_graph: GraphProjection
    workflow_graph: GraphProjection
    data_graph: GraphProjection
    warnings: list[str] = Field(default_factory=list)
    semantic_mode: str = "deterministic"


class AnalysisRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=300)


class HealthResponse(BaseModel):
    status: str = "ok"


class AnalysisSummary(BaseModel):
    id: str
    repository: RepositorySummary
    capability_count: int
